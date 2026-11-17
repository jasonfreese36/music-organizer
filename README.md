<div align="center">

# Music Organizer

### Music from everywhere. One organized library.

Organize folders · Convert audio · Unlock supported files · Fix tags · Embed album art

[![Release](https://img.shields.io/github/v/release/jasonfreese36/music-organizer?color=7664E8&label=Download)](https://github.com/jasonfreese36/music-organizer/releases/latest) [![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011%20x64-0078D4)](#get-started) [![Original code: MIT](https://img.shields.io/badge/Original%20code-MIT-7664E8)](#license-and-commercial-use)

**English** · [简体中文](README.zh-CN.md)

**[Download Windows EXE](https://github.com/jasonfreese36/music-organizer/releases/latest/download/MusicOrganizer.exe)** · [Get started](#get-started) · [Report an issue](https://github.com/jasonfreese36/music-organizer/issues)

</div>

Loose MP3s, lossless rips, full-disc images, encrypted downloads, duplicate albums and missing artwork: years of collecting can leave you with files scattered across folders. **Music Organizer brings scanning, unlocking, conversion, metadata, artwork and library organization into one Windows desktop workflow.**

![Workflow illustration: a mixed music folder passes through scanning, unlocking, conversion, tagging and artwork to become an artist-and-album library. Source files are retained.](docs/assets/library-flow.svg)

**Portable EXE with its runtime and audio tools included.** No separate Python, FFmpeg or decoder setup. The interface supports English and Simplified Chinese, with light, dark and system appearance.

## From a mixed folder to a finished library

| What you have | What Music Organizer does |
|---|---|
| Downloads and rips scattered across nested folders | Rebuilds an **Artist → Year / Album → Track** library with consistent names. Singles join their releases under `Albums`. |
| MP3, AAC, FLAC, ALAC, APE, WAV and other mixed formats | Produces a **FLAC / MP3 / AAC** playback library, preserving compatible encoded audio and converting where needed. Splits CUE albums by sample positions. |
| Files locked to a music platform | **Locally unlocks supported downloads** from NetEase, QQ Music, Kugou, Kuwo and Migu, then feeds the recovered audio into the same workflow. [Schemes and key requirements ↓](#encrypted-audio-support) |
| Missing or inconsistent tags, platform IDs and untidy names | Cleans platform identifier fields and helps fill or correct **artist, album, title, track number, date and release information** using online matches or your selections. |
| Blank album art or covers left beside the music | Finds local or online artwork and **embeds the selected cover into output tracks**. Tags and covers can come from different search results. |
| Repeated files, alternate masters and LP rips | Skips duplicates confirmed by audio content within the same release, while keeping different recordings, masters and explicitly identified **Vinyl Rip** editions separate. |

Source files stay in place. The organized library is written to a separate destination, with verification and a report of anything that needs attention.

## Fast conversion, less repeated work

- **Parallel processing:** configurable audio tasks and a separate decoding concurrency setting help use your CPU and storage effectively.
- **Less re-encoding:** existing FLAC, MP3 and AAC can retain their audio payload when the selected settings allow it. A CUE image is decoded once before splitting.
- **Cached lookups:** release and artwork queries are grouped by album and cached, reducing repeated requests.
- **Reusable results:** verified outputs and source records let you stop and rerun against the same managed library without rebuilding every completed track.

The release EXE uses **GCC `-O3` + LTO** through Nuitka. Actual throughput depends on the source format, verification settings, disk and online services.

## Get started

1. **Download and open** [MusicOrganizer.exe](https://github.com/jasonfreese36/music-organizer/releases/latest/download/MusicOrganizer.exe). The first launch extracts bundled components.
2. **Choose your folders.** Select a music source and a separate destination, then click **Read-only scan**.
3. **Review the plan.** Inspect tracks, tags and covers. Use **Find tags and artwork** to compare releases or choose a local cover. Advanced settings are optional.
4. **Click Organize.** Review the finished albums and `Needs Review/Review.csv`. Correct uncertain items and rerun to the same destination to update or complete them.

For English, choose **Advanced → Appearance → Interface language → English**, then save and restart. First launch uses the established v1.1 processing defaults; device presets and custom rules are opt-in.

[Detailed user guide (简体中文)](docs/USER_GUIDE.zh-CN.md) · [Build, test and CLI instructions](docs/DEVELOPMENT.md)

### Your library after organizing

```text
Organized/
├── Albums/
│   └── Artist/
│       ├── 2024 - Album/
│       │   ├── 01 - Song.flac       # tags + embedded cover
│       │   └── cover.jpg           # optional extra artwork file
│       └── 2024 - Album [Vinyl Rip]/
├── Disc Archives/                 # DSD/SACD, CUE, encrypted originals
├── Needs Review/                  # missing matches and processing issues
├── Library Records/               # indexes, verification and run reports
└── Playlists/
```

Top-level folders use English names; artist, album and track names keep their original language. Folder structure, filenames and multidisc layout are customizable.

## Release tags and artwork, with a choice of sources

Search multiple providers, compare editions and select **tags and artwork independently**. For example, use MusicBrainz release data with an Apple iTunes cover. You can also supply a local image or an image URL.

| Source | What it contributes |
|---|---|
| **MusicBrainz** | Release, artist, track, label and edition information |
| **Cover Art Archive** | Artwork associated with a specific MusicBrainz release |
| **Apple iTunes** | Digital release and track information, plus album artwork |

Enable sources separately for tags and covers, set priorities and test API/image connectivity from the app. Automatic processing gives existing local tags and covers priority; manual selections let you replace them.

Matching considers artist, release, track title, position and duration. Availability varies by release: uncertain matches and missing covers are reported for review. Selected covers are embedded in the output audio, with an optional `cover.jpg` / `cover.png` alongside it.

## Encrypted audio support

Supported files are identified, decoded locally, verified and organized into the regular library. In regular-library mode, encrypted originals are also archived. **Support is specific to the encryption scheme and version**; some files need a matching local key.

| Platform | Implemented formats / schemes | Key requirements and limits |
|---|---|---|
| **NetEase Cloud Music** | NCM, supported legacy UC cache | NCM uses bundled ncmdump. |
| **QQ Music** | QMC static / Map / RC4, embedded EKey / QTag, TM header restoration | STag, musicex and other external-key variants need the matching local EKey or raw key. |
| **Kugou Music** | Legacy KGM / KGMA / VPR, crypto v3, KGG / crypto v5 | v5 needs its matching EKey; selected `KGMusicV3.db` and `kgg.keys` files can be imported. |
| **Kuwo Music** | Legacy KWM / KWMA | New encryption variants may be incompatible. |
| **Migu Music** | MG3D | Some legacy WAV files recover automatically; other supported files need a fileKey / mask. **MGM is not supported.** |

Use **Advanced → Platform audio** to review support states, import local keys and configure concurrency or full decode verification. Missing keys, damaged files and unsupported versions are reported separately; a failed file does not stop the remaining library. Only explicitly selected key databases are read, using temporary copies. The app does not log into streaming accounts or retrieve keys from a service.

## A library for your player

The default profile organizes a FLAC / MP3 / AAC library and archives DSD/SACD and CUE originals. **v1.4 also includes iPod and iPhone/iPad export presets** under **Advanced → Apple devices**.

| Preset | Newly encoded output | Compatibility limits |
|---|---|---|
| **iPod universal / shuffle** | MP3 256 kbps; 192 kbps in Save space | Mono/stereo, 32 / 44.1 / 48 kHz; ID3v2.3 |
| **iPod classic / nano** | AAC-LC; optional ALAC for lossless sources | Mono/stereo; ALAC up to 16-bit / 44.1 kHz |
| **iPhone / iPad** | AAC-LC; optional ALAC for lossless sources | Mono/stereo; ALAC up to 24-bit / 48 kHz |

Apple exports contain **MP3/M4A audio only**, with embedded JPEG covers. Incompatible formats, sample rates, channels and AAC profiles are converted; compatible MP3/AAC can retain their encoded audio. Extra archive copies are off by default. **Original archives → Save in a separate folder** optionally keeps original audio and disc files outside the import folder. Reports, indexes and playlists stay in a sibling `<destination> - Records` folder. Source files are retained with either archive option.

<details>
<summary>Apple export details</summary>

Select a separate, empty destination. Existing incompatible or non-audio files cause the export to be rejected without deleting them. Device constraints take priority over custom rules. Save space re-encodes lossy sources above 192 kbps; ALAC is generated from lossless sources. Covers are limited to 600 px for iPod and 1000 px for iOS.

The optional archive folder must be independent of the source, output and reports. Originals are copied with byte verification; optional artwork/booklets follow the archive switch. Its local path is excluded from exported reusable profiles.

Import the prepared `Albums` folder into Apple Music/iTunes, then sync with Apple Devices/iTunes. The app prepares files; it does not write an iPod database or sync hardware directly. Generated-audio and packaged-EXE tests have passed; physical-device syncing has not been tested. See Apple's [iPod classic specifications](https://support.apple.com/en-ca/112601), [iPod nano specifications](https://support.apple.com/en-is/112039), [lossless guidance](https://support.apple.com/en-euro/118295), [Windows import instructions](https://support.apple.com/en-mo/guide/music-windows/mus3081/windows) and [sync guide](https://support.apple.com/en-gb/guide/devices-windows/mchlbf6a1fab/1.5/windows/10).

</details>

## Your rules, configured visually

Advanced settings let you tailor the library without writing scripts.

| Setting | Choose what works for you |
|---|---|
| **Folders and filenames** | Artist/album layouts, title-first or track-first names, metadata fields, multidisc folders or prefixes, live path previews |
| **Audio conversion** | Output codec, sample-rate policy, bit depth, channels, SWResample / SoXR, dithering, FLAC compression, MP3 CBR/VBR and AAC bitrate |
| **Conditional rules** | Source codec, bitrate, sample rate, bit depth, channels, size or lossless status; AND/OR conditions; enable, duplicate and reorder |
| **Profiles and previews** | Import/export settings and export a read-only path/conversion plan as CSV; local paths and media keys are excluded from reusable profiles |
| **Appearance** | Light, dark or system mode; five accent colors; English or Simplified Chinese |

For example, point and click to create:

> **If** source codec is AAC **and** bitrate is above 256 kbps → **Convert to MP3**.

The first matching enabled rule wins. Existing MP3/AAC encoding is preserved by default; enable re-encoding when you want new settings applied to the same codec. Lossy-to-lossy conversion introduces another lossy generation, and converting to FLAC cannot restore lost quality.

## Local processing and traceable results

- **Source files are retained:** scan read-only, write to a separate destination, and publish output tracks after conversion, tag and audio checks.
- **Uncertain items stay visible:** CSV/JSON reports record missing matches, covers and processing failures. Same-name files are retained when audio equivalence cannot be confirmed.
- **Music stays on your computer:** online lookup sends release search terms, not audio. Local scanning, conversion and supported decryption can work offline.
- **Local preferences and keys:** preferences, caches and selections live under `%LOCALAPPDATA%/MusicOrganizer`. Imported keys are stored in local JSON without extra encryption; values are excluded from logs, process arguments, reports and exported profiles.

<details>
<summary>Other practical details</summary>

The interactive preview shows up to 6,000 rows with filtering; processing covers all scanned files. Encrypted scans inspect containers, with final success determined during decoding and verification. Vinyl-rip classification requires explicit source/release labels; high sample rate alone is not proof of an LP source. DSD-to-PCM is a conversion: regular-library mode archives DSD/SACD, and Apple profiles offer a separate original archive.

</details>

## Build and contribute

For source users: **Windows 10/11 x64, Python 3.14**. Pinned dependencies, native-tool preparation, `-O3` packaging, tests and CLI examples are in the [developer guide](docs/DEVELOPMENT.md). Releases include the EXE, matching application source, third-party corresponding sources, build information and SHA-256 checksums.

[Report a bug or request a feature](https://github.com/jasonfreese36/music-organizer/issues) · [Contribution guide](CONTRIBUTING.md) · [Corresponding-source instructions](docs/CORRESPONDING_SOURCES.md)

Include the application version, file/encryption version and expected result when reporting an issue. Generated reproductions are welcome; keep personal keys, account databases and copyrighted audio out of public issues.

## License and commercial use

**Original application code: [MIT](LICENSE)** — use, modify, fork and sell it commercially while retaining the MIT notice. Third-party components retain their own licenses. The complete application includes **Mutagen (GPL-2.0-or-later)** and other GPL/LGPL components, so distributing it also requires compliance with their notice and corresponding-source obligations. Commercial distribution remains permitted under those conditions.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the retained license texts and [rebuilding instructions](docs/CORRESPONDING_SOURCES.md). Software licensing does not grant rights to music, artwork, streaming accounts or external metadata services.
