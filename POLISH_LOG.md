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

## Round 1

A new user's first run, and a blind review by a fresh agent. The agent made its own test windows (Win32, and an HTML page in a throwaway Edge profile), read nothing of the user's, and reproduced 13 of its 15 findings on a machine at 150% display scaling. All 15 are fixed.

- **First run, from GitHub**: the README's install command works into an empty environment in 18 s. `kanjian describe` with no model running printed a raw socket error (in the system's language) with no hint. It now says no model is answering and how to get one (`ollama pull qwen2.5vl:3b`), and it checks before anything is captured. A model that is not pulled says to pull it; a missing image says so.
- **Capture was wrong at any display scaling but 100%.** kanjian never declared DPI awareness, so window rectangles were in scaled units and captures in real pixels: at 150%, two thirds of a "window" picture was what lay around it. kanjian is now per-monitor DPI aware from the start.
- **"Only the window you ask for" was not true.** kanjian copied that area of the screen, so a window on top got into the picture, a minimized window gave a black image, and the desktop in front meant the whole screen. Now Windows renders the window itself (`PrintWindow`, full content). A test puts a green window over a red one, and the red one's capture is red with no green. Minimized windows and the desktop or taskbar are refused.
- **One-shot commands said nothing.** The Windows voice speaks in the background and the process exited, so `kanjian screen --say auto` was silent. One-shot commands now wait until the voice has finished; a silent test checks it. My test had only written to a WAV file, which waits by itself. Also:
  - with NVDA running but its DLL not found, `--say auto` used to talk over NVDA in a second voice; it now prints and says why;
  - `--say voice` without voices is an error, not silent printing.
- **Every element had a phantom "unknown" child.** At the end of the children, comtypes returns an empty COM pointer, not `None`, so a 3-item list was "4 items". The loop now tests the pointer itself.
- **Plain buttons are not toggles.** While fixing reading, plain buttons came out as "partially checked": UIA reports toggle state 2 for elements without the toggle pattern. The state is now read only where the pattern is available. Toggle buttons say "pressed" and "not pressed", as screen readers do; mixed check boxes say "partially checked".
- **Big windows were slow, and cut short silently.** About 15 cross-process calls per element (2,000 elements in 3.25 s) became one cached request for the whole subtree: the test window in 43 ms. A tree cut at the limit is now said so in the overview, and noted in the audit.
- **Lists counted only their visible items.** A 3,000-item list was "7 items"; items scrolled out of view now count.
- **Focus:**
  - With `--window`, the focus was never looked for; now the focus inside that window is found, or kanjian says it is in another window.
  - With no `--window` or `--after`, kanjian read the terminal it was typed in; it now asks which window is meant.
  - Ctrl+Shift+Alt+F reads only the focus, not the whole window.
  - The describe hotkey takes the window title from Windows, not from a full tree read.
- **Headings were cut at their first comma** ("Profile, and privacy" became "Profile"). They are now read whole.
- **Labels were read twice** ("Display name", then "Display name, edit"). A text label right before the control it names is now dropped.
- **Named groups** are now in the overview ("Network, group").
- **Audit:**
  - In a browser it reported Edge's own address bar and translate bubble, and `screen` read the address bar with the local file path. Browsers and Electron apps are now read as their page (the largest document), with `--whole-window` for the rest.
  - The small-target rule checked only one side and ignored WCAG 2.5.8's spacing exception, flagging default-height fields and well-spaced check boxes. It now fails only small targets crowded by others.
  - Paths leave out nameless layout panes, so they can be followed by ear.
  - Plurals are right ("2 check boxes").
- **Watch:**
  - Ctrl+C took effect only at the next hotkey: the loop blocked in `GetMessage`. It now polls.
  - Ctrl+Alt+letter is AltGr on many keyboards (AltGr+Q is "@" in German), so the default is now Ctrl+Shift+Alt, and `--keys` changes it.
  - A new X key stops speaking.
  - The overview is spoken line by line, so it can be cut short.
- **The local-only check:**
  - `127.attacker.example` passed for local, because the check looked at text, not addresses. It now compares real loopback IP addresses.
  - Ollama's cloud models (`-cloud`), reached through localhost but run remotely, now need `--allow-remote`.
- **Photos lost their rotation.** The EXIF orientation is now applied before the metadata is stripped.
- **Exit codes**: `audit` exits 1 when it finds errors and 2 when kanjian itself fails, so CI can tell them apart.
- **Docs**:
  - the README now says that SARIF output has no file locations (a window has none), so it suits viewers, not GitHub code scanning;
  - the Chinese output has words for every role;
  - the counts line is left out when there is nothing to count.
- **Test harness**: the test window's 64-bit module handle was cut to 32 bits, which caused an access-violation dump on every run. Fixed.
- **Patching rule** (from a mistake in livesub): each replacement must match exactly once, so that no code lands in the wrong class.
- 58 tests, ruff clean.

## Round 2

Real use, the way a blind user would meet it. kanjian read two windows made for the purpose:
- a WinForms order form (labels and fields, a drop-down, a check box, radio buttons in a group box, a picture, an icon-only button, a link, a data grid, two tabs);
- an HTML page in a throwaway Edge profile (navigation, headings that skip a level, images with and without alt text, a paragraph with a "click here" link, a table, a labelled number field, a toggle button and an icon-only button).

