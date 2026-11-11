import io
import sys
import wave

import pytest

from kanjian.speak import NVDA, Printer, best


class FakeNVDA:
    def __init__(self, running=True):
        self.running, self.spoken, self.cancelled = running, [], 0

    def nvdaController_testIfRunning(self):
        return 0 if self.running else 1

    def nvdaController_cancelSpeech(self):
        self.cancelled += 1
        return 0

    def nvdaController_speakText(self, text):
        self.spoken.append(text.value)
        return 0


def test_nvda_speaks_and_interrupts():
    lib = FakeNVDA()
    n = NVDA(lib)
    n.say("Save, button")
    n.say("more", interrupt=False)
    assert lib.spoken == ["Save, button", "more"] and lib.cancelled == 1


def test_nvda_not_running_is_refused():
    with pytest.raises(OSError, match="not running"):
        NVDA(FakeNVDA(running=False))


def test_printer_and_text_choice():
    buf = io.StringIO()
    Printer(buf).say("hello")
    assert buf.getvalue() == "hello\n"
    assert isinstance(best("text"), Printer)


def test_nvda_requested_but_not_installed(monkeypatch):
    monkeypatch.setattr(NVDA, "find", staticmethod(lambda: None))
    if sys.platform == "win32":
        with pytest.raises(OSError, match="KANJIAN_NVDA_DLL"):
            best("nvda")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows voices")
def test_windows_voice_to_a_file_makes_no_sound(tmp_path):
    pytest.importorskip("comtypes")
    from kanjian.speak import SAPI

    out = tmp_path / "said.wav"
    s = SAPI(to_file=str(out))
    s.say("Save, button")
    s.close()
    with wave.open(str(out)) as w:
        assert w.getnframes() > 1000  # real speech, written instead of played


def test_auto_does_not_talk_over_nvda_when_its_dll_is_missing(monkeypatch):
    import kanjian.speak as speak

    monkeypatch.setattr(speak.NVDA, "find", staticmethod(lambda: None))
    monkeypatch.setattr(speak, "nvda_running", lambda: True)
    warnings = []
    if sys.platform == "win32":
        assert isinstance(speak.best("auto", warn=warnings.append), Printer)
        assert "second voice" in warnings[0]


def test_voice_requested_but_unavailable_is_an_error(monkeypatch):
    import kanjian.speak as speak

    def broken(*a, **k):
        raise RuntimeError("no voices")

    monkeypatch.setattr(speak, "SAPI", broken)
    monkeypatch.setattr(speak.NVDA, "find", staticmethod(lambda: None))
    if sys.platform == "win32":
        with pytest.raises(OSError, match="no Windows voice"):
            speak.best("voice")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows voices")
def test_a_one_shot_command_waits_until_the_voice_has_finished():
    pytest.importorskip("comtypes")
    import time

    from kanjian.speak import SAPI

    s = SAPI()
    s.voice.Volume = 0  # silent: this test must not make a sound
    t0 = time.perf_counter()
    try:
        s.say("one two three four five six seven eight nine ten", wait=True)
    except OSError as e:  # CI runners have no audio output device
        pytest.skip(str(e))
    assert time.perf_counter() - t0 > 1.0, "returned before the sentence was spoken"
    assert s.voice.Status.RunningState == 1  # SRSEDone


def test_when_speaking_fails_the_text_is_printed_once_with_the_reason(capsys):
    from kanjian.speak import Fallback

    class Broken:
        name = "Windows voice"

        def say(self, text, interrupt=True, wait=False):
            raise OSError("Windows could not speak (0x8004503a); is there an audio output device?")

        def stop(self):
            raise OSError("no device")

    warnings = []
    f = Fallback(Broken(), warn=warnings.append)
    f.say("Save, button")
    f.say("Cancel, button")
    f.stop()
    assert capsys.readouterr().out == "Save, button\nCancel, button\n"
    assert len(warnings) == 1 and "audio output device" in warnings[0]
