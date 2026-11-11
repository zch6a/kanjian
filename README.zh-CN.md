<div align="center">

# kanjian

**听见屏幕上有什么。** 为盲人和低视力的 Windows 用户描述屏幕与图片，默认只在本机处理；同时给开发这些界面的人一份无障碍检查报告。

<a href="https://github.com/zch6a/kanjian/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zch6a/kanjian/actions/workflows/ci.yml/badge.svg"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white">
<img alt="默认本地处理" src="https://img.shields.io/badge/screen%20contents-stay%20local-2ea44f">
<a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/badge/license-MIT-blue"></a>

[English](README.md) · **简体中文**

</div>

---

*kanjian* 就是“看见”。它回答读屏软件回答得慢的问题：

- **这个窗口里有什么？** `kanjian screen` 告诉你窗口标题、焦点在哪、有几个标题、按钮和输入框，再按阅读顺序列出控件，说法和读屏软件一样。它读的是窗口的无障碍树，也就是 NVDA 和讲述人读的那棵树，所以准确，也不需要模型。
- **这张图里是什么？** `kanjian describe` 让视觉模型描述一个图片文件、剪贴板里的图片或一个窗口。模型知道自己是在给盲人描述：先说最重要的，文字一字不差地读，不猜测人物。
- **为什么我的用户用不了？** `kanjian audit` 列出让盲人难以使用的问题：没有名称的控件、没有描述的图片、叫“button”或“IMG_2041.JPG”这种名字的元素、小于 24 像素且周围没有留出空间的点击目标（WCAG 2.5.8，包括其中的间距例外）、跳级的标题。可以输出文本、JSON 或 SARIF。发现错误时退出码为 1，kanjian 读不了窗口时为 2，CI 可以区分这两种情况。（SARIF 里没有文件位置，因为窗口没有文件；它适合 SARIF 查看器，不适合 GitHub 代码扫描。）

## 隐私

屏幕上有邮件、聊天、没输完的密码和银行页面，所以：

- **无障碍树从不离开这台电脑。** 读它不需要模型。
- **图片只发给本机上的视觉模型**（Ollama、LM Studio、llama.cpp、vLLM），除非你加上 `--allow-remote`。Ollama 的云端模型（名字以 `-cloud` 结尾）算作远程：虽然通过 localhost 访问，实际在 Ollama 的服务器上运行。发送前，图片会转正、长边缩到最多 1344 像素，并去掉所有元数据；kanjian 会告诉你发了多少、发到哪里。
- **只截你指定的那个窗口，而且只截它本身**：由 Windows 为 kanjian 单独渲染这个窗口（`PrintWindow`），所以盖在上面的窗口或通知不会进入画面。最小化的窗口、或者前台是桌面和任务栏时，会直接拒绝，而不是去截图。
- 在确认模型在本机并且正在运行之前，什么都不会截取。
- 即使配置了代理，访问本机模型也会直连。
- 在浏览器里，`screen`、`audit` 和 `dump` 读的是网页本身，不包括工具栏和地址栏（加 `--whole-window` 才包括）。

## 安装

```bash
pip install "kanjian[windows] @ git+https://github.com/zch6a/kanjian"
```

要描述图片，需要一个本地视觉模型，例如用 [Ollama](https://ollama.com)：

```bash
ollama pull qwen2.5vl:3b
```

## 使用

```bash
kanjian screen --after 3              # 3 秒内切换到要读的窗口，听它里面有什么（既没有 --after
                                      # 也没有 --window 时，kanjian 会先问：否则读到的是它自己的终端）
kanjian screen --window 设置 --say auto       # 按标题指定窗口，并读出来（有 NVDA 就用 NVDA，否则用 Windows 语音）
kanjian describe photo.jpg            # 描述一张图片
kanjian describe --clipboard --task text      # 读出剪贴板图片里的文字
kanjian describe --window "登录" --lang zh    # 截取一个窗口并用中文描述
kanjian audit --window "My App" --format sarif > a11y.sarif
kanjian dump --window "My App" -o tree.json   # 保存窗口的树用于报告问题（里面包含窗口里的文字）
kanjian watch                         # 在后台运行，用快捷键操作
```

在 `kanjian watch` 运行时，在任何程序里都可以用（默认是 Ctrl+Shift+Alt，因为在很多键盘布局上单独的 Ctrl+Alt 就是 AltGr；可以用 `--keys win+alt` 等方式修改）：

| 快捷键 | |
|---|---|
| Ctrl+Shift+Alt+S | 前台窗口的概览，一行一行读 |
| Ctrl+Shift+Alt+F | 当前焦点控件的完整信息：名称、角色、值、状态、说明 |
| Ctrl+Shift+Alt+D | 用视觉模型描述前台窗口 |
| Ctrl+Shift+Alt+X | 停止朗读 |
| Ctrl+Shift+Alt+Q | 退出（在它的终端里按 Ctrl+C 也可以） |

**语音**：NVDA 正在运行时，通过 NVDA 的控制器客户端 DLL（`nvdaControllerClient64.dll`，由 NV Access 提供；kanjian 会在 NVDA 的安装目录里找，也可以用 `KANJIAN_NVDA_DLL` 指定）读出来，用的是你自己设置的语音和语速。如果 NVDA 在运行但找不到这个 DLL，kanjian 会改为打印文字，而不是用第二个声音盖过 NVDA。否则用 Windows 自带的语音（一次性的命令会等它读完再退出）。用 `--say text`（`watch` 以外的默认值）时只打印文字。

视觉模型用 `--vlm-url`、`--vlm-model` 指定，或者用环境变量 `KANJIAN_VLM_URL`、`KANJIAN_VLM_MODEL`、`KANJIAN_VLM_API_KEY`。默认是 `http://localhost:11434/v1` 上的 Ollama，模型 `qwen2.5vl:3b`。

## 状态

0.1，开发中。

**已测试：**
- 读取无障碍树、概览和检查：用合成的树测试，也用测试自己打开的一个真实 Win32 窗口测试（不读取用户的任何内容）。
- Windows 语音：测试时输出到 WAV 文件。
- 视觉客户端：对一个模拟的接口测试。

**作者尚未测试：** 通过 NVDA 朗读（测试机上没有安装 NVDA），以及真实的视觉模型（测试机上也没有）。详见 [POLISH_LOG.md](POLISH_LOG.md)。

## 开发

```bash
uv venv && uv pip install -e ".[windows]" pytest ruff
uv run pytest
```

## 许可证

[MIT](LICENSE)
