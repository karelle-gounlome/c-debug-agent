import subprocess
import ollama

MODEL = "llama3.2:3b"

def compile_c(path: str) -> str:
    """Compile un fichier C avec gcc et renvoie les erreurs du compilateur.

    Args:
        path: chemin du fichier .c à compiler
    """
    result = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-o", "/tmp/a.out", path],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        return "Compilation réussie."
    return result.stderr

messages = [{"role": "user",
             "content": "Compile le fichier bugs/compile_error/main.c et explique l'erreur."}]

# 1) Le LLM décide s'il veut utiliser un outil
r = ollama.chat(model=MODEL, messages=messages, tools=[compile_c])
messages.append(r.message)

# 2) Le code exécute l'outil demandé
for call in r.message.tool_calls or []:
    print(f">> Le LLM appelle : {call.function.name}({call.function.arguments})")
    output = compile_c(**call.function.arguments)
    print(f">> Résultat de gcc :\n{output}")
    messages.append({"role": "tool", "content": output, "tool_name": call.function.name})

# 3) Le LLM lit le résultat et explique
final = ollama.chat(model=MODEL, messages=messages)
print(">> Explication du LLM :\n", final.message.content)
