# Build, test and diagnose

[Project overview](../README.md) · [简体中文](DEVELOPMENT.zh-CN.md)

## Build from source

Use **Windows 10/11 x64 and Python 3.14**. Runtime and packaging versions are pinned in `requirements.txt`. Native downloads are pinned by SHA-256 in `prepare.py`; the native reader's Go SDK is pinned in `build_platform_audio.py`.

```powershell
git clone https://github.com/jasonfreese36/music-organizer.git
cd music-organizer
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prepare.py
.\.venv\Scripts\python.exe main.py
```

`prepare.py` downloads the pinned tools/Go SDK, verifies checksums, runs native tests, builds `platformaudio.exe`, collects licenses and generates build resources. The Go TEA dependency is vendored. A normal source build requires network access.

To create the portable application:

```powershell
.\.venv\Scripts\python.exe build.py --output dist
```

The default builder uses Nuitka 4.3.5 and GCC with **`-O3` and LTO**, and checks the compiler log for both flags. It produces a native one-file application and a verified local cache for bundled tools. First build downloads the pinned compiler SDK. Go's native reader uses Go's normal optimizations and stripped symbols; Go does not have an `-O3` flag. `--compiler pyinstaller` remains available as a bytecode-packaging fallback and is not labeled an O3 build. Build metadata and compiler logs accompany local outputs; processing speed still depends on decoding, disk speed and online services.

Outputs include `MusicOrganizer.exe`, a source ZIP, documentation and checksums. Packaging the program does **not** remove the redistribution obligations of its dependencies; read [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) before distributing binaries.

Before public binary distribution, run `python source_bundle.py --output dist` to produce the pinned third-party source attachment. See [corresponding-source and rebuilding instructions](CORRESPONDING_SOURCES.md).

### Tests

These integration tests generate their own audio in fresh output directories. They do not need a personal music library or streaming credentials.

```powershell
.\.venv\Scripts\python.exe test_e2e.py --root test-output/e2e
.\.venv\Scripts\python.exe test_advanced.py --root test-output/advanced
.\.venv\Scripts\python.exe test_multisource.py --root test-output/multisource
.\.venv\Scripts\python.exe test_audio_dsp.py --root test-output/audio-dsp
.\.venv\Scripts\python.exe test_platforms.py --root test-output/platforms
.\.venv\Scripts\python.exe test_apple.py --root test-output/apple
.\.venv\Scripts\python.exe test_apple_discs.py --root test-output/apple-discs
.\.venv\Scripts\python.exe test_i18n.py
.\.venv\Scripts\python.exe main.py --check-gui --language en --report Gui-English.json
.\.venv\Scripts\python.exe main.py --check-gui --language zh_CN --report Gui-Chinese.json
```

Use a new root for each run. Optional real-file checks belong outside version control. Online-source tests are separate because service availability, regional responses and rate limits vary.

`--check-gui` opens the actual GUI, checks its viewable geometry, page navigation, device/archive controls, theme switching and restart command, then exits. It uses temporary preferences and does not read a music library. Run the same flags against the packaged EXE to verify the compiled UI.

An optional GitHub Actions workflow template is provided at [docs/ci/windows-tests.yml](ci/windows-tests.yml). A maintainer can copy it to `.github/workflows/` to enable hosted tests.

### Diagnostic CLI

```powershell
.\.venv\Scripts\python.exe main.py --check-tools --report Tools.json
.\.venv\Scripts\python.exe main.py --preview --offline --source "D:\Music" --dest "D:\Organized" --report Preview.json
.\.venv\Scripts\python.exe main.py --organize --offline --source "D:\Music" --dest "D:\Organized" --report Run.json
```

The same flags work with a packaged `MusicOrganizer.exe`. Use `--settings Profile.json` to load an exported profile.

Repeat `--source` to combine folders in one run:

```powershell
.\.venv\Scripts\python.exe main.py --organize --offline --source "D:\Rips" --source "E:\Downloads" --dest "F:\Library" --report Run.json
```

Sources are ordered and must be disjoint. Reports cannot be written inside a source. The GUI checks also exercise source-list editing, fractional DSP values, inactive-engine controls and first-run defaults. DSP measurements and the generated SACD extractor contract are described in the [audio tuning guide](AUDIO_TUNING.md).
