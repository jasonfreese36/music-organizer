# 源码构建、测试与诊断

[项目说明](../README.zh-CN.md) · [English](DEVELOPMENT.md)

## 从源码运行与构建

需要 **Windows 10/11 x64 和 Python 3.14**。Python 依赖固定于 `requirements.txt`；音频工具的下载版本及 SHA-256 固定于 `prepare.py`；原生解密核心的 Go SDK 固定于 `build_platform_audio.py`。

```powershell
git clone https://github.com/jasonfreese36/music-organizer.git
cd music-organizer
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prepare.py
.\.venv\Scripts\python.exe main.py
```

`prepare.py` 下载并校验工具 / Go SDK，运行原生测试、构建 `platformaudio.exe`，收集许可证并生成构建资源。TEA 依赖源码已经 vendored。正常源码构建需要网络。

生成便携版 EXE：

```powershell
.\.venv\Scripts\python.exe build.py --output dist
```

默认使用 Nuitka 4.3.5 与 GCC 的 **`-O3` + LTO** 编译，并检查编译日志确认参数生效。首次构建会下载编译 SDK；Go 原生工具使用 Go 默认优化、移除调试符号，Go 本身没有 `-O3` 开关。可用 `--compiler pyinstaller` 生成原来的字节码打包版，该后备方式不标为 O3 编译。实际处理速度仍受解码、磁盘及在线服务影响。

公开分发前运行 `python source_bundle.py --output dist` 生成第三方对应源码附件；清单与构建/替换方法见 [对应源码说明](CORRESPONDING_SOURCES.md)。

输出包含 EXE、源码 ZIP、说明和校验值。打包不会消除第三方依赖的分发义务；公开分发二进制前请阅读 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

### 测试

集成测试在全新的输出目录生成测试音频，不需要个人曲库或流媒体账号。

```powershell
.\.venv\Scripts\python.exe test_e2e.py --root test-output/e2e
.\.venv\Scripts\python.exe test_advanced.py --root test-output/advanced
.\.venv\Scripts\python.exe test_platforms.py --root test-output/platforms
.\.venv\Scripts\python.exe test_apple.py --root test-output/apple
.\.venv\Scripts\python.exe test_apple_discs.py --root test-output/apple-discs
.\.venv\Scripts\python.exe test_i18n.py
.\.venv\Scripts\python.exe main.py --check-gui --language en --report Gui-English.json
.\.venv\Scripts\python.exe main.py --check-gui --language zh_CN --report Gui-Chinese.json
```

每次使用新的测试目录。可选的真实文件测试材料应放在版本管理之外。联网来源测试独立运行，其结果会受到服务可用性、地区和限速影响。

`--check-gui` 使用临时设置创建实际窗口，检查窗口可见状态、页面切换、设备与归档控件、深浅主题及语言重启命令后退出，不读取个人曲库。编译后的 EXE 也支持相同自检参数。

可选的 GitHub Actions 模板见 [docs/ci/windows-tests.yml](ci/windows-tests.yml)，维护者可将其复制到 `.github/workflows/` 启用托管测试。

### 诊断命令

```powershell
.\.venv\Scripts\python.exe main.py --check-tools --report Tools.json
.\.venv\Scripts\python.exe main.py --preview --offline --source "D:\Music" --dest "D:\Organized" --report Preview.json
.\.venv\Scripts\python.exe main.py --organize --offline --source "D:\Music" --dest "D:\Organized" --report Run.json
```

打包后的 EXE 支持相同参数。使用 `--settings Profile.json` 读取导出的配置。
