<div align="center">

# Music Organizer

**Turn a mixed music folder into a consistent, searchable library.**

[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows)](#getting-started)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](#build-from-source)
[![Source license](https://img.shields.io/badge/Original%20source-MIT-6556DC)](LICENSE)

**English** · [简体中文](README.zh-CN.md)

</div>

A Windows desktop application for organizing FLAC, MP3, AAC, lossless albums, DSD/SACD images and supported encrypted downloads. Scan first, review the plan, and write an organized library to a separate folder while keeping the source files intact.

**v1.4.0** adds iPod / iPhone / iPad exports, optional separate original archives and an English interface. Choose the language in **Advanced → Appearance**, then save and restart. Initial processing defaults remain those of v1.1.

Download the portable [Windows EXE](https://github.com/jasonfreese36/music-organizer/releases/latest/download/MusicOrganizer.exe) from [Releases](https://github.com/jasonfreese36/music-organizer/releases). Matching application source, third-party corresponding sources and checksums accompany the binary. The original source is MIT; the complete application also contains GPL/LGPL components. See [License and commercial use](#license-and-commercial-use).

## Highlights

- **Read-only inventory.** Inspect formats, existing tags and covers before organizing. Source and destination must be separate directories.
- **A consistent playback library.** Default outputs are FLAC, MP3 and AAC in an `.m4a` container. Existing MP3/AAC are normally preserved without lossy re-encoding.
- **Archive-aware processing.** Keep DSD/SACD images, CUE images and encrypted originals. Split CUE albums by sample positions and retain explicitly identified vinyl rips and alternate masters.
- **Release metadata and embedded artwork.** Search MusicBrainz, Cover Art Archive and Apple iTunes; compare releases, choose tags and artwork independently, and test source connectivity.
- **Visual advanced settings.** Choose light, dark or system appearance, five accent colors, folder/file naming presets, sample-rate and encoder options, and ordered point-and-click conversion rules.
- **Resume and inspect.** Verify audio, track source identities, avoid confirmed duplicates, resume interrupted work, and export CSV/JSON reports.

## Getting started

This repository contains the source, native decoder sources, licenses and build scripts. To run locally, follow [Build from source](#build-from-source). A packaged build produces a portable `MusicOrganizer.exe` with its Python runtime and native tools included.

1. Select a music source and a **separate** destination directory.
2. Click **Read-only scan**. Review files and correct release information or choose artwork if needed.
3. Click **Organize**. Successful tracks go into the destination library; source files remain in place.
4. Review `Needs Review/Review.csv` and `Library Records/Latest Run.json`. Correct uncertain items and run again against the same managed destination.

Online matching is optional. A service may not have a particular edition or cover; uncertain matches are reported instead of being presented as verified release data.

### Default library layout

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

Top-level folder names are English. Artist, album and song names retain their original language. Singles and recovered tracks are organized under `Albums` using their release information.

### Apple device exports

Open **Advanced → Apple devices** and select a separate, empty destination. The output is a folder to import into Apple Music/iTunes, then sync with Apple Devices/iTunes; this application does not write an iPod database or sync hardware directly.

| Preset | Newly encoded output | Limits |
|---|---|---|
| iPod universal / shuffle | MP3, 256 kbps; 192 kbps Save space | Mono/stereo, 32 / 44.1 / 48 kHz; ID3v2.3 |
| iPod classic / nano | AAC-LC, or ALAC for lossless sources | Mono/stereo; ALAC capped at 16-bit / 44.1 kHz |
| iPhone / iPad | AAC-LC, or ALAC for lossless sources | Mono/stereo; ALAC capped at 24-bit / 48 kHz |

Compatible MP3/AAC tracks can retain their encoded audio; Save space re-encodes lossy sources above 192 kbps. Incompatible codecs, high sample rates, multichannel audio and AAC profiles are converted. Device constraints take precedence over custom rules. The import folder contains **MP3/M4A audio only**, with embedded JPEG covers (up to 600 px for iPod, 1000 px for iOS). Reports, indexes and playlists go to a separate sibling `<destination> - Records` folder. An existing destination with incompatible or non-audio files is rejected without deleting anything.

**Original archives** defaults to **No extra archive**. Choose **Save in a separate folder** to archive DSD/SACD ISO, CUE images, encrypted files and ordinary audio originals in an independent folder, with byte verification. Optional source artwork/booklets follow the existing archive switch. Archive, report, source and device output paths cannot overlap. Source files are retained in both modes. Archive paths are excluded from exported reusable profiles.

Device generations differ. Check Apple's [iPod classic specifications](https://support.apple.com/en-ca/112601), [iPod nano specifications](https://support.apple.com/en-is/112039), and [lossless audio guidance](https://support.apple.com/en-euro/118295). See Apple's [Windows import instructions](https://support.apple.com/en-mo/guide/music-windows/mus3081/windows) and [device sync guide](https://support.apple.com/en-gb/guide/devices-windows/mchlbf6a1fab/1.5/windows/10). Verification uses generated audio and packaged-EXE tests; physical-device syncing has not been tested.

## Supported encrypted audio

The application identifies known containers, archives their originals, decodes locally, validates the result and then applies the normal library workflow. Recognition is based on known schemes, **not a promise that every file from a platform is supported**.

| Platform | Implemented schemes | Requirements / limits |
|---|---|---|
| NetEase Cloud Music | NCM, supported legacy UC cache | NCM uses the bundled ncmdump tool. |
| QQ Music | QMC static / Map / RC4, embedded EKey / QTag, TM header restoration | STag, musicex and other external-key variants need the matching local EKey or raw key. |
| Kugou Music | Legacy KGM / KGMA / VPR, crypto v3, KGG / crypto v5 | v5 needs its matching EKey; explicitly supplied `KGMusicV3.db` and `kgg.keys` files can be imported. |
| Kuwo Music | Legacy KWM / KWMA | New encryption variants may be incompatible. |
| Migu Music | MG3D | Some legacy WAV files can be recovered automatically; other supported files need their fileKey / mask. **MGM is not supported.** |

Open **高级设置 → 平台音频** (Advanced settings → Platform audio) to see support states, import local keys, set decoding concurrency or change full decode verification. Missing keys, mismatched keys, damaged files and unsupported versions receive separate statuses; one failed file does not stop the rest of the library.

Only databases explicitly selected by the user are read. Database decoding operates on temporary copies; the original database is unchanged. The application does not sign in to streaming accounts or obtain download permissions or song keys from a service.

## Metadata and artwork sources

| Source | Tags | Artwork |
|---|---|---|
| MusicBrainz | Release, artist, track, label and edition information | Release identification for Cover Art Archive |
| Cover Art Archive | — | Artwork associated with a MusicBrainz release |
| Apple iTunes | Digital release and track information | Album artwork |

Enable tag and artwork sources separately, set their priorities and test real connectivity. When searching manually, compare releases and choose metadata from one result and artwork from another. Existing local tags and artwork have priority in the automatic workflow.

Artwork is embedded in the output tracks; writing an additional `cover.jpg` / `cover.png` is configurable. Platform identifier fields are cleaned while valid release information is retained.

## Advanced settings

The initial experience uses conservative defaults: light/violet appearance, empty custom rules, FLAC for lossless playback copies, and preservation of existing MP3/AAC encoding.

- **Appearance:** light, dark or system mode; violet, blue, teal, rose or amber accents.
- **Folder and file naming:** presets, selectable metadata fields and live path previews; track-first, title-first and artist-first styles; multidisc folders, prefixes or a flat layout.
- **Audio conversion:** FLAC / MP3 / AAC, sample-rate limits or fixed rates, bit depth, channels, SWResample / SoXR, dithering and detailed encoding settings.
- **Visual rules:** ordered conditions using source codec, bitrate, sample rate, bit depth, channels, size or lossless status; AND / OR matching, enable/disable, duplicate and reorder. The first matching enabled rule wins.
- **Profiles and previews:** import/export settings and export the read-only path/conversion plan as CSV. Profiles exclude source/destination paths and media keys.

Example: to convert AAC above 256 kbps into MP3, add an AAC codec condition, add a bitrate `> 256 kbps` condition, choose “all conditions”, then select MP3 as the output. Rules are configured through controls, without writing code. Conversion between lossy codecs introduces another lossy generation; the source is retained.

The detailed Chinese user guide is available at [docs/USER_GUIDE.zh-CN.md](docs/USER_GUIDE.zh-CN.md).

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

Outputs include `MusicOrganizer.exe`, a source ZIP, documentation and checksums. Packaging the program does **not** remove the redistribution obligations of its dependencies; read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before distributing binaries.

Before public binary distribution, run `python source_bundle.py --output dist` to produce the pinned third-party source attachment. See [corresponding-source and rebuilding instructions](docs/CORRESPONDING_SOURCES.md).

### Tests

These integration tests generate their own audio in fresh output directories. They do not need a personal music library or streaming credentials.

```powershell
.\.venv\Scripts\python.exe test_e2e.py --root test-output/e2e
.\.venv\Scripts\python.exe test_advanced.py --root test-output/advanced
.\.venv\Scripts\python.exe test_platforms.py --root test-output/platforms
.\.venv\Scripts\python.exe test_apple.py --root test-output/apple
.\.venv\Scripts\python.exe test_i18n.py
.\.venv\Scripts\python.exe main.py --check-gui --language en --report Gui-English.json
.\.venv\Scripts\python.exe main.py --check-gui --language zh_CN --report Gui-Chinese.json
```

Use a new root for each run. Optional real-file checks belong outside version control. Online-source tests are separate because service availability, regional responses and rate limits vary.

`--check-gui` opens the actual GUI, checks its viewable geometry, page navigation, device/archive controls, theme switching and restart command, then exits. It uses temporary preferences and does not read a music library. Run the same flags against the packaged EXE to verify the compiled UI.

An optional GitHub Actions workflow template is provided at [docs/ci/windows-tests.yml](docs/ci/windows-tests.yml). A maintainer can copy it to `.github/workflows/` to enable hosted tests.

### Diagnostic CLI

```powershell
.\.venv\Scripts\python.exe main.py --check-tools --report Tools.json
.\.venv\Scripts\python.exe main.py --preview --offline --source "D:\Music" --dest "D:\Organized" --report Preview.json
.\.venv\Scripts\python.exe main.py --organize --offline --source "D:\Music" --dest "D:\Organized" --report Run.json
```

The same flags work with a packaged `MusicOrganizer.exe`. Use `--settings Profile.json` to load an exported profile.

## Privacy and practical limits

- Music is processed locally. Online lookup sends release search terms; it does not upload audio.
- Preferences, query caches and manual selections are stored under `%LOCALAPPDATA%/MusicOrganizer`.
- Local song keys are stored as a normal local JSON configuration file, **without an additional encryption layer**. Key values are excluded from logs, process arguments, reports and exported profiles.
- Encrypted-file scans inspect container information; final success is determined during decoding and audio verification.
- Library processing covers all scanned files; the interactive preview is limited to 6,000 rows and supports filtering.
- Vinyl-rip classification uses explicit source/release labels. A high sample rate alone is not treated as proof of an LP source.
- DSD-to-PCM is a conversion. Regular-library mode archives DSD/SACD; Apple presets optionally archive originals in a separate folder. Source files are always retained.

## License and commercial use

**The original Music Organizer source is licensed under [MIT](LICENSE).** It may be used, modified, forked and sold commercially, provided the MIT copyright and permission notice is retained.

Third-party code, libraries and programs keep their own licenses. In particular, the current Python runtime uses **Mutagen (GPL-2.0-or-later)**. Distributing the unchanged combined application therefore requires GPL compliance; the MIT grant for original source does not make the full dependency bundle permissive or remove its source-distribution obligations. Commercial distribution remains permitted subject to those conditions.

The native PlatformAudio reader uses MIT/BSD components and an MIT-based KGG implementation. FFmpeg, ncmdump, TagLib, the separately invoked SACD extractor, Python and the packaging toolchain each have their own terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the retained license texts under `resources/Licenses/` and `native/platformaudio/`.

The software license does not grant rights to music, artwork, streaming accounts or external metadata services.

## Contributing

Bug reports and focused pull requests are welcome. Include the application version, container/encryption version, expected result and a minimal generated reproduction when possible. Do not upload personal song keys, account databases or copyrighted music with an issue. See [CONTRIBUTING.md](CONTRIBUTING.md).
