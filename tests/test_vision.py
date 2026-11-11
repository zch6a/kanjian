import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image, PngImagePlugin

from kanjian.vision import RemoteNotAllowed, VisionClient, VisionError, clean_reply, is_local, prepare_image


class FakeVLM:
    """A local OpenAI-compatible endpoint that records what it is sent."""

    def __init__(self, reply="A login form with two fields.", status=200, body=None):
        self.reply, self.requests, self.status, self.body = reply, [], status, body
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                fake.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                data = fake.body or json.dumps({"choices": [{"message": {"content": fake.reply}}]}).encode()
                self.send_response(fake.status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def vlm():
    f = FakeVLM()
    yield f
    f.close()


def picture(w=2000, h=1000):
    img = Image.new("RGB", (w, h), (240, 240, 240))
    for x in range(min(100, w - 1), min(300, w)):
        for y in range(min(100, h - 1), min(140, h)):
            img.putpixel((x, y), (20, 20, 20))
    return img


def test_only_local_endpoints_unless_allowed():
    assert is_local("http://localhost:11434/v1") and is_local("http://127.0.0.1:1234/v1") and is_local("http://[::1]:8080/v1")
    assert not is_local("https://api.example.com/v1") and not is_local("http://192.168.1.5:11434/v1")
    with pytest.raises(RemoteNotAllowed, match="--allow-remote"):
        VisionClient("https://api.example.com/v1", "m")
    VisionClient("https://api.example.com/v1", "m", allow_remote=True)  # allowed when asked for


def test_the_image_is_downscaled_and_carries_no_metadata():
    img = picture(4000, 2000)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "someone")
    raw = io.BytesIO()
    img.save(raw, format="PNG", pnginfo=meta)
    out = Image.open(io.BytesIO(prepare_image(raw.getvalue())))
    assert max(out.size) == 1344 and out.size == (1344, 672)
    assert not out.info.get("Author") and "exif" not in out.info
    small = Image.open(io.BytesIO(prepare_image(picture(400, 300))))
    assert small.size == (400, 300)  # never enlarged


def test_describe_sends_the_prompt_and_image_and_cleans_the_answer(vlm):
    vlm.reply = "<think>looking</think>The image shows: A login form with two fields."
    c = VisionClient(vlm.url, "qwen2.5vl:3b")
    assert c.describe(picture(), context="window: Sign in") == "A login form with two fields."
    body = vlm.requests[0]
    assert body["model"] == "qwen2.5vl:3b" and body["temperature"] == 0
    parts = body["messages"][0]["content"]
    assert "blind person" in parts[0]["text"] and "Context: window: Sign in" in parts[0]["text"]
    png = base64.b64decode(parts[1]["image_url"]["url"].split(",", 1)[1])
    assert Image.open(io.BytesIO(png)).size == (1344, 672)
    assert c.sent == [len(png)]


def test_tasks_and_languages(vlm):
    zh = VisionClient(vlm.url, "m", lang="zh")
    zh.describe(picture(), task="text")
    assert "一字不差" in vlm.requests[-1]["messages"][0]["content"][0]["text"]
    VisionClient(vlm.url, "m").describe(picture(), task="control")
    assert "eight words" in vlm.requests[-1]["messages"][0]["content"][0]["text"]
    with pytest.raises(ValueError):
        VisionClient(vlm.url, "m", lang="fr")


def test_a_local_model_is_reached_directly_even_with_a_proxy(vlm, monkeypatch):
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    assert VisionClient(vlm.url, "m").describe(picture())


def test_failures_are_clear():
    with pytest.raises(VisionError, match="did not answer"):
        VisionClient("http://127.0.0.1:9/v1", "m", timeout=2).describe(picture(200, 100))
    empty = FakeVLM(reply="<think>hmm</think>")
    try:
        with pytest.raises(VisionError, match="empty"):
            VisionClient(empty.url, "m").describe(picture(200, 100))
    finally:
        empty.close()


def test_clean_reply():
    assert clean_reply("这张图片显示了：一个登录表单") == "一个登录表单"
    assert clean_reply("A chart.") == "A chart."


def test_no_model_running_says_what_to_install():
    c = VisionClient("http://127.0.0.1:9/v1", "qwen2.5vl:3b")
    with pytest.raises(VisionError, match="ollama pull qwen2.5vl:3b"):
        c.check()


def test_a_model_that_is_not_pulled_says_so():
    fake = FakeVLM(status=404, body=b'{"error":{"message":"model \\"llava\\" not found, try pulling it first"}}')
    try:
        with pytest.raises(VisionError, match="ollama pull llava"):
            VisionClient(fake.url, "llava").describe(picture(64, 48))
    finally:
        fake.close()

def test_a_name_that_only_looks_local_is_not():
    assert not is_local("http://127.attacker.example/v1") and not is_local("http://localhost.attacker.example/v1")
    assert is_local("http://127.0.0.5:11434/v1") and is_local("http://app.localhost:8080/v1")
    with pytest.raises(RemoteNotAllowed):
        VisionClient("http://127.attacker.example/v1", "m")


def test_ollama_cloud_models_count_as_remote():
    with pytest.raises(RemoteNotAllowed, match="cloud model"):
        VisionClient("http://localhost:11434/v1", "qwen3-vl:235b-cloud")
    VisionClient("http://localhost:11434/v1", "qwen3-vl:235b-cloud", allow_remote=True)


def test_a_phone_photo_is_sent_upright():
    img = Image.new("RGB", (400, 200), (0, 0, 0))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees to display
    raw = io.BytesIO()
    img.save(raw, format="JPEG", exif=exif)
    out = Image.open(io.BytesIO(prepare_image(raw.getvalue())))
    assert out.size == (200, 400)


def test_a_file_that_is_not_an_image_is_said_plainly():
    with pytest.raises(VisionError, match="not an image kanjian can read"):
        prepare_image(b"%PDF-1.7 this is not a picture")


def test_a_model_slow_to_answer_is_told_apart_from_a_missing_one():
    import time

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(2)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(VisionError, match="loading the model"):
            VisionClient(f"http://127.0.0.1:{server.server_port}/v1", "m", timeout=0.5).describe(picture(64, 48))
    finally:
        server.shutdown()
