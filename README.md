![Workbench — a mechanical arm assembling illuminated code on an engineering workbench](readme-assets/cover-renamed.png)

# Workbench — AI Coding Agent

**A command-line agent that can inspect, edit, and run a local calculator project.**

Give the agent a task in plain language. It sends the conversation to OpenRouter, executes supported tool calls inside a configured workspace (default: `calculator/`), and returns the results to the model until it produces a final response or reaches its 20-iteration limit.

**Requirements:** Python 3.13+, uv, and an OpenRouter API key for model requests. Python execution can access the host; workspace file checks do not provide an operating-system sandbox.

[Run a read-only task](#-quick-start) · [Read the tool boundaries](#-workspace-configuration-and-boundaries)

## <img src="readme-assets/icons/features.svg" width="24" height="24" alt=""> Features

- Inspect and edit files through workspace-scoped tools.
- Run Python with bounded execution time and output.
- Use read-only mode for inspection and save optional transcripts.
- Examine tool behavior without a provider request using the bundled calculator.

## <img src="readme-assets/icons/installation.svg" width="24" height="24" alt=""> Installation

Requires **Python 3.13+**, **uv**, and an **OpenRouter API key**.

```bash
uv sync
```

Create a local `.env` file containing your own key (`.env` is ignored by Git):

```dotenv
OPENROUTER_API_KEY=your_key_here
```

```bash
uv run main.py "Explain how the calculator handles operator precedence"
uv run main.py "Evaluate 3 + 5 using the calculator" --verbose
```

The default model is `openrouter/free`; set `OPENROUTER_MODEL` or pass `--model` to choose another. Availability and request limits depend on the provider. Verbose mode prints step counts, token usage when supplied, and tool names.

## <img src="readme-assets/icons/launch.svg" width="24" height="24" alt=""> Quick start

```bash
./launch "Explain how the calculator works" --read-only
```

The launcher uses uv to prepare the Python environment automatically. Run `./launch` without arguments to enter a task interactively. All CLI options work with the launcher; it can also be invoked by absolute path from another directory. Set `OPENROUTER_API_KEY` in your environment or the project `.env` before sending a task.

## <img src="readme-assets/icons/usage.svg" width="24" height="24" alt=""> Calculator example

The bundled calculator works independently of the model:

```bash
uv run calculator/main.py "3 + 5 * 2"
```

![Actual JSON output from the bundled calculator](readme-assets/calculator.png)

[Calculator documentation](calculator/README.md) · [Tool definitions](functions/) · [System prompt](prompts.py)

## <img src="readme-assets/icons/security.svg" width="24" height="24" alt=""> Workspace configuration and boundaries

```bash
uv run main.py "Explain this project" --workspace ../folio-static-site --read-only
uv run main.py "Fix the bug and run relevant tests" --workspace ./calculator --max-steps 30
uv run main.py "Inspect the calculator" --read-only --transcript conversation.json
```

`--read-only` exposes only listing and reading tools and also blocks mutation requests in the dispatcher. Normal mode allows file overwrites and Python execution. Inspect the workspace before using normal mode. Python subprocesses have a 30-second timeout; each output stream is truncated to 10,000 bytes. File reads are limited to 10,000 characters. These bounds do not limit subprocess disk usage or isolate executed code from the host.

Transcripts are opt-in JSON conversations, including tool results and file contents. Keep them private when inspecting sensitive projects. Interrupted or failed runs also save the available conversation. Provider failures and exhausted step limits return a nonzero exit status; Ctrl+C returns 130.

## <img src="readme-assets/icons/architecture.svg" width="24" height="24" alt=""> Architecture

The agent loop sends conversation history to the model, dispatches supported tool calls, and returns tool results for the next step.

![Agent workflow: prompt, model, tools, response](readme-assets/workflow.svg)

| Tool | What it does |
| --- | --- |
| `get_files_info` | List files and directories |
| `get_file_content` | Read file contents |
| `write_file` | Write a file |
| `run_python_file` | Execute a Python file with a 30-second timeout |

`call_function.py` validates tool arguments and dispatches requests into the configured workspace. The default calculator path is anchored to the project, so launching from another directory works. File tools resolve symlinks and reject paths outside that directory. Python execution is a subprocess, so these checks are not an operating-system sandbox. Run the course agent against disposable local work you are comfortable letting it modify.

## <img src="readme-assets/icons/verification.svg" width="24" height="24" alt=""> Verification

```bash
uv run python -m unittest discover -s tests -v
uv run calculator/tests.py
```

These checks need no API key and make no provider requests. They cover argument validation, workspace traversal and symlinks, read-only enforcement, Python execution, tool conversations, empty responses, and step limits.

## <img src="readme-assets/icons/learning.svg" width="24" height="24" alt=""> Learning context

Function schemas, tool dispatch, conversation history, subprocess execution, and a bounded agent loop. The root `test_*.py` files are legacy manual tool demonstrations; some write files or run code. The automated tests in `tests/` use temporary workspaces and simulated provider responses.

---

Built by **[Abdulrahman M. Yaqyn](https://yaqyn.github.io/folio-static-site/)**.

> **Learning Journey Project · Boot.dev**
> Developed through the Boot.dev curriculum and extended through independent work.
