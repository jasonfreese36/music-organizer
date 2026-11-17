# Corresponding sources for v1.5.0 / 对应源码

The release provides `MusicOrganizer-Source.zip` and `ThirdPartySources.zip` alongside the EXE. The former contains the application, visual UI, translation catalog, native Go reader (including vendored TEA), tests, build scripts and retained notices. The latter contains the source archives pinned by URL, revision and SHA-256 in `resources/ThirdPartySources.json`, including Mutagen, FFmpeg, SACD Extract, TagLib, ncmdump, relevant copyleft native libraries, their build recipes, and Python dependency source distributions. These packages preserve their original licenses; the original application's MIT license does not replace them.

发布附件同时提供应用源码及第三方源码。清单记录下载位置、版本/提交与 SHA-256；第三方软件均保留原有许可。源码包不包含用户音乐、账号数据库或歌曲密钥。

## Build the application

Use Windows x64 and Python 3.14, install `requirements.txt`, then run `prepare.py` and `build.py --output dist`. The builder uses Nuitka 4.3.5, GCC `-O3` and LTO. Go uses its default optimizing compiler, `-trimpath`, vendored dependencies and stripped symbols. A PyInstaller fallback is available with `--compiler pyinstaller`. Compiler logs and `Build.json` identify the actual selected build; no Python/Go `-O3` flag is claimed.

Run `source_bundle.py --output dist` to reproduce the third-party source ZIP. Downloaded source archives are verified against the manifest. The binary inputs and their digests are pinned in `prepare.py` / `build_platform_audio.py`; local generated dependency metadata records the included versions.

## Rebuild or replace native components

- **FFmpeg / FFprobe:** extract FFmpeg at `a35157abb9` and `FFmpeg-Build-Recipes.zip` at `c9fe5114060e507409f7ee07edfd82efaf25d767`. The recipe repository contains `makeimage.sh`, `generate.sh`, `build.sh`, patches, variant definitions and pinned external-library revisions. Use the Windows x64 LGPL shared variant and the 8.1 addin, with the FFmpeg source fixed to the supplied snapshot. `ffmpeg -buildconf` prints the actual binary's full configure command. The archived external-library sources include LAME r7113, SoXR, libiconv/gnulib, FriBidi, GMP, libbluray/libudfread, GME, aribb24, libssh, OpenAL, libplacebo, GLib/GVDB/proxy-libintl, Cairo, Pango, librsvg, libzmq, SRT, twolame and VapourSynth. Local modifications from the build recipes are preserved in those recipe files. FFmpeg shared DLLs are separate files in the extracted runtime tool cache and may be replaced with compatible rebuilt versions.
- **SACD Extract 2 v0.9.0:** its archive contains source, `docs/building.md`, `scripts/build.sh`, CMake files and the upstream Windows build workflow. The reference libFLAC 1.5.0 archive is also included. The MinGW build links libiconv; the included upstream build instructions describe static Windows packaging.
- **ncmdump 1.5.1 / TagLib 2.0.2:** both sources are supplied. ncmdump includes its CMake and vcpkg configuration. Build with a compatible TagLib, including your modified version if desired, then replace `ncmdump.exe` in a source build or extracted tool cache.
- **Mutagen:** its exact 1.48.1 source distribution is supplied. Install the modified package in the build environment and rebuild the application. The original MIT application code permits such changes; Mutagen's applicable GPL terms still govern distribution of the combination.
- **Nuitka:** compiler/runtime source and retained AGPL text plus the Runtime Library Exception are supplied. The exception permits independent compiled applications under their own terms. It does not waive unrelated GPL/LGPL requirements.

The runtime cache is `%LOCALAPPDATA%/MusicOrganizer/RuntimeTools/<bundle fingerprint>`. It is application-owned and never a music source or output folder. The initial extraction verifies the tool manifest; later launches reuse it. To redistribute modified native tools, rebuild with modified `resources/tools` so the new bundle fingerprint and checksums reflect them. The application adds no restriction on reverse engineering to debug modifications to LGPL components. No signing keys, account credentials or proprietary SDK are required to build the original source.

For local replacement without rebuilding the EXE, copy the tool directory to a location you control, replace its executables or shared libraries with compatible versions, and set `MUSIC_ORGANIZER_TOOLS` to that directory before launching. This explicit override bypasses the managed-cache checksum restoration, so modified LGPL components can be loaded. Keep all required tools/DLLs in the directory. For example, in PowerShell: `$env:MUSIC_ORGANIZER_TOOLS = 'C:\CustomAudioTools'`, then run the EXE. Normal users do not need this override.

The application and source-bundle scripts are build recipes, not a promise of byte-identical output across every compiler host. Preserve copyright/license texts and the corresponding source materials when redistributing the full binary. External services, music and artwork retain their own terms.
