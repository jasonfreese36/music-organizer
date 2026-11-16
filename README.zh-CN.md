<div align="center">

# Music Organizer · 音乐整理工具

**将混杂的音乐目录，整理成结构统一、资料清晰的曲库。**

[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows)](#开始使用)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](#从源码运行与构建)
[![源码协议](https://img.shields.io/badge/自有源码-MIT-6556DC)](LICENSE)

[English](README.md) · **简体中文**

</div>

面向 Windows 的桌面音乐整理应用，处理散装音轨、无损专辑、DSD/SACD 原盘及已支持的加密下载格式。先只读扫描、核对资料，再写入独立的目标曲库，保留源文件。

**v1.4.0** 新增 iPod、iPhone/iPad 输出预设、原盘独立归档和英文界面。语言可在“高级设置 → 外观”中选择，保存并重启后生效。首次打开仍使用 v1.1 的默认整理设置。

从 [Releases](https://github.com/jasonfreese36/music-organizer/releases) 下载便携版 [Windows EXE](https://github.com/jasonfreese36/music-organizer/releases/latest/download/MusicOrganizer.exe)。发布附件同时提供对应应用源码、第三方组件源码与校验值。自有源码采用 MIT；完整应用仍须遵守 GPL、LGPL 等第三方组件的分发条件，见[开源协议与商业使用](#开源协议与商业使用)。

## 主要功能

- **只读扫描与预览：**检查格式、标签和封面，整理前可更正发行信息；源目录与目标目录必须独立。
- **统一播放库：**默认输出 FLAC、MP3、AAC（使用 `.m4a` 容器）。已有 MP3/AAC 通常保留编码，避免不必要的有损重编码。
- **保留原盘与版本：**备份 DSD/SACD、CUE 整轨和加密原件，按采样位置分轨；明确标识的 LP rip、其他录音或母带分别保留。
- **发行资料与内嵌封面：**联网检索 MusicBrainz、Cover Art Archive、Apple iTunes，比较发行结果，分别选择标签和封面，测试来源连通性。
- **可视化高级设置：**浅色、深色、跟随系统，五种主题色；目录和文件名预设、采样率及编码参数、点选式条件转换规则。
- **校验、续跑与报告：**按音频内容确认重复，保留来源记录；支持停止、重新运行及 CSV/JSON 报告。

## 开始使用

苹果设备用户可先在“**高级设置 → 苹果设备**”选择 iPod 或 iPhone/iPad，再选择独立的空目标目录。设备预设将不兼容的 FLAC、WAV、DSD、高采样率、多声道等转换为兼容音轨，封面内嵌为 JPEG，目标只含 MP3/M4A；报告、索引、播放列表放在旁边的 `<目标名> - Records` 文件夹。

| 设备预设 | 新编码音轨 | 保守兼容限制 |
|---|---|---|
| iPod 通用 / shuffle | MP3 256 kbps；节省空间为 192 kbps | 单声道/立体声，32/44.1/48 kHz，ID3v2.3 |
| iPod classic / nano | AAC-LC；无损选项为 ALAC | ALAC 最高 16-bit / 44.1 kHz，单声道/立体声 |
| iPhone / iPad | AAC-LC；无损选项为 ALAC | ALAC 最高 24-bit / 48 kHz，单声道/立体声 |

兼容的 MP3/AAC 可保留原编码；节省空间会重新编码高于 192 kbps 的有损音轨。设备限制优先于自定义规则。iPod 封面最大 600 像素，iOS 最大 1000 像素。目标已有不兼容文件时会拒绝运行，请选新目录，程序不会删除已有内容。

**原盘处理**默认“不另存原盘”。可选择“**另存到独立文件夹**”，指定与源目录、导入目录、报告目录互不包含的归档位置。DSD/SACD ISO、CUE 整轨、平台加密原件和普通音频原件都会复制并校验；图片附页遵循原有备份开关。归档路径不会写入可复用的导出配置。两种选项均保留源文件。

将整理后的 Albums 导入 Apple Music/iTunes，再通过 Apple Devices/iTunes 同步。程序负责准备文件，不直接写入 iPod 数据库。不同代际请核对 [iPod classic 规格](https://support.apple.com/en-ca/112601)、[nano 规格](https://support.apple.com/en-is/112039)和 [Apple 无损说明](https://support.apple.com/en-euro/118295)。另见 [Windows 导入](https://support.apple.com/en-mo/guide/music-windows/mus3081/windows)及[设备同步说明](https://support.apple.com/en-gb/guide/devices-windows/mchlbf6a1fab/1.5/windows/10)。本版本验证了生成样本和编译 EXE，尚未连接实体设备验证同步。

本仓库提供源码、原生解密工具源码、许可说明及构建脚本。运行方法见[从源码运行与构建](#从源码运行与构建)。打包后可得到包含 Python 运行时及音频工具的便携版 `MusicOrganizer.exe`。

1. 选择音乐源目录和一个**独立的目标目录**。
2. 点击“**只读扫描**”，检查文件，按需更正专辑信息或指定封面。
3. 点击“**开始整理**”，成功处理的音轨进入目标曲库，源文件保留。
4. 查看 `Needs Review/Review.csv` 和 `Library Records/Latest Run.json`。修正不确定项目后，重新整理到同一受管理目标库即可继续补全。

自动联网可关闭。在线服务不一定收录所有发行版本或封面；匹配不足时会记录问题，不将推测写成已核实的发行资料。

### 默认目录结构

```text
Organized/
├── Albums/
│   └── Artist/
│       ├── 2024 - Album/
│       │   ├── 01 - Song.flac
│       │   └── cover.jpg
│       └── 2024 - Album [Vinyl Rip]/
├── Disc Archives/
│   ├── DSD Originals/
│   ├── Cue Images/
│   ├── NCM Originals/
│   └── Platform Originals/
├── Needs Review/
├── Library Records/
└── Playlists/
```

顶层目录为英文，艺术家、专辑和曲名保留原语言。单曲与恢复的音频按发行资料归入 `Albums`。

## 平台加密音频支持范围

程序先识别已知容器并备份原件，再在本机解密、校验，继续进入常规整理流程。**支持特定加密方案，不代表兼容各平台全部历史和最新文件。**

| 平台 | 已实现方案 | 密钥要求与限制 |
|---|---|---|
| 网易云音乐 | NCM、受支持的旧 UC 缓存 | NCM 使用内置 ncmdump。 |
| QQ 音乐 | QMC 静态 / Map / RC4、内嵌 EKey / QTag、TM 头部恢复 | STag、musicex 等外置密钥版本需要对应的本地 EKey 或原始密钥。 |
| 酷狗音乐 | 旧 KGM / KGMA / VPR、crypto v3、KGG / crypto v5 | v5 需要对应 EKey，可导入用户选择的 KGMusicV3.db 或 kgg.keys。 |
| 酷我音乐 | 旧 KWM / KWMA | 新加密变体可能不兼容。 |
| 咪咕音乐 | MG3D | 部分旧 WAV 可自动恢复，其他受支持文件需要 fileKey / 掩码；**暂不支持 MGM**。 |

“**高级设置 → 平台音频**”中可查看支持状态、导入本地密钥、设置并行数量及完整解码校验。缺密钥、密钥不匹配、文件损坏、版本未支持会分别记录；单个失败项目不会阻止其他文件处理。

仅读取用户明确选择的数据库，数据库解密在临时副本上执行，不修改原数据库。程序不登录流媒体账号，也不向平台获取下载权限或歌曲密钥。

## 标签和封面数据源

| 来源 | 标签 | 封面 |
|---|---|---|
| MusicBrainz | 发行、艺术家、曲目、厂牌、版本等 | 为 Cover Art Archive 定位发行 |
| Cover Art Archive | — | 对应 MusicBrainz 发行的专辑图片 |
| Apple iTunes | 数字发行与曲目资料 | 专辑图片 |

可分别启用标签与封面来源、设定优先顺序、测试实际连通性。手动检索时可比较不同发行，并分别选用标签和封面。自动处理优先使用现有本地标签及封面。

封面内嵌到输出音轨中，也可设置另存 `cover.jpg` / `cover.png`。清理平台标识字段，保留有效的发行信息。

## 高级设置

初次打开使用保守默认值：浅色紫色外观、自定义规则为空、无损生成 FLAC、已有 MP3/AAC 保留编码。新增选项均集中在高级设置中，按需调整。

- **外观：**浅色、深色、跟随系统；紫、蓝、绿、粉、橙五种主题色。
- **目录与命名：**选择预设、插入资料字段、预览目标路径；支持轨号、歌名或艺术家在前，以及多碟目录、前缀或平铺。
- **音频转换：**FLAC / MP3 / AAC、采样率上限或固定值、位深、声道、SWResample / SoXR、抖动和编码参数。
- **条件规则：**点选格式、码率、采样率、位深、声道、大小或是否无损等条件，选择“全部 / 任一满足”，启停、复制和排序；采用第一条命中的启用规则。
- **配置和预览：**导入 / 导出配置，导出只读路径与转换计划 CSV。配置不包含源 / 目标目录和媒体密钥。

例如“所有高于 256 kbps 的 AAC 转 MP3”：添加“AAC 格式”条件，再添加“码率 > 256 kbps”，选择“全部满足”，输出选择 MP3。通过界面点选，无需编写代码。有损格式之间的转换会产生再次有损，源文件保留。

更多选项见[完整中文使用手册](docs/USER_GUIDE.zh-CN.md)。

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

公开分发前运行 `python source_bundle.py --output dist` 生成第三方对应源码附件；清单与构建/替换方法见 [对应源码说明](docs/CORRESPONDING_SOURCES.md)。

输出包含 EXE、源码 ZIP、说明和校验值。打包不会消除第三方依赖的分发义务；公开分发二进制前请阅读 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

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

可选的 GitHub Actions 模板见 [docs/ci/windows-tests.yml](docs/ci/windows-tests.yml)，维护者可将其复制到 `.github/workflows/` 启用托管测试。

### 诊断命令

```powershell
.\.venv\Scripts\python.exe main.py --check-tools --report Tools.json
.\.venv\Scripts\python.exe main.py --preview --offline --source "D:\Music" --dest "D:\Organized" --report Preview.json
.\.venv\Scripts\python.exe main.py --organize --offline --source "D:\Music" --dest "D:\Organized" --report Run.json
```

打包后的 EXE 支持相同参数。使用 `--settings Profile.json` 读取导出的配置。

## 隐私与实际限制

- 音频在本机处理；在线查询发送发行检索词，不上传音乐。
- 设置、查询缓存与手动选择存放在 `%LOCALAPPDATA%/MusicOrganizer`。
- 本地歌曲密钥保存在普通 JSON 配置中，**未额外加密**。密钥值不进入日志、进程参数、报告或导出配置。
- 扫描只检查加密容器信息，成功与否以解密和音频校验结果为准。
- 实际整理处理全部扫描文件；交互预览最多显示 6,000 行，可筛选。
- LP rip 分类依靠明确的来源或发行标识，不凭高采样率推定黑胶来源。
- DSD 转 PCM 属于转换。常规曲库归档 DSD/SACD，苹果设备模式可选择独立归档原盘；两种模式均保留源文件。

## 开源协议与商业使用

**Music Organizer 的自有源码采用 [MIT](LICENSE) 协议。**允许使用、修改、分叉、再分发及商业销售，须保留 MIT 版权和许可声明。

第三方代码、库和独立工具保持各自的协议。当前 Python 运行依赖包含 **Mutagen（GPL-2.0-or-later）**：分发未经替换的完整组合应用时，仍须遵守 GPL，包括适用的源码提供义务。自有源码采用 MIT，不代表整个依赖包都变成宽松协议，也不免除这些义务；满足相关条件后仍可商业分发。

原生 PlatformAudio 解密核心采用 MIT / BSD 组件，KGG 实现基于 MIT 来源。FFmpeg、ncmdump、TagLib、独立调用的 SACD 工具、Python 及打包工具链各有许可。完整列表见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，许可文本保存在 `resources/Licenses/` 和 `native/platformaudio/`。

软件协议不授予音乐、封面、流媒体账号或外部资料服务的权利。

## 参与贡献

欢迎提交问题和范围明确的 Pull Request。建议附上应用版本、容器 / 加密版本、预期结果和可生成的最小复现。请勿在 Issue 中上传个人歌曲密钥、账号数据库或受版权保护的音乐。参见 [CONTRIBUTING.md](CONTRIBUTING.md)。
