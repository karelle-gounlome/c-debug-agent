import os
import subprocess
import ollama

MODEL = "llama3.2:3b"
MAX_STEPS = 8
TARGET = "bugs/compile_error/main.c"


def compile_c(path: str) -> str:
    """Compile a C file with gcc. Return the errors, or 'Compilation succeeded.'.

    Args:
        path: path of the .c file to compile
    """
    r = subprocess.run(["gcc", "-Wall", "-Wextra", "-o", "/tmp/a.out", path],
                       capture_output=True, text=True, timeout=30)
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

    r = subprocess.run(["/tmp/a.out"], capture_output=True, text=True, timeout=10)
    if r.stdout == expected:
        return "TEST PASSED"
    return "TEST FAILED: expected " + repr(expected) + ", got " + repr(r.stdout)


def read_file(path: str) -> str:
    """Return the full content of a file.

    Args:
        path: path of the file to read
    """
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    """Replace the full content of a .c file with the fixed code.

    Args:
        path: path of the .c file to write
        content: new full content of the file
    """
    # Guard: the agent may only modify .c files, never the expected output
    if not path.endswith(".c"):
        return "Error: you can only write .c files."
    with open(path, "w") as f:
        f.write(content)
    return "File written."


TOOLS = {
    "compile_c": compile_c,
    "run_test": run_test,
    "read_file": read_file,
    "write_file": write_file,
}

messages = [
    {"role": "system", "content":
        "You are an agent that fixes C programs. "
        "Do one action at a time. Method: "
        "1) run_test to see the error, "
        "2) read_file to see the code, "
        "3) write_file with the fixed code, "
        "4) run_test again. "
        "Make the smallest possible fix. Never remove existing functionality. "
        "Stop only when the result is TEST PASSED."},
    {"role": "user", "content": "Fix " + TARGET + " so that its test passes."},
]

for step in range(1, MAX_STEPS + 1):
    r = ollama.chat(model=MODEL, messages=messages, tools=list(TOOLS.values()))
    messages.append(r.message)

    if not r.message.tool_calls:
        status = run_test(TARGET)
        if status == "TEST PASSED":
            print("Agent stopped:", r.message.content)
            break
        # The agent wants to stop but the test fails: push it back to work
        print("Agent tried to stop, but:", status.splitlines()[0])
        messages.append({"role": "user", "content":
            "The test still fails. Do not answer with text. "
            "Call one of the tools: run_test, read_file, write_file."})
        continue

    for call in r.message.tool_calls:
        name = call.function.name
        args = call.function.arguments
        print("[step", step, "]", name, str(args)[:80])

        fn = TOOLS.get(name)
        if fn is None:
            output = "Unknown tool: " + name
        else:
            try:
                output = fn(**args)
            except Exception as e:
                # A tool error becomes an observation for the agent, not a crash
                output = "Error: " + str(e)

        print("    result:", output[:150])
        messages.append({"role": "tool", "content": output, "tool_name": name})

# Independent check: the test decides, not the LLM
print("Final check:", run_test(TARGET))
