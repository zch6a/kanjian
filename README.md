<div align="center">

# kanjian

**Hear what is on the screen.** A screen and image describer for blind and low-vision Windows users,
local by default, and an accessibility audit for the developers who build those screens.

<a href="https://github.com/zch6a/kanjian/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zch6a/kanjian/actions/workflows/ci.yml/badge.svg"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white">
<img alt="Local by default" src="https://img.shields.io/badge/screen%20contents-stay%20local-2ea44f">
<a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-blue"></a>

**English** · [简体中文](README.zh-CN.md)

</div>

---

*kanjian* (看见) means "to see". It answers the questions a screen reader is slow to answer:

- **What is in this window?** `kanjian screen` gives the window, where the focus is, how many
  headings, buttons and fields there are, and the controls in reading order, said the way a screen
  reader says them. It reads the window's accessibility tree, the same one NVDA and Narrator read, so
  it is exact and needs no model.
- **What does this picture show?** `kanjian describe` asks a vision model about an image file, the
  clipboard, or a window. The model is told it is describing for a blind listener: the main point
  first, any text read exactly, no guessing about people.
- **Why can't my users use this?** `kanjian audit` lists what makes a window hard to use without
  sight: controls with no name, images with no description, names like "button" or "IMG_2041.JPG",
  targets under 24 px with no space around them (WCAG 2.5.8, with its spacing exception), headings
  that skip a level. Output is text, JSON or SARIF. The exit code is 1 when there are errors and 2 when
  kanjian could not read the window, so CI can tell the two apart. (The SARIF has no file locations,
  since a window has none; it suits SARIF viewers, not GitHub code scanning.)

## Privacy

A screen holds mail, messages, half-typed passwords and bank pages, so:

- **The accessibility tree never leaves the machine.** Reading it needs no model.
- **Images go only to a vision model on this machine** (Ollama, LM Studio, llama.cpp, vLLM),
  unless you pass `--allow-remote`. Ollama's cloud models (names ending in `-cloud`) count as remote:
  they are reached through localhost but run on Ollama's servers. Before anything is sent, the image is
  turned upright, reduced to at most 1344 pixels on its long side and stripped of all metadata. kanjian
  says how much it sent and where.
- **Only the window you ask for is captured**, and only it: Windows renders that window for kanjian
  (`PrintWindow`), so a window or notification on top of it does not get into the picture. A minimized
  window, or the desktop and taskbar in front, is refused rather than captured.
- Nothing is captured before kanjian has checked that the model is local and running.
- A local model is reached directly even when a proxy is configured.
- In a browser, `screen`, `audit` and `dump` read the page, not the toolbars and address bar
  (`--whole-window` to include them).

## Install

```bash
pip install "kanjian[windows] @ git+https://github.com/zch6a/kanjian"
```

For describing images, run a local vision model, for example with [Ollama](https://ollama.com):

```bash
ollama pull qwen2.5vl:3b
```

## Use

```bash
kanjian screen --after 3              # switch to a window within 3 s; hear what is in it (with neither
                                      # --after nor --window, kanjian asks: it would read its own terminal)
kanjian screen --window Settings --say auto   # a window by title, spoken (NVDA if running, else a Windows voice)
kanjian describe photo.jpg            # describe an image
kanjian describe --clipboard --task text      # read the text in the copied image
kanjian describe --window "Sign in" --lang zh # a picture of a window, described in Chinese
kanjian audit --window "My App" --format sarif > a11y.sarif
kanjian dump --window "My App" -o tree.json   # save the tree for a bug report (it holds the window's text)
kanjian watch                         # stay in the background, with hotkeys
```

In `kanjian watch`, from any application (Ctrl+Shift+Alt by default, because Ctrl+Alt alone is AltGr
on many keyboards; `--keys win+alt` and so on to change it):

| Hotkey | |
|---|---|
| Ctrl+Shift+Alt+S | overview of the window in front, one line at a time |
| Ctrl+Shift+Alt+F | the focused control in full: name, role, value, states, description |
| Ctrl+Shift+Alt+D | describe the window in front with the vision model |
| Ctrl+Shift+Alt+X | stop speaking |
| Ctrl+Shift+Alt+Q | quit (Ctrl+C in its terminal works too) |

**Speech** goes through NVDA when it is running, in your voice and speed, using NVDA's controller client
DLL (`nvdaControllerClient64.dll`, from NV Access; kanjian looks in NVDA's program folder, or set
`KANJIAN_NVDA_DLL`). If NVDA is running but the DLL is not found, kanjian prints rather than talk over
NVDA in a second voice. Otherwise it uses Windows' own voices (one-shot commands wait until they have
finished speaking), and with `--say text`, the default outside `watch`, it prints.

The vision model is set with `--vlm-url` and `--vlm-model`, or `KANJIAN_VLM_URL`, `KANJIAN_VLM_MODEL`
and `KANJIAN_VLM_API_KEY`. The default is Ollama at `http://localhost:11434/v1` with `qwen2.5vl:3b`.

## Status

0.1, in development.

**Tested:**
- Reading the tree, the summary and the audit: on synthetic trees, and on a real Win32 window that
  the tests open themselves (nothing of the user's is read).
- Windows' voices: the tests speak to a WAV file.
- The vision client: against a stand-in endpoint.

**Not yet tested by the author:** speech through NVDA (not installed on the test machine), and a real
vision model (none installed there). See [POLISH_LOG.md](POLISH_LOG.md).

## Develop

```bash
uv venv && uv pip install -e ".[windows]" pytest ruff
uv run pytest
```

## License

[MIT](LICENSE)
