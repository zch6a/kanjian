# Changelog

## 0.1.0 (unreleased)

First version.

- `kanjian screen`: what is in a window, read from its accessibility tree the way a screen reader says
  it. The output covers the focus, counts of each kind of control, landmarks and headings, and then
  the controls in reading order. Tables are read as their size, columns and first row; a paragraph
  with a link is read as one sentence. A control with no name is placed by the nearest named one. In a
  browser, only the page is read.
- `kanjian describe`: an image file, the clipboard, or one window, described by a vision model on this
  machine (Ollama by default). A remote endpoint needs `--allow-remote`. Images are turned upright,
  shrunk, and stripped of metadata before they are sent.
- `kanjian audit`: what makes a window hard to use without sight, with the WCAG 2.2 criterion for each
  finding, as text, JSON or SARIF. Exit code 1 means errors were found; 2 means the window could not be
  read.
- `kanjian watch`: global hotkeys (Ctrl+Shift+Alt with S, F, D, X, Q) to hear the window in front, the
  focus, or a description. For a control with no name, the vision model can guess a label from that
  control's picture.
- Speech through NVDA when it is running, otherwise Windows' voices, otherwise printed text.
- `kanjian dump`: save a window's tree for bug reports and tests.
- English and Chinese output (`--lang zh`).
