# Third-party notices / 第三方许可

Music Organizer's original source is licensed under the [MIT License](LICENSE), Copyright (c) 2026 jasonfreese36 and contributors. That grant permits commercial use of the original code. It does not replace the licenses of third-party source, libraries, runtimes or programs listed below.

Music Organizer 自有源码采用 MIT，允许商业使用。第三方组件保持原协议，不因本仓库的 MIT 声明而改变。

## Full application distribution

The current Python application imports Mutagen, which is GPL-2.0-or-later. Distribution of the unchanged combined application requires compliance with the applicable GPL terms, including providing the corresponding source. The original-source MIT grant does not make that full combination suitable for unrestricted proprietary distribution. Commercial sale and redistribution are permitted subject to those third-party terms.

当前完整版使用 Mutagen（GPL-2.0-or-later）；完整组合程序的再分发须遵守相应 GPL 条件，包括适用的源码提供义务。商业销售可以进行，但 MIT 自有源码声明不免除这些义务。

The native command-line tools are separately invoked programs. Their licenses, source-distribution requirements and notices remain applicable. FFmpeg is a shared LGPL build. Compatible modified tools/libraries may be loaded from an explicit `MUSIC_ORGANIZER_TOOLS` directory, or bundled by rebuilding. The optimized v1.4.0 EXE uses Nuitka and GCC `-O3` + LTO; Nuitka's Runtime Library Exception permits independent application output under its own terms. The optional PyInstaller builder retains its bootloader exception. Neither exception waives unrelated dependency obligations.

## Components

| Component | Version / license | Upstream source |
|---|---|---|
| Python | 3.14, PSF and component licenses | https://www.python.org/downloads/source/ |
| Tcl/Tk | 8.6, Tcl/Tk license | https://www.tcl.tk/software/tcltk/ |
| Mutagen | 1.48.1, GPL-2.0-or-later | https://github.com/quodlibet/mutagen/tree/release-1.48.1 |
| Pillow | 13.0.0, HPND and bundled component notices | https://github.com/python-pillow/Pillow/tree/13.0.0 |
| certifi / Mozilla CA bundle | 2026.10.23, MPL-2.0 | https://github.com/certifi/python-certifi |
| opencc-python-reimplemented / dictionaries | 0.1.7, Apache-2.0 | https://github.com/yichen0831/opencc-python |
| CustomTkinter | 6.0.0, MIT and bundled font notices | https://github.com/TomSchimansky/CustomTkinter |
| darkdetect | 0.8.0, BSD-3-Clause | https://github.com/albertosottile/darkdetect |
| packaging | 26.3, Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| PyInstaller bootloader | 6.22.3, GPL with bootloader exception | https://github.com/pyinstaller/pyinstaller/tree/v6.22.3 |
| Nuitka compiler/runtime | 4.3.5, AGPL-3.0-or-later with Runtime Library Exception | https://github.com/Nuitka/Nuitka/tree/4.3.5 |
| Onefile zstd compression | zstandard 0.25.0 / bundled zstd, BSD licenses | https://github.com/indygreg/python-zstandard |
| FFmpeg / FFprobe | n8.1.3-34-ga35157abb9, shared LGPLv3 build | https://github.com/FFmpeg/FFmpeg/tree/a35157abb9 |
| FFmpeg build recipes / included components | autobuild-2026-11-09-12-42 | https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-11-09-12-42 |
| ncmdump | 1.5.1, MIT | https://github.com/taurusxin/ncmdump/tree/1.5.1 |
| TagLib in ncmdump | 2.0.2, LGPL-2.1-only OR MPL-1.1 | https://github.com/taglib/taglib/tree/v2.0.2 |
| SACD Extract 2 / libFLAC | 0.9.0, GPL-2.0 / bundled component licenses | https://github.com/dev-zetta/sacd_extract2/tree/v0.9.0 |
| PlatformAudio reader, original code | MIT | `native/platformaudio` |
| QMC static / Map / RC4, EKey / TEA, KGM v3, KWM, TM reference and test vectors | Unlock Music, MIT | https://github.com/lishanxin/unlockMusic/tree/380ed78b6b0bcc70250e9a97ed5189795c4466f2 |
| Legacy KGM / VPR constants and reference | MengYX / huangbao, MIT, preserved by MusicUnlock | https://github.com/Lin-M11/MusicUnlock/tree/58c4f9b6e13ffc8dd8bd86273f39fe9f585ec428 |
| KGG layout and Kugou database algorithm | kgg-dec, Copyright (c) 2024 LSR, MIT | https://github.com/lizipeng0013/kgg-dec.mirror/tree/b3bb5cb15933fb6c2c859665041d728e24777ca9 |
| MG3D transform, key derivation and vectors | TuneWeave, MIT | https://github.com/MOPELotus/TuneWeave/tree/84bc7b34935198caa40f612876f4624a17b40221/crates/tuneweave-provider-migu/src/client/mg3d.rs |
| MG3D WAV recovery reference | MengYX, MIT, preserved mirror | https://github.com/kevinstoy/unlock-music/blob/master/src/decrypt/mg3d.ts |
| Go runtime / standard library | Go 1.27.4, BSD-3-Clause | https://go.dev/dl/ |
| golang.org/x/crypto/tea | v0.29.0, BSD-3-Clause, vendored | https://github.com/golang/crypto/tree/v0.29.0/tea |

Retained texts are under `resources/Licenses/`, `native/platformaudio/LICENSE-*` and `native/platformaudio/vendor/`. Preparation gathers additional runtime notices. Generated artifact versions and checksums are recorded in `resources/Dependencies.json` and `resources/PlatformAudio.json`; download origins are pinned in the build scripts.

The v1.4.0 release accompanies its EXE with application and pinned third-party source ZIPs, including relevant copyleft native-library sources and build recipes. The manifest is `resources/ThirdPartySources.json`; download/verify/package them using `source_bundle.py`. See [corresponding-source and replacement instructions](docs/CORRESPONDING_SOURCES.md). Further binary redistribution must preserve applicable sources, notices and replacement/relinking permissions. An upstream URL alone does not replace a source-delivery requirement.

## Changes and provenance

The native reader adds streaming I/O, bounded parsing, validation, cancellation through the host application, safe output creation and structured results. Its QMC code retains the Unlock Music notice. Legacy KGM constants retain the MusicUnlock/MengYX/huangbao notices. MG3D uses the MIT option from TuneWeave. The KGG/database implementation in this repository is a new Go port based on the MIT kgg-dec reference, replacing the GPL-based adapter from the private prototype.

## Services and media

MusicBrainz, Cover Art Archive and Apple iTunes are external services, not included software. Their data, images and service usage remain subject to their own terms. Music, artwork, real account databases and personal song keys are not distributed in this repository. No audio is uploaded by the application; online lookup sends release search terms.
