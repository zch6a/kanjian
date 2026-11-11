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

- **这个窗口里有什么？** `kanjian screen` 告诉你窗口标题、焦点在哪、有几个标题、按钮和输入框，再按阅读顺序列出控件，说法和读屏软件一样。它读的是窗口的无障碍树，也就是 NVDA 和讲述人读的那棵树，所以准确，也不需要模型。表格会读成大小、列名和第一行（“Prices，表格，3 行，3 列：Tool，Size，Price；第一行：Spade，Large，25.00”，和 NVDA 一样把表头行算在内），带链接的段落读成一句话，没有名称的控件会附上离它最近的有名称的控件作为参照（“未标注的按钮，在‘收藏’旁边”）。
- **这张图里是什么？** `kanjian describe` 让视觉模型描述一个图片文件、剪贴板里的图片或一个窗口。模型知道自己是在给盲人描述：先说最重要的，文字一字不差地读，不猜测人物。
- **为什么我的用户用不了？** `kanjian audit` 列出让看不见屏幕或不用鼠标的人难以使用的问题：没有名称的控件、没有描述的图片、叫“button”或“IMG_2041.JPG”这种名字的元素、键盘到不了的控件、小于 24×24 有效像素且与其他目标挤在一起的点击目标（WCAG 2.5.8，包括其中的间距例外）。每条问题都注明它不符合的 WCAG 2.2 成功标准（见[检查规则](#检查规则)）。可以输出文本、JSON 或 SARIF。发现错误时退出码为 1，kanjian 读不了窗口时为 2，CI 可以区分这两种情况。（SARIF 里没有文件位置，因为窗口没有文件；它适合 SARIF 查看器，不适合 GitHub 代码扫描。）

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
pip install "kanjian @ git+https://github.com/zch6a/kanjian"
```

如果只想要 `kanjian` 命令、不影响其他 Python 项目，可以用 `uv tool install git+https://github.com/zch6a/kanjian`（或 `pipx install ...`）。在 Windows 上会一并安装 comtypes，kanjian 用它访问 UI Automation 和 Windows 语音。在 macOS 和 Linux 上只有 `kanjian describe` 可用。

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
| Ctrl+Shift+Alt+F | 当前焦点控件的完整信息：名称、角色、值、状态、说明。如果它没有名称、并且配置了视觉模型，会根据它的外观猜测它的用途（只发送这一个控件的图像） |
| Ctrl+Shift+Alt+D | 用视觉模型描述前台窗口 |
| Ctrl+Shift+Alt+X | 停止朗读 |
| Ctrl+Shift+Alt+Q | 退出（在它的终端里按 Ctrl+C 也可以） |

**语音**：NVDA 正在运行时，通过 NVDA 的控制器客户端 DLL（`nvdaControllerClient64.dll`，由 NV Access 提供；kanjian 会在 NVDA 的安装目录里找，也可以用 `KANJIAN_NVDA_DLL` 指定）读出来，用的是你自己设置的语音和语速。如果 NVDA 在运行但找不到这个 DLL，kanjian 会改为打印文字，而不是用第二个声音盖过 NVDA。否则用 Windows 自带的语音（一次性的命令会等它读完再退出）。用 `--say text`（`watch` 以外的默认值）时只打印文字。

视觉模型用 `--vlm-url`、`--vlm-model` 指定，或者用环境变量 `KANJIAN_VLM_URL`、`KANJIAN_VLM_MODEL`、`KANJIAN_VLM_API_KEY`。默认是 `http://localhost:11434/v1` 上的 Ollama，模型 `qwen2.5vl:3b`。

## 检查规则

`kanjian audit` 读取 Windows UI Automation 提供的内容，也就是屏幕阅读器使用的同一棵树。每条问题都会注明它不符合的 WCAG 2.2 成功标准（如果有的话）；在 SARIF 输出里是结果的 `properties.wcag`，并附有 W3C 的说明链接。

| 规则 | 严重程度 | WCAG | 发现什么 |
|---|---|---|---|
| `no-name` | 错误 | 4.1.2 | 控件没有可访问名称（屏幕阅读器只能说“按钮”）；能获得焦点却没有名称的自定义控件、列表或表格记为警告 |
| `image-no-description` | 警告 | 1.1.1 | 图片没有替代文字；它可能是装饰性的，需要人工确认 |
| `meaningless-name` | 图片为错误，其余为警告或提示 | 1.1.1、2.4.4、2.4.6、2.4.9 | 图片名为“IMG_2041.JPG”（F30）、链接名为“点击这里”（如果所在的句子已说明去向，则只是提示）、表格名为“DataGridView” |
| `class-like-name` | 警告 | 2.4.6 | “MyApp.Models.Person”：程序显示的是对象本身，而不是它的文字 |
| `keyboard-unreachable` | 警告 | 2.1.1 | 控件无法获得键盘焦点（工具栏、菜单、列表和选项卡列表用方向键移动，不在此列） |
| `small-target` | 警告；数值框的箭头为提示 | 2.5.8 | 小于 24×24 有效像素、且与其他目标挤在一起的点击目标。已考虑显示缩放，未考虑页面缩放；句子中的链接不算 |
| `duplicate-name` | 用 Tab 键依次经过时为警告，否则为提示 | | 相邻的、角色和名称都相同的控件 |
| `name-includes-role` | 提示 | | “保存按钮”，听起来是“保存按钮，按钮” |
| `heading-skip` | 提示 | | 标题跳级：属于最佳实践，不算不符合 WCAG |

滚动到视野外的元素也会检查名称（屏幕阅读器能读到它们），但不检查尺寸。

**它做不到的事。** 它只能看到名称、角色和状态，看不到外观：颜色对比度、焦点是否可见、重排以及需要人来判断的内容都不检查。对于网页，UIA 是通过浏览器看到页面的，所以结果只是近似：网页内容请用 [axe-core](https://github.com/dequelabs/axe-core) 这类浏览器工具，kanjian 用于桌面程序和 Electron 外壳。任何自动检查都不能代替用屏幕阅读器实际测试。

## 状态

0.1.0，第一个版本。支持 Windows 10 和 11；`kanjian describe` 在 macOS 和 Linux 上也能用。

**已测试：**
- 读取无障碍树、概览和检查：用合成的树测试，用测试自己打开的真实 Win32 窗口测试，也专门做了一个 WinForms 表单和一个 Edge 里的 HTML 页面来手动测试（从不读取测试者自己的窗口）。2 万个元素的网页大约 3 秒读完。
- 检查规则：对照 WCAG 2.2、WCAG2ICT 和 NVDA 的说法核对过，并在上面两个窗口上排查过误报。变异测试脚本（`scripts/mutate.py`）会依次在每条规则里埋一个错误，确认测试能发现它。
- Windows 语音：测试时输出到 WAV 文件。没有音频设备的机器会改为输出文字。
- 视觉客户端：对一个模拟的接口测试，包括发送了什么（尺寸、无元数据、不走代理）。

**作者尚未测试：** 通过 NVDA 朗读（测试机上没有安装 NVDA），以及真实的视觉模型（测试机上也没有）。详见 [POLISH_LOG.md](POLISH_LOG.md)。

## 开发

```bash
uv venv && uv pip install -e . pytest ruff
uv run pytest
```

测试的工作方式、以及如何报告 kanjian 读得不好的窗口，见 [CONTRIBUTING.md](CONTRIBUTING.md)（英文）；每个版本的改动见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[MIT](LICENSE)
