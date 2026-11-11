"""Describing images with a vision-language model, for someone who cannot see them.

Any OpenAI-compatible chat endpoint that accepts images works: Ollama (qwen2.5vl, llava, moondream,
gemma3), LM Studio, llama.cpp's server, vLLM. **Only endpoints on this machine are used unless you say
otherwise**: a screen holds mail, passwords half-typed, bank pages. A remote endpoint needs
`allow_remote=True` (`--allow-remote`), and the image is still downscaled and stripped of metadata first.
"""

from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request

PROMPTS = {
    "en": {
        "describe": ("You describe images for a blind person, who will hear your answer read aloud. Start with what the "
                     "image is and its most important content, in one sentence. Then, if there is text, read it exactly "
                     "as written, in reading order. Then add only the details that matter for understanding or acting on "
                     "it. Be concise; no preamble such as 'The image shows'. Say plainly when something is unclear. Do "
                     "not guess who a person is, or their age, ethnicity or feelings, unless it is written in the image."),
        "text": ("Read all the text in this image exactly as written, in reading order, for a blind person. Keep line "
                 "breaks and lists. Do not describe anything else. If there is no text, say 'No text.'"),
        "control": ("This is a cut-out of a user interface control that has no label, for a blind person using a screen "
                    "reader. In at most eight words, say what the control most likely does (for example 'Send message' "
                    "or 'Close window'). Answer with the label only."),
    },
    "zh": {
        "describe": ("你在为一位盲人描述图片，他会听到你的回答。第一句话说明这是什么图片、最重要的内容是什么。"
                     "如果图片里有文字，接着按阅读顺序一字不差地读出来。然后只补充对理解或操作有用的细节。"
                     "简洁，不要用“这张图片显示了”之类的开场。看不清的地方直接说看不清。"
                     "不要猜测人物是谁、年龄、民族或情绪，除非图片里写明了。用简体中文回答。"),
        "text": "把这张图片里的所有文字按阅读顺序一字不差地读出来，给一位盲人听。保留换行和列表。不要描述别的。没有文字就回答“没有文字。”",
        "control": "这是界面上一个没有标签的控件的截图，给使用读屏软件的盲人看。用不超过十个字说明它最可能的作用（例如“发送消息”“关闭窗口”）。只回答标签本身。",
    },
}


class RemoteNotAllowed(PermissionError):
    pass


class VisionError(RuntimeError):
    pass


def is_local(url: str) -> bool:
    """The endpoint is this machine: localhost, or a loopback address. A host name that merely starts
    with "127." (127.attacker.example) is not."""
    import ipaddress

    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def runs_remotely(model: str) -> bool:
    """Ollama's cloud models ("gpt-oss:120b-cloud") are reached through localhost but run on Ollama's servers."""
    name = model.lower()
    return name.endswith(("-cloud", ":cloud"))


def prepare_image(image, max_side: int = 1344) -> bytes:
    """PNG bytes of a PIL image (or image file bytes), at most `max_side` pixels on its long side, with
    no metadata: no EXIF location, no camera, no text chunks. Vision models gain nothing from more
    pixels than they read, and every pixel is data that leaves the screen."""
    from PIL import Image, ImageOps

    if isinstance(image, (bytes, bytearray)):
        try:
            image = Image.open(io.BytesIO(image))
            image.load()
        except (OSError, SyntaxError, ValueError) as e:  # Pillow raises all three for broken files
            raise VisionError("that is not an image kanjian can read (PNG, JPEG, GIF, BMP, WebP and TIFF are)") from e
    image = ImageOps.exif_transpose(image)  # a phone photo upright, as it is shown, before its metadata goes
    image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
    w, h = image.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        image = image.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    clean = Image.frombytes(image.mode, image.size, image.tobytes())  # pixels only: nothing else comes across
    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue()


def clean_reply(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()
    text = re.sub(r"^(the image shows|this image shows|图片显示了?|这张图片显示了?)[,:：，]?\s*", "", text, flags=re.I)
    return text.strip()


class VisionClient:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, *, allow_remote: bool = False,
                 timeout: float = 120.0, lang: str = "en"):
        if not is_local(base_url) and not allow_remote:
            raise RemoteNotAllowed(
                f"{base_url} is not on this machine. kanjian sends screen contents only to a local model unless you "
                "pass --allow-remote: a screenshot can hold mail, messages, passwords and bank details.")
        if runs_remotely(model) and not allow_remote:
            raise RemoteNotAllowed(f"\"{model}\" is a cloud model: Ollama sends its images to its own servers. Use a local "
                                   "model, or pass --allow-remote.")
        if lang not in PROMPTS:
            raise ValueError(f"language must be one of {', '.join(PROMPTS)}")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.api_key, self.timeout, self.lang = model, api_key, timeout, lang
        self.sent: list[int] = []  # bytes of image data sent, per request (shown to the user)

    def check(self) -> None:
        """Is a model server answering at all? Only a TCP connection is opened (nothing is sent), and it
        is done before anything is captured, so a missing model never costs a screenshot."""
        import socket

        parts = urllib.parse.urlsplit(self.url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            socket.create_connection((parts.hostname, port), timeout=3).close()
        except OSError:
            hint = (" Install Ollama (https://ollama.com), run `ollama pull " + self.model + "`, and try again, or pass --vlm-url."
                    if is_local(self.url) else "")
            raise VisionError(f"no vision model is answering at {parts.scheme}://{parts.hostname}:{port}.{hint}") from None

    def describe(self, image, task: str = "describe", context: str = "") -> str:
        """`task`: "describe", "text" (read the text only) or "control" (suggest a label). `context`:
        what kanjian already knows, such as the window title, to help the model."""
        png = prepare_image(image)
        prompt = PROMPTS[self.lang][task] + (f"\n\nContext: {context}" if context else "")
        body = {"model": self.model, "temperature": 0, "stream": False, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
        ]}]}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, json.dumps(body).encode(), headers, method="POST")
        # A local model is reached directly: a configured http_proxy would otherwise see the screenshot.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if is_local(self.url) else urllib.request.build_opener()
        self.sent.append(len(png))
        try:
            with opener.open(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            reply = data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404 and "model" in detail.lower():
                raise VisionError(f"the model \"{self.model}\" is not installed there; with Ollama: ollama pull {self.model}") from e
            raise VisionError(f"the vision model at {self.url} answered {e.code}: {detail}") from e
        except TimeoutError as e:
            raise VisionError(f"the vision model took more than {self.timeout:g} s to answer. The first request after it "
                              "starts includes loading the model, which can take a minute on a CPU: try again") from e
        except (urllib.error.URLError, OSError, KeyError, IndexError, TypeError, ValueError) as e:
            # (a timeout while connecting is wrapped in URLError: the server is not there, which is not slowness)
            raise VisionError(f"the vision model at {self.url} did not answer: {e}") from e
        out = clean_reply(reply if isinstance(reply, str) else "")
        if not out:
            raise VisionError("the vision model returned an empty answer")
        return out
