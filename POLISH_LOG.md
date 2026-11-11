# Polish log

Each round goes through the whole project: code, tests, docs, and actually running it.

## Development

- **Scope**: for blind and low-vision Windows users, an overview of the window in front read from its
  accessibility tree (UI Automation), image and window descriptions from a vision model, and global
  hotkeys. For developers, an accessibility audit with text, JSON and SARIF output.
- **Privacy by design**:
  - the tree never leaves the machine;
  - images go only to a model on this machine unless `--allow-remote` is passed, and a remote
    endpoint is refused before anything is captured;
  - images are downscaled to 1344 px and rebuilt from raw pixels, so no metadata survives;
  - only the requested window is captured;
  - `kanjian dump` warns that the file holds the window's text.
- **Found while building**: reading order bucketed rows by 12 px bands, so two buttons on one line at
  y=10 and y=12 were read right to left. Rows are now grouped by vertical overlap.
- **Tests (36)**:
  - Synthetic trees cover the summary (English and Chinese), the audit rules and the JSON round
    trip.
  - A stand-in vision endpoint checks the local-only rule, proxy bypass, metadata removal, prompts
    and failures.
  - A real Win32 window, opened by the tests themselves, is read through UI Automation: names,
    roles, a checked box, an edit's value, a disabled button and a 12x12 target. It also serves the CLI
    `--window` test.
  - Windows' voices speak to a WAV file, so the tests make no sound.
  - A fake controller library stands in for NVDA.
  - The watch-mode actions are tested without a desktop.
- **Not yet verified**: speech through real NVDA (not installed here) and a real vision model (no
  Ollama here).
