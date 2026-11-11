"""kanjian command line.

    kanjian screen --after 3          what is in the window in front (switch to it within 3 s)
    kanjian describe photo.jpg        describe an image with a local vision model
    kanjian describe --clipboard      ... the image on the clipboard
    kanjian audit --window Settings   accessibility problems in a window, for developers
    kanjian watch                     global hotkeys: Ctrl+Alt+S, Ctrl+Alt+D, Ctrl+Alt+F
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import __version__
from .tree import Issue, Node, audit, speak_node, summarize

DEFAULT_VLM_URL = "http://localhost:11434/v1"
DEFAULT_VLM_MODEL = "qwen2.5vl:3b"


# ---------------------------------------------------------------- reading windows


def read_window(args) -> tuple[Node, Node | None]:
    """The window the arguments name: --tree FILE (a saved tree), --window TITLE, or the foreground
    window after --after seconds."""
    if getattr(args, "tree", None):
        data = json.loads(Path(args.tree).read_text(encoding="utf-8"))
        return Node.from_dict(data.get("window", data)), Node.from_dict(data["focused"]) if data.get("focused") else None
    from .uia import Reader

    reader = Reader()
    if getattr(args, "window", None):
        from .windows import find_window

        return reader.window(find_window(args.window)), None
    if args.after:
        print(f"reading the window in front in {args.after:g} s...", file=sys.stderr)
        time.sleep(args.after)
    return reader.foreground()


# ---------------------------------------------------------------- output


def sarif(issues: list[Issue], window: str) -> dict:
    """SARIF 2.1.0, for code-scanning tools and editors."""
    levels = {"error": "error", "warning": "warning", "info": "note"}
    rules = sorted({i.rule for i in issues})
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "kanjian", "version": __version__, "informationUri": "https://github.com/zch6a/kanjian",
                                "rules": [{"id": r} for r in rules]}},
            "results": [{"ruleId": i.rule, "level": levels[i.severity], "message": {"text": i.message},
                         "locations": [{"logicalLocations": [{"fullyQualifiedName": i.path, "kind": "element"}]}]} for i in issues],
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
            print(f"{i.severity:7} {i.rule:21} {i.path}\n        {i.message}")
        errors = sum(1 for i in issues if i.severity == "error")
        if issues:
            print(f"\n{len(issues)} problem(s), {errors} error(s)")


# ---------------------------------------------------------------- commands


def cmd_screen(args) -> int:
    window, focused = read_window(args)
    lines = summarize(window, focused, lang=args.lang)
    if args.json:
        print(json.dumps({"window": window.to_dict(), "focused": focused.to_dict() if focused else None}, ensure_ascii=False))
        return 0
    out = speaker(args)
    out.say("\n".join(lines))
    return 0


def cmd_audit(args) -> int:
    window, _ = read_window(args)
    issues = audit(window, min_target=args.min_target)
    print_issues(issues, args.format, window.name)
    return 1 if any(i.severity == "error" for i in issues) else 0


def cmd_dump(args) -> int:
    window, focused = read_window(args)
    data = {"window": window.to_dict(), "focused": focused.to_dict() if focused else None}
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
    client = make_vision(args)  # refuses a remote endpoint before anything is captured
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
        image = capture_window(hwnd)
        try:
            from .uia import Reader

            context = "window: " + (Reader(max_nodes=1).window(hwnd).name or "untitled")
        except Exception:  # noqa: BLE001 - context is only a help
            context = ""
    text = client.describe(image, task=args.task, context=context)
    speaker(args).say(text)
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
                                       "  kanjian watch                      hotkeys: Ctrl+Alt+S, D, F")
    p.add_argument("--version", action="version", version=f"kanjian {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, window=True):
        sp.add_argument("--lang", choices=["en", "zh"], default="en", help="language of what kanjian says (default en)")
        if window:
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--window", metavar="TITLE", help="a window by (part of) its title, instead of the one in front")
            g.add_argument("--tree", metavar="FILE", help="a tree saved with `kanjian dump`")
            sp.add_argument("--after", type=float, default=0, metavar="SECONDS", help="wait before reading the window in front, to switch to it")

    def output(sp):
        sp.add_argument("--say", choices=["auto", "nvda", "voice", "text"], default="text",
                        help="speak: auto (NVDA if running, else a Windows voice), nvda, voice, or text only (default)")

    s = sub.add_parser("screen", help="what is in a window: its controls, read like a screen reader would")
    common(s)
    output(s)
    s.add_argument("--json", action="store_true", help="the raw tree as JSON")

    a = sub.add_parser("audit", help="accessibility problems in a window (exit code 1 if there are errors)")
    common(a)
    a.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    a.add_argument("--min-target", type=int, default=24, help="smallest target size in px (WCAG 2.5.8: 24)")

    d = sub.add_parser("dump", help="save a window's tree as JSON (for bug reports and tests)")
    common(d)
    d.add_argument("-o", "--output", help="file to write (default: standard output)")

    v = sub.add_parser("describe", help="describe an image, the clipboard, or a window, with a vision model")
    v.add_argument("image", nargs="?", help="an image file")
    v.add_argument("--clipboard", action="store_true", help="the image on the clipboard")
    v.add_argument("--window", metavar="TITLE", help="a picture of a window, by (part of) its title")
    v.add_argument("--after", type=float, default=0, metavar="SECONDS", help="without an image: wait, then capture the window in front")
    v.add_argument("--task", choices=["describe", "text", "control"], default="describe", help="describe it, read its text, or suggest a label")
    v.add_argument("--lang", choices=["en", "zh"], default="en")
    v.add_argument("--vlm-url", help=f"OpenAI-compatible endpoint (or KANJIAN_VLM_URL; default {DEFAULT_VLM_URL}, Ollama)")
    v.add_argument("--vlm-model", help=f"vision model (or KANJIAN_VLM_MODEL; default {DEFAULT_VLM_MODEL})")
    v.add_argument("--allow-remote", action="store_true", help="allow an endpoint that is not on this machine (screens hold private data)")
    output(v)

    w = sub.add_parser("watch", help="stay in the background; hotkeys read and describe the window in front")
    w.add_argument("--lang", choices=["en", "zh"], default="en")
    w.add_argument("--vlm-url")
    w.add_argument("--vlm-model")
    w.add_argument("--allow-remote", action="store_true")
    w.add_argument("--say", choices=["auto", "nvda", "voice", "text"], default="auto")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "describe" and sum(bool(x) for x in (args.image, args.clipboard, args.window)) > 1:
        print("kanjian: give one of: an image file, --clipboard or --window", file=sys.stderr)
        return 2
    from .uia import UIAUnavailable
    from .vision import RemoteNotAllowed, VisionError

    try:
        if args.command == "watch":
            from .watch import run

            return run(args)
        return {"screen": cmd_screen, "audit": cmd_audit, "dump": cmd_dump, "describe": cmd_describe}[args.command](args)
    except (RemoteNotAllowed, VisionError, UIAUnavailable, RuntimeError, OSError, ValueError) as e:
        print(f"kanjian: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


__all__ = ["main", "build_parser", "sarif", "speak_node"]
