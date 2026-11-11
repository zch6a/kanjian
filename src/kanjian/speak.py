"""Saying things out loud: through the user's screen reader when it is running, so that kanjian speaks
in the voice, speed and language they chose; otherwise through Windows' own voices; otherwise as text.

NVDA is reached through its controller client DLL (`nvdaControllerClient64.dll`, published by NV Access
with NVDA's releases); kanjian looks for it in NVDA's program folder and next to itself, or where
`KANJIAN_NVDA_DLL` points.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


class Printer:
    name = "text"

    def __init__(self, stream=None):
        self.stream = stream

    def say(self, text: str, interrupt: bool = True) -> None:
        print(text, file=self.stream or sys.stdout, flush=True)


class NVDA:
    """NVDA's controller client: speakText / cancelSpeech, only while NVDA is running."""

    name = "NVDA"

    def __init__(self, lib):
        self.lib = lib
        if self.lib.nvdaController_testIfRunning() != 0:
            raise OSError("NVDA is not running")

    def say(self, text: str, interrupt: bool = True) -> None:
        if interrupt:
            self.lib.nvdaController_cancelSpeech()
        if self.lib.nvdaController_speakText(ctypes.c_wchar_p(text)) != 0:
            raise OSError("NVDA did not accept the text")

    @staticmethod
    def find() -> Path | None:
        candidates = [os.environ.get("KANJIAN_NVDA_DLL", "")]
        for base in (os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("PROGRAMFILES", "")):
            if base:
                candidates.append(os.path.join(base, "NVDA", "nvdaControllerClient64.dll" if sys.maxsize > 2**32 else "nvdaControllerClient32.dll"))
        candidates.append(str(Path(__file__).with_name("nvdaControllerClient64.dll")))
        return next((Path(c) for c in candidates if c and Path(c).is_file()), None)


class SAPI:
    """Windows' own text-to-speech (the voices Narrator uses). `to_file` writes a WAV instead of speaking."""

    name = "Windows voice"
    ASYNC, PURGE = 1, 2

    def __init__(self, to_file: str | None = None):
        import comtypes.client

        self.voice = comtypes.client.CreateObject("SAPI.SpVoice")
        self.stream = None
        if to_file:
            self.stream = comtypes.client.CreateObject("SAPI.SpFileStream")
            self.stream.Open(str(to_file), 3, False)  # SSFMCreateForWrite
            self.voice.AudioOutputStream = self.stream

    def say(self, text: str, interrupt: bool = True) -> None:
        flags = (self.PURGE if interrupt else 0) | (0 if self.stream else self.ASYNC)
        self.voice.Speak(text, flags)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.Close()
            self.stream = None


def best(prefer: str = "auto"):
    """`prefer`: "auto" (NVDA if running, else a Windows voice, else text), "nvda", "voice" or "text"."""
    if prefer == "text" or sys.platform != "win32":
        return Printer()
    if prefer in ("auto", "nvda"):
        dll = NVDA.find()
        if dll:
            try:
                return NVDA(ctypes.WinDLL(str(dll)))
            except OSError:
                if prefer == "nvda":
                    raise
        elif prefer == "nvda":
            raise OSError("NVDA's controller client DLL was not found: set KANJIAN_NVDA_DLL to nvdaControllerClient64.dll")
    try:
        return SAPI()
    except Exception:  # noqa: BLE001 - no voices, no comtypes
        return Printer()
