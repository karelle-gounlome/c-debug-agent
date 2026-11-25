import inspect
import json
import os
import re
import subprocess
import ollama

# Model can be changed without editing the code: MODEL=llama3.1:8b python agent/loop.py
MODEL = os.environ.get("MODEL", "llama3.2:3b")
MAX_STEPS = 8
TARGET = "bugs/compile_error/main.c"


# ---------- Sandbox ----------

SANDBOX_IMAGE = "c-sandbox"


def sandbox_run(path, command):
    """Run a shell command inside the Docker sandbox.

    The folder of 'path' is mounted read-only in /work.
    No network, limited memory, CPU and number of processes.
    """
    folder = os.path.abspath(os.path.dirname(path))
    return subprocess.run(
        ["docker", "run", "--rm",
         "--network", "none",
         "--memory", "256m",
         "--cpus", "1",
         "--pids-limit", "64",
         "-v", folder + ":/work:ro",
         SANDBOX_IMAGE, "sh", "-c", command],
        capture_output=True, text=True, timeout=60)


# ---------- Tools ----------

def compile_c(path: str) -> str:
    """Compile a C file with gcc. Return the errors, or 'Compilation succeeded.'.

    Args:
        path: path of the .c file to compile
    """
    name = os.path.basename(path)
    r = sandbox_run(path, "gcc -Wall -Wextra -o /tmp/a.out " + name)
    if r.returncode == 0:
        return "Compilation succeeded."
    return r.stderr


def run_test(path: str) -> str:
    """Compile the C file, run it, and compare its output with the expected output.

    Args:
        path: path of the .c file to test
    """
    result = compile_c(path)
    if result != "Compilation succeeded.":
        return "TEST FAILED: compilation error\n" + result

    expected_file = os.path.join(os.path.dirname(path), "expected_output.txt")
    with open(expected_file) as f:
        expected = f.read()

    # Compile and run in the same container: the binary is lost when it stops.
    # 'timeout 10' stops programs that run forever.
    name = os.path.basename(path)
    r = sandbox_run(path, "gcc -o /tmp/a.out " + name + " && timeout 10 /tmp/a.out")
    if r.returncode == 124:
        return "TEST FAILED: the program ran for more than 10 seconds"
    if r.stdout == expected:
        return "TEST PASSED"
    return "TEST FAILED: expected " + repr(expected) + ", got " + repr(r.stdout)


def read_file(path: str) -> str:
    """Return the content of a file, with line numbers.

    Args:
        path: path of the file to read
    """
    with open(path) as f:
        lines = f.read().split("\n")
    return "\n".join(str(i) + ": " + line for i, line in enumerate(lines, start=1))


def replace_line(path: str, line: int, new_content: str) -> str:
    """Replace one line of a .c file. Lines are numbered from 1.

    Args:
        path: path of the .c file to modify
        line: number of the line to replace (the first line is 1)
        new_content: new content of the line, without the line number
    """
    # Guard: the agent may only modify .c files, never the expected output
    if not path.endswith(".c"):
        return "Error: you can only modify .c files."
    line = int(line)
    with open(path) as f:
        lines = f.read().split("\n")
    if line < 1 or line > len(lines):
        return "Error: line must be between 1 and " + str(len(lines)) + "."
    lines[line - 1] = new_content
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return "Line " + str(line) + " replaced."


TOOLS = {
    "compile_c": compile_c,
    "run_test": run_test,
    "read_file": read_file,
    "replace_line": replace_line,
}


# ---------- Helpers ----------

def run_tool(name, args):
    """Run a tool by name. Any error is returned as text, never raised."""
    fn = TOOLS.get(name)
    if fn is None:
        return "Unknown tool: " + name + ". Available tools: " + ", ".join(TOOLS) + "."
    try:
        return fn(**args)
    except TypeError as e:
        # Wrong arguments: tell the agent the correct argument names
        params = ", ".join(inspect.signature(fn).parameters)
        return "Error: " + str(e) + ". The arguments of " + name + " are: " + params + "."
    except Exception as e:
        return "Error: " + str(e)


def parse_text_tool_call(text):
    """Look for a tool call written as JSON inside a text answer.

    Return (name, args) if a valid call is found,
    ("", None) if a call is found but its JSON is invalid,
    None if there is no call in the text.
    """
    match = re.search(r'\{\s*"name"', text)
    if match is None:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[match.start():])
    except json.JSONDecodeError:
        return ("", None)
    name = obj.get("name", "")
    args = obj.get("parameters", obj.get("arguments"))
    if not isinstance(name, str) or not isinstance(args, dict):
        return ("", None)
    return (name, args)


# ---------- Agent loop ----------

messages = [
    {"role": "system", "content":
        "You are an agent that fixes C programs. "
        "Do one action at a time. Method: "
        "1) run_test to see the error and its line number, "
        "2) read_file to see the code with line numbers, "
        "3) replace_line to fix only the wrong line, "
        "4) run_test again. "
        "Make the smallest possible fix. Never remove existing functionality. "
        "Stop only when the result is TEST PASSED."},
    {"role": "user", "content": "Fix " + TARGET + " so that its test passes."},
]

for step in range(1, MAX_STEPS + 1):
    r = ollama.chat(model=MODEL, messages=messages, tools=list(TOOLS.values()))
    messages.append(r.message)
    text = r.message.content or ""

    if r.message.tool_calls:
        calls = [(c.function.name, c.function.arguments) for c in r.message.tool_calls]
    else:
        parsed = parse_text_tool_call(text)
        if parsed is not None and parsed[1] is not None:
            # The agent wrote a valid tool call as text: run it anyway
            print("    (tool call found in text)")
            calls = [parsed]
        else:
            status = run_test(TARGET)
            if status == "TEST PASSED":
                print("Agent stopped:", text)
                break
            # The agent wants to stop but the test fails: push it back to work
            print("Agent tried to stop, but:", status.splitlines()[0])
            print("    agent said:", text[:200])
            if parsed is not None:
                hint = ("Your tool call written as text is not valid JSON. "
                        "Use a real tool call instead of text.")
            else:
                hint = ("The test still fails. Do not answer with text. "
                        "Call one of the tools: run_test, read_file, replace_line.")
            messages.append({"role": "user", "content": hint})
            continue

    for name, args in calls:
        print("[step", step, "]", name, str(args)[:80])
        output = run_tool(name, args)
        print("    result:", output[:150])
        messages.append({"role": "tool", "content": output, "tool_name": name})

# Independent check: the test decides, not the LLM
print("Final check:", run_test(TARGET))