Each output was judged as a screen reader user would: most important first, nothing said twice, nothing that means nothing. Both test windows were closed afterwards, and only the throwaway Edge profile's processes were stopped.

- **Tables were the framework's internals.** "DataGridView, table, 4 items: 首行, 行 0, 行 1, 行 2" (Windows localizes "Top Row", "Row 0"). Tables are now read as "table, 3 rows, columns: Item, Quantity, Price; first row: Tea, 2, 4.00". Edge reports `<th>` cells as plain data items, so header cells are also recognized by the page's ARIA role (`columnheader`, `rowheader`), which UIA exposes. A table named after its class ("DataGridView") is an audit warning.
- **The browser's own placeholder counted as alt text.** Edge names an image without alt "要获取缺失的图片说明，请打开上下文菜单。" ("To get missing image descriptions, open the context menu."), so the audit missed it. Browser placeholders are now treated as no name.
- **A paragraph with a link was three lines** ("…returns policy," / "click here, link" / "."). Text and links on one line are now read as one sentence: "…returns policy, click here (link)." A row of links alone stays a list of links.
- **Unlabeled controls get a landmark**: "unlabeled button, near 'Favourite'", from the nearest named control within 400 px, never the page or a group. In `watch`, Ctrl+Shift+Alt+F on a control with no name also asks the vision model for a guess, sending only that control's pixels, cut from the window's picture: "Probably: Settings (a guess from its picture)."
- **Label colons** are not read ("Name, edit", not "Name:, edit").
- **The page itself was listed as a control** ("kanjian test page, document"). It is not; the window line names it.
- **A focus outside the page** (Edge's sync bubble had it) is said to be: "Focus (outside the page): …".
- **Audit false positives:**
  - A combo box's drop-down arrow was flagged as a small target. Parts of compound controls (combo, spin box, slider, split button, scroll bar) are no longer separate targets.
  - An icon inside an unlabeled button was reported again as an image without a description; the button's error covers it.
- **CI found a real gap.** GitHub's Windows runners have no audio device, and speaking raised a COM error (`0x8004503A`). On a PC without working audio that would have crashed kanjian. Speech now falls back to printing, once saying why, and the speech-timing test skips where there is no audio device.
- 71 tests, ruff clean.

## Round 3

Checked against the standards and the screen readers themselves: WCAG 2.2 and its Understanding pages, WCAG2ICT (how WCAG applies to desktop software), the ARIA Authoring Practices, NVDA's spoken words, axe-windows' rules and the UIA documentation. Fifteen findings, all fixed. The two test windows from round 2 were used again to check each change for false positives.

**What the reader gets from UIA**
- **Every Win32 control said "invalid entry".** `IsDataValidForForm` reads False on plain Win32 controls, so it cannot be trusted. Invalid fields now come from the page's own `aria-invalid`.
- **Radio buttons never said "not checked".** They have no Toggle pattern: their state is `IsSelected`. They now say "checked" or "not checked", as NVDA does.
- **Read only** was set on every edit with no Value pattern (UIA's default is TRUE). It is now asked only where there is a Value pattern; sliders and progress bars fall back to their RangeValue.
- **New from UIA:** keyboard focusability, landmarks (navigation, main, search, form), custom controls' own role names ("rating"), a table's own row and column counts (a virtualized grid holds only the rows on screen), and the window's DPI.

**Wording, as NVDA says it**
- A table is "4 rows, 3 columns: …": the header row counts, as NVDA counts it.
- A pressed button is a "toggle button, pressed"; a half-checked box is "half checked"; Chinese uses NVDA's "未标注的" and "错误的输入".
- Pages now have a **Landmarks** line ("Landmarks: Main, navigation landmark; Search landmark").

**The audit**
- **Each finding names its WCAG criterion**, and the severity follows what it breaks: an image named "IMG_2041.JPG" is an error (1.1.1, failure F30); "click here" in a sentence is info (2.4.9, since 2.4.4 lets the sentence explain it), alone it is a warning (2.4.4).
- **Target size is in effective pixels.** At 150% scaling a 30 px button is 20 effective pixels: it was passed before, and is flagged now. Page zoom is not taken into account, and the message says so. Links in a sentence are exempt, as 2.5.8 says.
- **A spin box's arrows** are info, "check by hand": WCAG2ICT reads the user-agent exception as covering sizes the platform sets. A combo box's arrow and a slider's thumb are still part of one target.
- **New rules:** `keyboard-unreachable` (2.1.1; arrow-key containers left out), `class-like-name`, `name-includes-role`, and `no-name` for custom controls, lists and tables that take the focus. Testing found that Win32's proxy calls every child window focusable (a PictureBox showed as a focusable, unnamed pane), so plain panes and groups count only on web pages.
- **Off-screen elements** are checked for names, because a screen reader reaches them, but not for size. The CLI says how many there were.
- `duplicate-name` is a warning when the controls are in the tab order. `heading-skip` says it is best practice, not a WCAG failure.
- **SARIF** rules carry a description, tags (`WCAG 1.1.1`, `best-practice`) and a help link; results carry the criterion and the W3C page that explains it.
- **README**: an audit-rules table, and what the audit cannot tell you. UIA sees a web page through the browser, so for web content it points to axe-core.

- **Test fix**: a stand-in vision server swapped its handler after its thread had started, which could race. It now gets its status and body when it is made.
- 78 tests, ruff clean.
