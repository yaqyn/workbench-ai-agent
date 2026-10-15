# Workbench terminal design

Workbench is a local coding agent for inspecting, editing, and executing project code. Its interface should make the workspace and access level visible before a task starts.

## Visual direction

The canonical cover in `readme-assets/cover-renamed.webp` depicts an engineering desk with brass illumination, dark machinery, and ivory code. Use that material palette rather than a generic neon developer console.

| Role | Workbench | Light | High contrast |
| --- | --- | --- | --- |
| Surface | `#171612` | `#FAF6ED` | `#000000` |
| Text | `#F4E8CA` | `#27231B` | `#FFFFFF` |
| Accent / focus | `#E9B968` | `#755014` | `#FFFF00` |

All text/background pairs exceed 4.5:1 contrast by the WCAG relative-luminance formula. These values describe the requested palette; terminal color conversion can change actual rendering. Text markers and explicit status labels carry meaning independently of color.

Use the terminal's own monospace font and zoom. Never change the user's global terminal configuration. Comfortable spacing is the default; compact is optional. Use sentence case, no large ASCII art, animation, or decorative boxes in result output.

## Runtime ownership and shared controls

`terminal_ui.PALETTES` owns the palette values above. `WorkbenchApp.make_style()` maps these into surface, text, accent, focus, completion, selection, and scrollbar roles through one `DynamicStyle`. Every persistent view consumes that adapter. `NO_COLOR` selects a monochrome adapter while keeping the full TUI. `TerminalUI` owns the separate linear fallback and never launches dialogs.

`Choice` is the canonical choice control. One index owns highlight and selection: arrows commit immediately and call the theme adapter synchronously. A focused selection uses an inverse background and `>`; an unfocused selection uses `*`. Enter advances; it never requires a second selection gesture. Form fields retain their text when Enter advances. Focus order includes offscreen settings and scrolls them into view.

## Layout and interaction

```text
Workbench / inspect, edit, execute
Access | project | model
+ Results: activity, tool progress, final responses, errors +
+ Task composer: Enter runs; Ctrl+J inserts a newline       +
Run task   Stop task   Settings   Export   Help
Persistent status
Keyboard controls
```

One `Application` owns the terminal until explicit quit. Task results and failures never close the UI. Settings and help swap the central panel without leaving the alternate screen or spawning shell prompts. F2 returns from settings, F3 focuses results, F4 focuses the task, and F1 toggles help. Repeated tasks share a visible result log but each starts an independent provider conversation. Ctrl+N clears the composer; Alt+P/Alt+N recall session tasks. No history is persisted implicitly.

The results pane owns output scrolling and search. The settings pane owns form scrolling. At 48 columns and 18 rows, the composer contracts to one visible row and the action row retains Run, Stop, and Settings. Export and Help remain available via Ctrl+S and F1. At larger sizes the composer has three visible rows. Comfortable spacing adds one line between results and input; compact removes it. There is no animation or mouse capture. Use terminal selection for visible text, explicit export for complete output, or plain mode for linear scrollback.

## Async states and recovery

Run captures settings and sets busy synchronously before scheduling background work, preventing duplicate submissions. Provider calls and tools execute off the UI thread. Worker events enter a queue that is drained before completion feedback, so late progress cannot replace a completed status. Settings can change during a run; the in-flight workspace and permissions remain fixed.

Validation preserves entered data and focuses the invalid field. Pending, completed, failed, and stopped states share the same status region. Failures remain in results and permit explicit retry. Interactive requests use a 30-second network timeout with automatic retries disabled. Ctrl+C requests cooperative cancellation; checks before requests and between tools prevent further work. An in-flight request/tool finishes first. Completed changes cannot be undone by stopping. Ctrl+Q during work requests a stop and asks the user to wait before quitting.

JSON transcripts remain opt-in, including interrupted or failed runs; they can include file contents. Ctrl+S explicitly exports results to the configured text path, replacing that file. Prompt history stays in memory. Model/path text is rendered literally with terminal control characters removed.

## Review of the design plan

The earlier sequence of setup dialogs was rejected by the user because confirmation dropped back into ordinary terminal prompts and results. The approved replacement is a persistent workbench with a task composer, settings, results, help, and in-app recovery. Keep the cover palette and restrained typography. Spend visual emphasis on keyboard focus and current access; avoid decorative dashboards and motion.

## Verification boundaries

Offline integration tests drive the real application through pipe input, covering Enter submission, live arrow previews, focus order, multiple tasks, completion, search, export, duplicate prevention, delayed work, cancellation, errors, retry, and ordered progress. Terminal rendering is inspected at 80x24 and 48x18 using a pseudo-terminal. The agent/tool and calculator suites remain provider-free. Manual screen-reader and cross-emulator validation remain necessary before claiming universal accessibility.
