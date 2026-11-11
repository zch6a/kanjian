"""kanjian command line.

    kanjian screen --after 3          what is in the window in front (switch to it within 3 s)
    kanjian describe photo.jpg        describe an image with a local vision model
    kanjian describe --clipboard      ... the image on the clipboard
    kanjian audit --window Settings   accessibility problems in a window, for developers
    kanjian watch                     global hotkeys: Ctrl+Shift+Alt with S, F, D, X, Q
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import __version__
from .tree import RULES, Issue, Node, audit, count_offscreen, speak_node, summarize, understanding_url

DEFAULT_VLM_URL = "http://localhost:11434/v1"
DEFAULT_VLM_MODEL = "qwen2.5vl:3b"


# ---------------------------------------------------------------- reading windows


class Read:
    """What was read: the window (a browser's page only, unless --whole-window), the focus in it, and
    how complete the reading was."""

    def __init__(self, window: Node, focused: Node | None, focus_elsewhere: bool = False, truncated_at: int | None = None):
        self.window, self.focused, self.focus_elsewhere, self.truncated_at = window, focused, focus_elsewhere, truncated_at
        self.focus_outside_page = False
        page = window.children[0] if len(window.children) == 1 and window.children[0].role == "document" else None
        if focused and page and page.bbox and focused.bbox:
            x, y, w, h = page.bbox
            fx, fy = focused.bbox[0] + focused.bbox[2] / 2, focused.bbox[1] + focused.bbox[3] / 2
            self.focus_outside_page = not (x <= fx <= x + w and y <= fy <= y + h)


def load_tree(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"no such file: {path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{path} is not a tree saved with `kanjian dump` ({e})") from e
    if not isinstance(data, dict) or not isinstance(data.get("window", data), dict) or "role" not in data.get("window", data):
        raise ValueError(f"{path} is not a tree saved with `kanjian dump` (no window in it)")
    return data


def read_window(args) -> Read:
    """The window the arguments name: --tree FILE (a saved tree), --window TITLE, or the window in front
    after --after seconds. Without any of them kanjian would read the terminal it was typed into, so
    it asks which window is meant instead."""
    from .tree import content

    def scoped(node: Node) -> Node:
        return node if getattr(args, "whole_window", False) else content(node)

    if getattr(args, "tree", None):
        data = load_tree(args.tree)
        focused = Node.from_dict(data["focused"]) if data.get("focused") else None
        return Read(scoped(Node.from_dict(data.get("window", data))), focused)
    if not getattr(args, "window", None) and not args.after:
        raise ValueError("which window? Pass --window TITLE, or --after 3 and switch to the window within 3 s "
                         "(reading the window in front now would read this terminal)")
    from .uia import Reader
    from .windows import find_window, foreground_window

    reader = Reader()
    if getattr(args, "window", None):
        hwnd = find_window(args.window)
    else:
        print(f"reading the window in front in {args.after:g} s...", file=sys.stderr)
        time.sleep(args.after)
        hwnd = foreground_window()
    window = reader.window(hwnd)
    truncated = reader.count if reader.truncated else None
    focused = reader.focus_in(hwnd)
    return Read(scoped(window), focused, focus_elsewhere=focused is None, truncated_at=truncated)


# ---------------------------------------------------------------- output


HOME = "https://github.com/zch6a/kanjian"


def sarif(issues: list[Issue], window: str) -> dict:
    """SARIF 2.1.0, for code-scanning tools and editors."""
    levels = {"error": "error", "warning": "warning", "info": "note"}
    rules = sorted({i.rule for i in issues})

    def rule(r: str) -> dict:
        criteria = sorted({i.wcag for i in issues if i.rule == r and i.wcag})
        tags = ["accessibility", *(f"WCAG {sc}" for sc in criteria)]
        return {"id": r, "shortDescription": {"text": RULES.get(r, r)}, "helpUri": f"{HOME}#audit-rules",
                "properties": {"tags": tags if criteria else [*tags, "best-practice"]}}

    def result(i: Issue) -> dict:
        out = {"ruleId": i.rule, "ruleIndex": rules.index(i.rule), "level": levels[i.severity], "message": {"text": i.message},
               "locations": [{"logicalLocations": [{"fullyQualifiedName": i.path, "kind": "element"}]}]}
        if i.wcag:
            out["properties"] = {"wcag": i.wcag, "helpUri": understanding_url(i.wcag)}
        return out

    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "kanjian", "version": __version__, "informationUri": HOME,
                                "rules": [rule(r) for r in rules]}},
            "results": [result(i) for i in issues],
            "properties": {"window": window},
        }],
    }


def print_issues(issues: list[Issue], fmt: str, window: str) -> None:
    if fmt == "json":
        print(json.dumps([i.__dict__ for i in issues], ensure_ascii=False, indent=2))
    elif fmt == "sarif":
        print(json.dumps(sarif(issues, window), ensure_ascii=False, indent=2))
    else:
        if not issues:
            print("No accessibility problems found.")
        for i in issues:
            print(f"{i.severity:7} {i.rule:21} {i.path}\n        {i.message}" + (f" [WCAG {i.wcag}]" if i.wcag else ""))
        errors = sum(1 for i in issues if i.severity == "error")
        if issues:
            print(f"\n{len(issues)} problem(s), {errors} error(s)")


# ---------------------------------------------------------------- commands


def cmd_screen(args) -> int:
    r = read_window(args)
    lines = summarize(r.window, r.focused, lang=args.lang, focus_elsewhere=r.focus_elsewhere, truncated_at=r.truncated_at,
                      focus_outside_page=r.focus_outside_page)
    if args.json:
        print(json.dumps({"window": r.window.to_dict(), "focused": r.focused.to_dict() if r.focused else None}, ensure_ascii=False))
        return 0
    speaker(args).say("\n".join(lines), wait=True)
    return 0


def cmd_audit(args) -> int:
    """Exit 1 when there are errors, 0 when not; 2 means kanjian itself failed (see main)."""
    r = read_window(args)
    if r.truncated_at:
        print(f"kanjian: only the first {r.truncated_at} elements were read, so this audit is partial", file=sys.stderr)
    issues = audit(r.window, min_target=args.min_target)
    hidden = count_offscreen(r.window)
    if hidden and args.format == "text":
        print(f"kanjian: {hidden} element(s) are off screen (scrolled away or hidden): their names were checked, "
              f"their size was not", file=sys.stderr)
    print_issues(issues, args.format, r.window.name)
    return 1 if any(i.severity == "error" for i in issues) else 0


def cmd_dump(args) -> int:
    r = read_window(args)
    data = {"window": r.window.to_dict(), "focused": r.focused.to_dict() if r.focused else None}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"tree written to {args.output}: it holds every name and value in the window; read it before sharing it", file=sys.stderr)
    else:
        print(text)
    return 0


def make_vision(args):
    from .vision import VisionClient

    url = args.vlm_url or os.environ.get("KANJIAN_VLM_URL", DEFAULT_VLM_URL)
    model = args.vlm_model or os.environ.get("KANJIAN_VLM_MODEL", DEFAULT_VLM_MODEL)
    return VisionClient(url, model, os.environ.get("KANJIAN_VLM_API_KEY"), allow_remote=args.allow_remote, lang=args.lang)


def cmd_describe(args) -> int:
    if not (args.image or args.clipboard or args.window or args.after):
        # The window in front now is the terminal this was typed into.
        raise ValueError("what should be described? Give an image file, --clipboard, --window TITLE, "
                         "or --after 3 and switch to the window within 3 s")
    client = make_vision(args)  # refuses a remote endpoint before anything is captured
    if args.image and not Path(args.image).is_file():
        raise RuntimeError(f"no such image: {args.image}")
    client.check()  # and a model that is not running, before a window is captured
    context = ""
    if args.image:
        image = Path(args.image).read_bytes()
    elif args.clipboard:
        from PIL import ImageGrab

        image = ImageGrab.grabclipboard()
        if image is None or isinstance(image, list):
            raise RuntimeError("there is no image on the clipboard")
    else:
        from .windows import capture_window, find_window, foreground_window

        if args.window:
            hwnd = find_window(args.window)
        else:
            if args.after:
                print(f"describing the window in front in {args.after:g} s...", file=sys.stderr)
                time.sleep(args.after)
            hwnd = foreground_window()
        from .windows import window_title

        image = capture_window(hwnd)
        context = "window: " + (window_title(hwnd) or "untitled")
    text = client.describe(image, task=args.task, context=context)
    speaker(args).say(text, wait=True)
    print(f"(sent {client.sent[-1] // 1024} KB of image data to {client.url})", file=sys.stderr)
    return 0


def speaker(args):
    from .speak import Printer, best

    return best(args.say) if args.say != "text" else Printer()


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kanjian", description="Hear what is on the screen.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="examples:\n"
                                       "  kanjian screen --after 3           what is in the window in front\n"
                                       "  kanjian describe photo.jpg         describe an image (local vision model)\n"
                                       "  kanjian audit --window Settings    accessibility problems, for developers\n"
                                       "  kanjian watch                      hotkeys: Ctrl+Shift+Alt with S, F, D, X, Q")
    p.add_argument("--version", action="version", version=f"kanjian {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, window=True):
        sp.add_argument("--lang", choices=["en", "zh"], default="en", help="language of what kanjian says (default en)")
        if window:
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--window", metavar="TITLE", help="a window by (part of) its title, instead of the one in front")
            g.add_argument("--tree", metavar="FILE", help="a tree saved with `kanjian dump`")
            sp.add_argument("--after", type=float, default=0, metavar="SECONDS", help="wait before reading the window in front, to switch to it")
            sp.add_argument("--whole-window", action="store_true", help="in a browser, also its toolbars and address bar (default: the page only)")

    def output(sp):
        sp.add_argument("--say", choices=["auto", "nvda", "voice", "text"], default="text",
                        help="speak: auto (NVDA if running, else a Windows voice), nvda, voice, or text only (default)")

    s = sub.add_parser("screen", help="what is in a window: its controls, read like a screen reader would")
    common(s)
    output(s)
    s.add_argument("--json", action="store_true", help="the raw tree as JSON")

    a = sub.add_parser("audit", help="accessibility problems in a window (exit code 1 if there are errors)")
    common(a)
    a.add_argument("--format", choices=["text", "json", "sarif"], default="text", help="text (default), json, or SARIF 2.1.0 for code scanning")
    a.add_argument("--min-target", type=int, default=24, metavar="PX",
                   help="smallest target size in effective pixels, before display scaling (WCAG 2.5.8: 24)")

    d = sub.add_parser("dump", help="save a window's tree as JSON (for bug reports and tests)")
    common(d)
    d.add_argument("-o", "--output", help="file to write (default: standard output)")

    v = sub.add_parser("describe", help="describe an image, the clipboard, or a window, with a vision model")
    v.add_argument("image", nargs="?", help="an image file")
    v.add_argument("--clipboard", action="store_true", help="the image on the clipboard")
    v.add_argument("--window", metavar="TITLE", help="a picture of a window, by (part of) its title")
    v.add_argument("--after", type=float, default=0, metavar="SECONDS", help="without an image: wait, then capture the window in front")
    v.add_argument("--task", choices=["describe", "text", "control"], default="describe", help="describe it, read its text, or suggest a label")
    v.add_argument("--lang", choices=["en", "zh"], default="en", help="language of the description (default en)")
    v.add_argument("--vlm-url", help=f"OpenAI-compatible endpoint (or KANJIAN_VLM_URL; default {DEFAULT_VLM_URL}, Ollama)")
    v.add_argument("--vlm-model", help=f"vision model (or KANJIAN_VLM_MODEL; default {DEFAULT_VLM_MODEL})")
    v.add_argument("--allow-remote", action="store_true", help="allow an endpoint that is not on this machine (screens hold private data)")
    output(v)

    w = sub.add_parser("watch", help="stay in the background; hotkeys read and describe the window in front")
    w.add_argument("--lang", choices=["en", "zh"], default="en", help="language of what kanjian says (default en)")
    w.add_argument("--vlm-url", help="vision endpoint for D and for guessing labels (as in `kanjian describe`)")
    w.add_argument("--vlm-model", help=f"vision model (default {DEFAULT_VLM_MODEL})")
    w.add_argument("--allow-remote", action="store_true", help="allow a vision endpoint that is not on this machine")
    w.add_argument("--say", choices=["auto", "nvda", "voice", "text"], default="auto",
                   help="auto (default: NVDA if running, else a Windows voice), nvda, voice, or text")
    w.add_argument("--keys", default="ctrl+shift+alt", help="modifiers for the hotkeys (default ctrl+shift+alt; Ctrl+Alt alone is AltGr on many keyboards)")
    return p


def main(argv: list[str] | None = None) -> int:
    """Exit codes: 0 fine; 1 `audit` found errors; 2 kanjian could not do what was asked."""
    args = build_parser().parse_args(argv)
    from .windows import set_dpi_aware

    set_dpi_aware()  # before any window is measured
    if args.command == "describe" and sum(bool(x) for x in (args.image, args.clipboard, args.window)) > 1:
        print("kanjian: give one of: an image file, --clipboard or --window", file=sys.stderr)
        return 2
    # kanjian's own errors are RuntimeError (UIAUnavailable, VisionError) or OSError (RemoteNotAllowed),
    # so the vision module (and urllib, a third of the start-up time) is imported only when it is used.
    try:
        if args.command == "watch":
            from .watch import run

            return run(args)
        return {"screen": cmd_screen, "audit": cmd_audit, "dump": cmd_dump, "describe": cmd_describe}[args.command](args)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"kanjian: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


__all__ = ["main", "build_parser", "sarif", "speak_node"]
