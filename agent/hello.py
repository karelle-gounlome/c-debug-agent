import ollama

r = ollama.chat(model="llama3.2:3b",
                messages=[{"role": "user", "content": "Explique un segfault en une phrase."}])
print(r["message"]["content"])
