![Workbench — a mechanical arm assembling illuminated code on an engineering workbench](readme-assets/cover-renamed.webp)

# Workbench — AI Coding Agent

**A terminal workbench for inspecting, editing, and running code in a local project.**

Give the agent a task in plain language. It sends the conversation to OpenRouter, executes supported tool calls inside a configured workspace (default: `calculator/`), and returns the results to the model until it produces a final response or reaches its 20-iteration limit.

Model requests require your own OpenRouter API key. Python execution can access the host; workspace file checks do not provide an operating-system sandbox.

[Open Workbench](#-quick-start) · [Read the tool boundaries](#-workspace-configuration-and-boundaries)

## <img src="readme-assets/icons/features.svg" width="24" height="24" alt=""> Features

- Stay in a full-screen terminal interface with task input, settings, progress, and results.
- Inspect and edit files through workspace-scoped tools; listings report inaccessible entries individually.
- Run Python with bounded execution time and output.
- Use read-only mode for inspection and save optional transcripts.
- Preview the interface offline without credentials or provider requests.

## <img src="readme-assets/icons/installation.svg" width="24" height="24" alt=""> Installation

Clone with `git clone https://github.com/yaqyn/workbench-ai-agent.git`, then run the commands below from `workbench-ai-agent/`.

Requires **uv** and an interactive terminal. The launcher uses uv to prepare the project’s **Python 3.13+** environment and install its locked dependencies automatically; no separate `uv sync` step is needed. Model tasks require an **OpenRouter API key**.

Create a local `.env` file containing your own key (`.env` is ignored by Git):

```dotenv
OPENROUTER_API_KEY=your_key_here
```

## <img src="readme-assets/icons/launch.svg" width="24" height="24" alt=""> Quick start

```bash
./launch
```

That single command prepares the environment and opens the full terminal workbench. Type a task, such as `Explain how the calculator works`, and press **Enter**. New sessions start in **Inspect only** mode. Press **F2** to choose the project, model, access level, or theme; **Ctrl+Q** quits.

To explore without an API key, run `./launch --preview` and enter a task. All CLI options work with the launcher, including when invoked by absolute path from another directory.

## <img src="readme-assets/icons/usage.svg" width="24" height="24" alt=""> Usage

```bash
./launch "Explain how the calculator handles operator precedence"
./launch "Evaluate 3 + 5 using the calculator" --verbose
```

The default model is `openrouter/free`; set `OPENROUTER_MODEL` or pass `--model` to choose another. Availability and request limits depend on the provider. The interface shows step counts and tool names. `--verbose` adds token usage when supplied by the provider.

### Terminal interface

`./launch` opens a persistent full-screen workbench in an interactive terminal. Enter a task and press **Enter** to run. Settings, activity, errors, and results stay inside the app; it returns to the shell when you quit with **Ctrl+Q**. A new interactive session starts with **Inspect only** selected. Passing a task directly prefills the composer and preserves the existing access default; add `--read-only` for inspection.

```bash
./launch
./launch --preview
./launch --theme light --spacing compact
./launch "Explain the calculator" --read-only
./launch --plain "Explain the calculator" --read-only
```

`--preview` opens the same interface with an offline task runner: press Enter on a task to exercise the complete flow without credentials, network requests, or workspace changes. Export remains available when you explicitly request it. `--tui` requires an interactive terminal and reports a clear error if one is unavailable. Redirected streams, `TERM=dumb`, and `--plain` use linear text instead.

The charcoal, ivory, and brass palette comes from the project cover. Light and high-contrast themes provide alternatives. Open settings with **F2** and use arrows to preview themes instantly across the entire app. The highlighted choice is already selected; **Enter** advances without requiring Space or Tab. Set `WORKBENCH_THEME=light` (or `workbench` / `contrast`) in your environment or project `.env` for a default; `--theme` overrides it. `NO_COLOR` keeps the TUI and its visible selection markers, using monochrome styling.

| Control | Action |
| --- | --- |
| Enter in task input | Run the task; results remain in the app |
| Ctrl+J | Insert a new line; pasted multiline text stays intact |
| F5 / Ctrl+R | Run from any view; duplicate submissions are blocked |
| F2 | Open settings; apply settings and return to the task |
| Arrows in settings choices | Select immediately; theme changes preview live |
| Enter in settings | Advance to the next control; activate the focused button |
| Tab / Shift+Tab | Move between controls, including settings below the viewport |
| Down in path fields | Open completion suggestions; Down/Tab cycles candidates |
| F3 / F4 | Focus results / task input |
| Ctrl+F in results | Search; Enter confirms and Escape cancels |
| Arrows / PageUp / PageDown in results | Browse output |
| Ctrl+N | Clear task input for a new independent task; keep prior results |
| Alt+P / Alt+N | Recall previous / next tasks from this session |
| Ctrl+S | Export activity and results to the text path configured in settings |
| Ctrl+C | Request a stop; no further tools start after the current request/tool finishes |
| F1 | Open help; press again to return |
| Ctrl+Q | Quit; during a run, first request a stop and wait for completion |

Requests run off the UI thread so navigation stays responsive. A run uses a snapshot of its workspace, model, and permissions; settings edits apply to the next task. Errors preserve the task and show a retry path. Interactive requests have a 30-second network timeout and no automatic retries; explicit retries stay under your control. Stopping cannot interrupt an already running tool or undo its changes.

Mouse capture is off, so terminal text selection and copying remain available. Use export for complete output, or `--plain` for ordinary scrollback and screen-reader use. The settings view scrolls to the focused field; compact layouts support 48-column, 18-row terminals. Font family, size, and line height belong to your terminal settings. `--spacing comfortable` adds breathing room; `compact` reduces gaps. Prompts and results stay in memory unless you explicitly enable JSON transcripts or export text. Each task starts a fresh agent conversation.

Accessibility depends on the terminal and assistive software. Keyboard navigation, contrast, plain mode, and narrow layouts are tested; universal accessibility has not been verified with users or assistive devices.

### <img src="readme-assets/icons/usage.svg" width="20" height="20" alt=""> Calculator example

The bundled calculator works independently of the model:

```bash
uv run calculator/main.py "3 + 5 * 2"
```

![Actual JSON output from the bundled calculator](readme-assets/calculator.png)

[Calculator documentation](calculator/README.md) · [Tool definitions](functions/) · [System prompt](prompts.py)

## <img src="readme-assets/icons/security.svg" width="24" height="24" alt=""> Workspace configuration and boundaries

```bash
./launch "Explain this project" --workspace ../folio-static-site --read-only
./launch "Fix the bug and run relevant tests" --workspace ./calculator --max-steps 30
./launch "Inspect the calculator" --read-only --transcript conversation.json
```

`--read-only` exposes only listing and reading tools and also blocks mutation requests in the dispatcher. Normal mode allows file overwrites and Python execution. Inspect the workspace before using normal mode. Python subprocesses have a 30-second timeout; each output stream is truncated to 10,000 bytes. File reads are limited to 10,000 characters. These bounds do not limit subprocess disk usage or isolate executed code from the host.

Transcripts are opt-in JSON conversations, including tool results and file contents. Keep them private when inspecting sensitive projects. Parent directories are created automatically, and transcripts are replaced atomically so a failed save preserves an existing file. Interrupted or failed runs also save the available conversation. In plain mode, provider, step-limit, and transcript-save failures return a nonzero exit status, and Ctrl+C returns 130. The TUI displays failures in place for correction and retry; Ctrl+C requests a stop without closing the interface.

## <img src="readme-assets/icons/architecture.svg" width="24" height="24" alt=""> Architecture

`tui.py` owns the persistent interface and runs provider work off the UI thread. `terminal_ui.py` supplies the linear fallback for `--plain` and redirected streams. The launcher starts `main.py`, which selects the appropriate interface.

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

These checks need no API key and make no provider requests. They cover argument validation, workspace traversal and symlinks, read-only enforcement, Python execution, tool conversations, empty responses, step limits, and atomic transcript persistence. Terminal tests drive Enter submission, live theme selection, settings validation, focus traversal, path completion, multiple tasks, search, export, cancellation, duplicate prevention, and failure recovery.

## <img src="readme-assets/icons/learning.svg" width="24" height="24" alt=""> Learning context

Function schemas, tool dispatch, conversation history, subprocess execution, and a bounded agent loop. The root `test_*.py` files are legacy manual tool demonstrations; some write files or run code. The automated tests in `tests/` use temporary workspaces and simulated provider responses.

---

Built by **[Abdulrahman M. Yaqyn](https://yaqyn.github.io/folio-static-site/)**.

> **Learning Journey Project · Boot.dev**
> Developed through the Boot.dev curriculum and extended through independent work.
