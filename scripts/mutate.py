"""Test the tests: plant one plausible bug at a time in a copy of the code and check that a test fails.

    python scripts/mutate.py            # all mutants
    python scripts/mutate.py 12 30      # only these (numbers as printed)

The unmutated suite must pass first; otherwise every mutant would look "caught". The repository is
never modified: the code is copied to a temporary folder. Each original must appear exactly once in
its file, so that a mutant never lands somewhere it was not meant for.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T, U, C, V, W, S = (f"src/kanjian/{m}.py" for m in ("tree", "uia", "cli", "vision", "windows", "speak"))

MUTANTS = [
    # how one element is said
    (T, 'toggle = n.role == "button" and bool({"pressed", "not_pressed", "mixed"} & n.states)', "toggle = False"),
    (T, "role = n.kind  # the control's own role name", "pass  # the control's own role name"),
    (T, 'parts = [n.name.strip().rstrip(":：").rstrip() or n.name.strip(), role]', "parts = [n.name.strip(), role]"),
    (T, 'elif n.role in INTERACTIVE or n.role == "image":  # "unlabeled button"', 'elif True:  # "unlabeled button"'),
    (T, 'if n.value and n.value != n.name and n.role in ("edit", "combobox", "slider", "spinner", "progressbar"):', "if False:"),
    (T, 'shown = {"half_pressed"} | n.states - {"mixed"} if toggle and "mixed" in n.states else n.states', "shown = n.states"),
    (T, '    if self.name.strip().lower() in PLACEHOLDER_NAMES:\n            self.name = ""', "    if False:\n            pass"),
    # what is read, and in what order
    (T, "if rows and node.bbox[1] < rows[-1][0].bbox[1] + max(1, min(x.bbox[3] for x in rows[-1])) / 2:", "if False:"),
    (T, "return [x for row in rows for x in sorted(row, key=lambda x: x.bbox[0])]", "return [x for row in rows for x in row]"),
    (T, 'if _meaningful(n) and n is not root and n.role != "document":', "if _meaningful(n) and n is not root:"),
    (T, '                return  # a button\'s inner text is its name already', "                pass"),
    (T, "and _label_text(x.name) and _label_text(x.name) == _label_text(out[i + 1].name))]", "and False)]"),
    (T, "and any(x.role == \"text\" for x in (*runs[-1], n)):", "and True:"),
    (T, "    if n.landmark:\n        return True  # \"Main, navigation landmark\"", "    if False:\n        return True"),
    (T, "landmark = _nearest_named(n, items)", "landmark = None"),
    (T, 'or o.role in ("window", "tabitem", "document", "group", "dialog", "pane"):', ":"),
    (T, "        if len(runs) > max_items:", "        if False:"),
    # tables and lists
    (T, "n_rows = n.rows or len(rows)", "n_rows = len(rows)"),
    (T, "n_rows = n.rows or len(rows)", "n_rows = n.rows or len(rows) - 1"),
    (T, "columns = [(c.value or c.name).strip() for c in valued] if valued else [x for x in cells if x]", "columns = [x for x in cells if x]"),
    (T, "kids = n.children  # all of them", 'kids = [c for c in n.children if "offscreen" not in c.states]  # all of them'),
    (T, "page = max(documents, key=lambda d: (d.bbox[2] * d.bbox[3]) if d.bbox else 0)", "page = documents[0]"),
    # the audit
    (T, '        if not name and (n.role in INTERACTIVE or takes_focus):', '        if not name and n.role in INTERACTIVE:'),
    (T, 'or (in_page and n.role in ("group", "pane")))', 'or n.role in ("group", "pane"))'),
    (T, "elif n.role == \"image\" and not name and not n.description and not inside_control:", "elif n.role == \"image\" and not name and not n.description:"),
    (T, '                issues.append(Issue("error", "meaningless-name", where,', '                issues.append(Issue("warning", "meaningless-name", where,'),
    (T, 'elif n.role in ("link", "hyperlink") and _in_sentence(n, siblings):', "elif False:"),
    (T, "            if gap <= max(n.bbox[3], s.bbox[3]):", "            if True:"),
    (T, 'return bool(CLASS_LIKE.match(name) and re.search(r"\\.[A-Z]", name))', "return bool(CLASS_LIKE.match(name))"),
    (T, '(n.role == "image" and low.startswith(word + " of "))', 'low.startswith(word + " ")'),
    (T, "and not any(a.role in ARROW_KEYS for a in path)):", "):"),
    (T, 'and n.focusable is False and not hidden and "disabled" not in n.states', "and n.focusable is False and not hidden"),
    (T, "size = min_target * scale", "size = min_target"),
    (T, "        if (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 < r * r:", "        if False:"),
    (T, "        if min(ow, oh) < size and ((ox + ow / 2) - cx) ** 2 + ((oy + oh / 2) - cy) ** 2 < size * size:", "        if False:"),
    (T, "and not any(a.role in WHOLE for a in p)]", "]"),
    (T, "if n in targets and _small_and_crowded(n, targets, size) and not _in_sentence(n, siblings):", "if n in targets and _small_and_crowded(n, targets, size):"),
    (T, '            part = next((a for a in reversed(path) if a.role in PARTS), None)', "            part = None"),
    (T, "            if last_level and n.level > last_level + 1:", "            if last_level and n.level > last_level:"),
    (T, 'issues.append(Issue("warning" if tabbable else "info", "duplicate-name"', 'issues.append(Issue("info", "duplicate-name"'),
    (T, '    return sorted(issues, key=lambda i: order[i.severity])', "    return issues"),
    # reading UI Automation
    (U, 'states.add("checked" if get(P_SELECTED, False) else "unchecked")', 'states.add("checked") if get(P_SELECTED, False) else None'),
    (U, 'if "invalid=true" in str(get(P_ARIA_PROPERTIES, "") or "").lower().replace(" ", ""):', "if not get(30103, True):"),
    (U, 'if role == "edit" and get(P_VALUE_AVAILABLE, False) and get(P_READONLY, False):', 'if role == "edit" and get(P_READONLY, False):'),
    (U, 'states.add("pressed" if toggle == 1 else "mixed" if toggle == 2 else "not_pressed")', 'states.add("checked" if toggle == 1 else "unchecked")'),
    (U, '        elif aria == "rowheader":\n            role = "rowheader"', '        elif aria == "rowheader":\n            role = "headeritem"'),
    (U, 'landmark = str(get(P_LANDMARK_NAME, "") or "") or LANDMARKS[landmark_type] or "landmark"', 'landmark = ""'),
    (U, "            rows, columns = get(P_ROWS, None), get(P_COLUMNS, None)", "            pass"),
    (U, '                value = f"{number:g}"', "                pass"),
    (U, "            tree.scale = (ctypes.windll.user32.GetDpiForWindow(hwnd) or 96) / 96", "            tree.scale = 1.0"),
    # the command line: never read the terminal, never capture before checking
    (C, 'if not getattr(args, "window", None) and not args.after:', "if False:"),
    (C, "    if not (args.image or args.clipboard or args.window or args.after):", "    if False:"),
    (C, "    client.check()  # and a model that is not running", "    pass  # and a model that is not running"),
    (C, '    return 1 if any(i.severity == "error" for i in issues) else 0', "    return 0"),
    (C, '            out["properties"] = {"wcag": i.wcag, "helpUri": understanding_url(i.wcag)}', "            pass"),
    (C, "    return node if getattr(args, \"whole_window\", False) else content(node)", "    return node"),
    (W, 'matches = [(h, t) for h, t in matches if h != own and "--window" not in t]', "matches = list(matches)"),
    # vision: nothing private leaves
    (V, "        return ipaddress.ip_address(host).is_loopback", "        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback"),
    (V, '    if host == "localhost" or host.endswith(".localhost"):', '    if host.startswith("127.") or host == "localhost":'),
    (V, '    return name.endswith(("-cloud", ":cloud"))', "    return False"),
    (V, "    clean = Image.frombytes(image.mode, image.size, image.tobytes())", "    clean = image"),
    (V, "    image = ImageOps.exif_transpose(image)", "    pass"),
    (V, "opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if is_local(self.url) else urllib.request.build_opener()", "opener = urllib.request.build_opener()"),
    (V, '    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()', '    text = (text or "").strip()'),
    # speech
    (S, "                self.failed = True", "                raise"),
    (S, '        if prefer == "auto" and nvda_running():', "        if False:"),
]


def main(argv: list[str]) -> int:
    chosen = {int(a) for a in argv} if argv else None
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "repo"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".venv", ".git", "__pycache__", ".pytest_cache", "*.egg-info"))
        env = {**os.environ, "PYTHONPATH": str(copy / "src") + os.pathsep + str(copy / "tests"), "PYTHONDONTWRITEBYTECODE": "1"}

        def run_suite() -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"],
                                  cwd=copy, env=env, capture_output=True, timeout=300)

        baseline = run_suite()
        if baseline.returncode != 0:
            print("The test suite fails without any mutant; fix that first:\n" + baseline.stdout.decode(errors="replace")[-2000:])
            return 2
        # The copy must be what is tested, not an installed kanjian elsewhere.
        check = subprocess.run([sys.executable, "-c", "import kanjian; print(kanjian.__file__)"], cwd=copy, env=env, capture_output=True, text=True)
        if not check.stdout.strip().startswith(str(copy)):
            print(f"kanjian is imported from {check.stdout.strip()}, not from the copy; uninstall it or run from a clean venv")
            return 2
        survived = []
        for i, (file, original, mutant) in enumerate(MUTANTS, start=1):
            if chosen and i not in chosen:
                continue
            path = copy / file
            source = path.read_text(encoding="utf-8")
            if source.count(original) != 1:
                print(f"{i:>2}. FOUND {source.count(original)} TIMES in {file}: {original[:60]} (update this list)")
                survived.append(i)
                continue
            path.write_text(source.replace(original, mutant, 1), encoding="utf-8")
            try:
                caught = run_suite().returncode != 0
            except subprocess.TimeoutExpired:
                caught = True  # a hang is a failure too
            path.write_text(source, encoding="utf-8")
            print(f"{i:>2}. {'caught  ' if caught else 'SURVIVED'}  {file}: {original[:70]}", flush=True)
            if not caught:
                survived.append(i)
        total = len(chosen) if chosen else len(MUTANTS)
        print(f"\n{total - len(survived)} of {total} mutants caught" + (f"; survived: {' '.join(map(str, survived))}" if survived else ""))
        return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
