# Changelog

## 1.4.0 — 2026-11-16

- Add opt-in iPod universal, classic/nano, shuffle and iPhone/iPad export presets, with device format/rate/channel restrictions and Standard, Save space or compatible ALAC lossless choices.
- Keep device import folders audio-only. Embed compatible JPEG artwork and move reports/indexes/playlists to a sibling Records folder.
- Add optional independent original archives for Apple exports, with path separation, source preservation, hash verification and repeat-run reuse. The default makes no additional original archive.
- Add English across UI, visual rules, lookup panels, diagnostics and help, with a saved language choice and restart. Release metadata retains its original language; initial v1.1 processing defaults remain.
- Add a Nuitka/GCC `-O3` + LTO build, verified native-tool caching, explicit replacement tools, pinned corresponding-source bundles and binary smoke tests. Keep PyInstaller as a fallback.
- Relaunch the compiled EXE when changing language; isolate onefile runtime directories for simultaneous starts while retaining the verified native-tool cache.
- Validate generated high-rate/multichannel audio, AAC/MP3/ALAC, DSD/CUE, repeat runs, archive verification, unsupported-target rejection, language placeholders, existing core/rule/platform behavior and source immutability. No physical iPod/iPhone/iPad sync test is claimed.

### 中文

- 新增 iPod 与 iPhone/iPad 可选输出预设，适配格式、采样率、位深和声道，内嵌 JPEG 封面。
- 设备目录只留兼容音轨；报告、索引及播放列表独立存放，原盘可选择另一个目录归档，默认不另存，源文件保留。
- 新增英语界面，支持保存语言后重启；首次使用仍沿用 v1.1 默认整理设置。
- 新增实际启用 `-O3` 与 LTO 的编译方式、工具缓存及第三方对应源码附件，保留原有功能与许可说明。
