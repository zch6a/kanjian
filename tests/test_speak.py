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
