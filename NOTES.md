# Notes

## Week 1: first agent loop

Model: llama3.2:3b (local, CPU only)
Bug: bugs/compile_error/main.c (missing ';' after 'int x = 42')
Max steps: 8

### Results (baseline)

| Run | Result | Steps | Wasted steps (bad tool arguments) |
|-----|--------|-------|-----------------------------------|
| 1   | PASSED | 8     | 3                                 |
| 2   | FAILED | 8     | 1 + 3 text answers                |
| 3   | PASSED | 7     | 4                                 |
| 4   | FAILED | 8     | 5                                 |

Success rate: 2/4 (50%)

### Diagnosis

The model understands the bug (it finds the missing ';' almost every time).
The problem is malformed tool calls:
- invented arguments: 's', 'f', 'mode', 'test_name'
- missing arguments: 'path', 'content'
- text answers instead of tool calls

### Observations

- The agent cheated: it deleted the code so that it compiles.
  Fix: added run_test, which checks the program output.
- The agent forgot the '#' of #include when rewriting the file.
  Idea: a tool that edits one line instead of rewriting the whole file.
- The agent called tools with wrong arguments and the program crashed.
  Fix: try/except, so the error is sent back to the agent.
- The agent stopped with a text answer while the test still failed.
  Fix: if the agent stops, run the test; if it fails, push it back to work.

### Next ideas

- Try a bigger model (llama3.1:8b), better at tool call formats.
- Add a replace_line tool for small, targeted edits.


## Experiment: Docker sandbox

compile_c and run_test now run inside a Docker container (image c-sandbox):
no network, 256 MB memory, 1 CPU, 64 processes, folder mounted read-only,
programs stopped after 10 seconds.

| Run | Model        | Result | Steps | Bad arguments |
|-----|--------------|--------|-------|---------------|
| 1   | llama3.1:8b  | PASSED | 4     | 1             |
| 2   | llama3.1:8b  | PASSED | 4     | 0             |
| 3   | llama3.1:8b  | PASSED | 5     | 1             |
| 4   | llama3.1:8b  | PASSED | 6     | 1             |

Success rate: 4/4 (100%). Average steps: 4.75.
The sandbox did not reduce reliability.

Observations:
- In run 4 the agent also rewrote line 6, which was correct.
  The test passed, but the fix was not minimal.
  Idea: also measure the number of changed lines.
- The agent always loses the indentation of the lines it replaces.
  Idea: replace_line could keep the original indentation automatically.
