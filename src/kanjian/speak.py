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

    def say(self, text: str, interrupt: bool = True, wait: bool = False) -> None:
        print(text, file=self.stream or sys.stdout, flush=True)

    def stop(self) -> None:
        pass


class NVDA:
    """NVDA's controller client: speakText / cancelSpeech, only while NVDA is running."""

    name = "NVDA"

    def __init__(self, lib):
        self.lib = lib
        if self.lib.nvdaController_testIfRunning() != 0:
            raise OSError("NVDA is not running")

    def say(self, text: str, interrupt: bool = True, wait: bool = False) -> None:
        # NVDA speaks on its own, after kanjian has gone, so there is nothing to wait for.
        if interrupt:
            self.lib.nvdaController_cancelSpeech()
        if self.lib.nvdaController_speakText(ctypes.c_wchar_p(text)) != 0:
            raise OSError("NVDA did not accept the text")

    def stop(self) -> None:
        self.lib.nvdaController_cancelSpeech()

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

    def say(self, text: str, interrupt: bool = True, wait: bool = False) -> None:
        """`wait`: return only when it has been said. A one-shot command must wait, or the process
        exits and the voice with it: kanjian screen used to say nothing at all."""
        flags = (self.PURGE if interrupt else 0) | (0 if self.stream else self.ASYNC)
        self.voice.Speak(text, flags)
        if wait and not self.stream:
            self.voice.WaitUntilDone(-1)

    def stop(self) -> None:
        self.voice.Speak("", self.ASYNC | self.PURGE)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.Close()
            self.stream = None


def nvda_running() -> bool:
    if sys.platform != "win32":
        return False
    import subprocess

    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq nvda.exe", "/NH"], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "nvda.exe" in out.lower()


def best(prefer: str = "auto", warn=None):
    """`prefer`: "auto" (NVDA if running, else a Windows voice, else text), "nvda", "voice" or "text".
    With NVDA running but its controller DLL missing, "auto" prints rather than speak over NVDA in a
    second voice; `warn` hears why."""
    warn = warn or (lambda message: print(f"kanjian: {message}", file=sys.stderr))
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
        if prefer == "auto" and nvda_running():
            warn("NVDA is running but its controller DLL was not found (set KANJIAN_NVDA_DLL), so kanjian prints instead "
                 "of talking over NVDA in a second voice")
            return Printer()
    try:
        return SAPI()
    except Exception as e:  # noqa: BLE001 - no voices, no comtypes
        if prefer == "voice":
            raise OSError(f"no Windows voice is available: {e}") from e
        return Printer()
