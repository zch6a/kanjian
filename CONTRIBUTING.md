# Contributing

Thanks for helping. kanjian is small on purpose: plain Python, Pillow, and comtypes on Windows. The
most useful things you can send are a saved tree of a window that kanjian reads badly, and a note on
what a screen reader says for the same window.

## Set up

```bash
git clone https://github.com/zch6a/kanjian && cd kanjian
uv venv && uv pip install -e . pytest ruff
uv run pytest            # about 85 tests; no model, no screen reader and no audio device needed
uv run ruff check src tests
```

The tests run on Windows, macOS and Linux. Those that need UI Automation or Windows' voices skip
elsewhere.

## How the tests work

- **Trees, not screens.** Most tests build an accessibility tree by hand (`tests/test_tree.py`) or
  load a saved one (`kanjian dump`), so the reading and the audit can be tested anywhere.
- **A real window of their own.** `tests/win32window.py` opens a plain Win32 window with standard
  controls, and `tests/test_uia.py` reads it through UI Automation. The tests never read the windows
  of the person running them.
- **A stand-in vision model.** `FakeVLM` in `tests/test_vision.py` is a local HTTP server that answers
  like an OpenAI-compatible endpoint and records what it was sent, so the tests can check that images
  are shrunk and stripped of metadata before they go anywhere.
- **Speech to a file.** Windows' voices are tested by speaking to a WAV file. GitHub's Windows runners
  have no audio device, which is how the fallback to printing is tested.

## Reporting a window that reads badly

```bash
kanjian dump --window "Your app" -o tree.json
```

The file holds every name and value in the window, which can include private text. Read it, and
remove anything private, before you attach it to an issue. Say what kanjian said, and if you can,
what NVDA or Narrator says for the same control.

## Changing what kanjian says or reports

- Words should be the ones screen readers use (NVDA's, where they differ), in both English and
  Chinese. `ROLE_WORDS`, `STATE_WORDS` and `TEXT` in `src/kanjian/tree.py` hold them.
- An audit rule should name the WCAG 2.2 success criterion it checks, or say that it is best
  practice. Add it to `RULES` and to the rules table in both READMEs.
- Check a new rule against a real window for false positives. UI Automation reports some things
  differently for Win32, WinForms, WPF and browsers. One example: Win32 calls every child window
  focusable.

## Pull requests

- Add a test that fails without your change.
- Test data is synthetic: no real names, mail, screenshots of real people, or real keys.
