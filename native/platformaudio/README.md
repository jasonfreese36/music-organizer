# PlatformAudio provenance

The original reader code is MIT-licensed under the project root LICENSE. Third-party portions and test vectors retain their notices. The Go runtime and vendored TEA primitive use BSD licenses.

This is an offline streaming reader. It contains no network clients, account login, audio upload or automatic client-database discovery. A JSON request arrives on standard input and a JSON response is returned on standard output. Keys are excluded from process arguments and result text. Output creation is exclusive; failed output is removed. The host validates the decoded audio before publishing it to the library.

## References

- QMC static / Map / RC4, EKey / TEA and independent known-answer vectors: Unlock Music CLI, MIT, mirrored at `lishanxin/unlockMusic@380ed78b6b0bcc70250e9a97ed5189795c4466f2`. The reader adds bounded footer parsing, fixes TEA padding checks, handles zero RC4 seeds, and removes online lookup and automatic database access.
- KGM v3 MD5, KWM and TM recovery: the same MIT Unlock Music reference.
- Legacy KGM / VPR constants: MengYX / huangbao, MIT, preserved by `Lin-M11/MusicUnlock@58c4f9b6e13ffc8dd8bd86273f39fe9f585ec428`; see LICENSE-MusicUnlock and NOTICES-MusicUnlock.md.
- KGG v5 layout and KGMusicV3.db page transform: a Go port of the MIT `lizipeng0013/kgg-dec.mirror@b3bb5cb15933fb6c2c859665041d728e24777ca9`, `src/jobs.hpp` and `src/infra/infra.cpp`, Copyright (c) 2024 LSR. This replaces the GPL-based adapter used in the private prototype. See LICENSE-KGG-Dec. The MIT reference's unsafe length assumptions and key logging are not carried over; this reader bounds lengths, streams pages and returns no key values.
- MG3D subtraction, file-key derivation and native vectors: the MIT option of `MOPELotus/TuneWeave@84bc7b34935198caa40f612876f4624a17b40221`, `crates/tuneweave-provider-migu/src/client/mg3d.rs`. Legacy WAV recovery follows MengYX's MIT unlock-music implementation, preserved by `kevinstoy/unlock-music`; each candidate uses a fresh header copy.
- TEA: `golang.org/x/crypto/tea` v0.29.0, BSD-3-Clause, vendored with its license.

Native tests cover upstream QMC vectors, MG3D vectors/recovery, malformed footer rejection, KGG key/bounds handling, database page transforms/integrity and exclusive output, plus variable TM box sizes.

NCM is handled by the separately bundled ncmdump program. MG3D and MGM are different schemes; MGM is not supported. External-key variants require the matching user-supplied keys.

Build from this directory with `CGO_ENABLED=0 go build -mod=vendor -trimpath -ldflags="-s -w" .`. The Windows packaging script pins and verifies the Go SDK and runs `go test -mod=vendor ./...` first.
