# Changelog

## 1.5.0 — 2026-11-17

- Organize multiple source folders in one run. Add, remove and reorder sources in the GUI, or repeat `--source` in the CLI. Reject nested sources and validate every source against outputs and device archives.
- Keep per-source identity for same-name folders, CUE references, manual selections, encrypted-file status and output provenance. Deduplicate verified audio across roots, including rendered audio; retain different versions and resume after adding or reordering roots.
- Reuse byte-identical same-name archives across roots and existing single-source archives without replacing different originals.
- Add opt-in Audio tuning: SoXR HQ/VHQ/15–33-bit precision and Chebyshev mode; SWR Kaiser, Blackman–Nuttall and Cubic filters, length, phase-table precision, Kaiser beta and exact rational ratios. Custom cutoff starts at 98%; engine defaults remain active until enabled.
- Add sample-rate-family downsampling, expanded dithering/noise shaping, dither amplitude, output headroom and optional normalized downmix matrices. Reject unsupported shaping/rate combinations rather than silently substituting another method.
- Add DSD PCM rates from 44.1 to 384 kHz, independent 16/24/32-bit output, gain, double-precision 2/4/6/8-order Butterworth low-pass and optional 5 Hz DC removal. Advanced SACD ISO processing extracts DSD first so the controls reach the same decoder/post-processing chain as DSF/DFF. Apple ceilings still apply.
- Keep first-run v1.1 processing defaults. Save active DSP settings in conversion signatures, update changed processing from the original source, skip unchanged repeat encodes and support restoring original PCM.
- Retain manual tags, cover choices and release selections per source when the batch changes. Fix delayed tab hiding during rapid programmatic navigation; reject fractional values in integer DSP fields.
- Validate real encoders, cutoff frequency response, DSD gain/ultrasonic attenuation/DC removal, multi-source CUE/encrypted files, archive integrity, resume, Apple limits and both GUI languages using generated fixtures. The SACD advanced extractor path has a fixture-based contract check; no physical player sync test is claimed.

### 中文

- 新增多个源文件夹合并整理，支持添加、移除和排序；跨来源校验去重、区分同名目录、保留不同版本，新增来源及调整顺序后可续跑。
- 高级设置新增“音频精调”：SoXR 精度、SWR 三种滤波、可调 cutoff、采样率家族策略、更多抖动/噪声整形、增益余量及混缩矩阵保护。
- 扩展 DSD → PCM 采样率、独立位深、增益、低通阶数与去直流；高级 ISO 处理先提取 DSD，确保设置真正生效。
- 沿用首次使用的默认行为；新增选项按需启用，中英文界面同步支持。继续提供 GCC `-O3` + LTO 编译的便携 EXE。

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
