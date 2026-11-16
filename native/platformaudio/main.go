// Copyright (c) 2026 Music Organizer contributors. MIT.
package main

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"unicode/utf16"
)

const version = "PlatformAudio 1.3.0"

type request struct {
	Source  string `json:"source"`
	Dest    string `json:"dest"`
	Family  string `json:"family"`
	Key     string `json:"key"`
	KeyType string `json:"key_type"`
}

type response struct {
	OK      bool   `json:"ok"`
	Code    string `json:"code,omitempty"`
	Message string `json:"message,omitempty"`
	Scheme  string `json:"scheme,omitempty"`
	Format  string `json:"format,omitempty"`
	Bytes   int64  `json:"bytes,omitempty"`
	SHA256  string `json:"sha256,omitempty"`
}

type failure struct{ code, text string }

func (e *failure) Error() string   { return e.text }
func fail(code, text string) error { return &failure{code, text} }

type cipher interface{ Decrypt([]byte, int) }
type noCipher struct{}

func (noCipher) Decrypt([]byte, int) {}

type xorCipher struct{ key []byte }

func (c xorCipher) Decrypt(b []byte, off int) {
	for i := range b {
		b[i] ^= c.key[(off+i)%len(c.key)]
	}
}

type subCipher struct{ key []byte }

func (c subCipher) Decrypt(b []byte, off int) {
	for i := range b {
		b[i] -= c.key[(off+i)%len(c.key)]
	}
}

type headerCipher struct{ header []byte }

func (c headerCipher) Decrypt(b []byte, off int) {
	for i := range b {
		if off+i < len(c.header) {
			b[i] = c.header[off+i]
		}
	}
}

type plan struct {
	offset, length int64
	cipher         cipher
	scheme         string
}

func main() {
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "--version":
			fmt.Println(version)
			return
		case "--self-test":
			if !selfTest() {
				fmt.Println("self-test failed")
				os.Exit(1)
			}
			fmt.Println(version + " self-test passed (QMC/KGM/KWM/MG3D/UC/TM)")
			return
		}
	}
	result := response{}
	defer func() {
		if recover() != nil {
			result = response{Code: "invalid_data", Message: "Malformed encrypted container or key"}
		}
		_ = json.NewEncoder(os.Stdout).Encode(result)
	}()
	var r request
	d := json.NewDecoder(io.LimitReader(os.Stdin, 1024*1024))
	d.DisallowUnknownFields()
	if err := d.Decode(&r); err != nil {
		result = response{Code: "invalid_request", Message: "Invalid decoder request"}
		return
	}
	var err error
	result, err = decode(r)
	if err != nil {
		code := "invalid_data"
		var f *failure
		if errors.As(err, &f) {
			code = f.code
		}
		result = response{Code: code, Message: err.Error()}
	}
}

func decode(r request) (response, error) {
	if r.Source == "" || r.Dest == "" {
		return response{}, fail("invalid_request", "Missing source or output path")
	}
	if r.Family == "kugou_db" {
		return decodeKugouDB(r)
	}
	f, err := os.Open(r.Source)
	if err != nil {
		return response{}, fail("read_error", "Cannot read encrypted source")
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil || !st.Mode().IsRegular() || st.Size() < 16 {
		return response{}, fail("invalid_data", "Source is not a complete regular audio file")
	}
	p, err := choose(f, st.Size(), r)
	if err != nil {
		return response{}, err
	}
	if p.offset < 0 || p.length < 16 || p.offset+p.length > st.Size() {
		return response{}, fail("invalid_data", "Encrypted audio range is invalid")
	}
	first := make([]byte, min(int64(128), p.length))
	if _, err = f.ReadAt(first, p.offset); err != nil {
		return response{}, err
	}
	p.cipher.Decrypt(first, 0)
	ext := audioExt(first)
	if ext == "" {
		return response{}, fail("bad_key", "Decrypted header is not recognized audio; key or encryption version does not match")
	}
	out, err := os.OpenFile(r.Dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return response{}, fail("write_error", "Cannot exclusively create decoder output")
	}
	success := false
	defer func() {
		out.Close()
		if !success {
			_ = os.Remove(r.Dest)
		}
	}()
	if _, err = f.Seek(p.offset, io.SeekStart); err != nil {
		return response{}, err
	}
	h := sha256.New()
	writer := io.MultiWriter(out, h)
	buf := make([]byte, 1024*1024)
	var pos int64
	for pos < p.length {
		n := min(int64(len(buf)), p.length-pos)
		block := buf[:int(n)]
		if _, err = io.ReadFull(f, block); err != nil {
			return response{}, fail("invalid_data", "Encrypted audio ended early")
		}
		p.cipher.Decrypt(block, int(pos))
		if _, err = writer.Write(block); err != nil {
			return response{}, fail("write_error", "Cannot write decoded audio")
		}
		pos += n
	}
	if err = out.Close(); err != nil {
		return response{}, err
	}
	success = true
	return response{OK: true, Scheme: p.scheme, Format: ext, Bytes: pos, SHA256: hex.EncodeToString(h.Sum(nil))}, nil
}

func audioExt(b []byte) string {
	if bytes.HasPrefix(b, []byte("fLaC")) {
		return "flac"
	}
	if bytes.HasPrefix(b, []byte("ID3")) {
		return "mp3"
	}
	if bytes.HasPrefix(b, []byte("OggS")) {
		return "ogg"
	}
	if bytes.HasPrefix(b, []byte("MAC ")) {
		return "ape"
	}
	if len(b) >= 12 && string(b[:4]) == "RIFF" && string(b[8:12]) == "WAVE" {
		return "wav"
	}
	if len(b) >= 12 && string(b[4:8]) == "ftyp" {
		return "m4a"
	}
	if bytes.HasPrefix(b, []byte{0x30, 0x26, 0xB2, 0x75, 0x8E, 0x66, 0xCF, 0x11}) {
		return "wma"
	}
	if bytes.HasPrefix(b, []byte("wvpk")) {
		return "wv"
	}
	if bytes.HasPrefix(b, []byte(".RMF")) || bytes.HasPrefix(b, []byte{'.', 'r', 'a', 0xFD}) {
		return "ra"
	}
	if len(b) >= 4 && b[0] == 255 && b[1]&0xE0 == 0xE0 {
		if b[1]&0xF6 == 0xF0 {
			return "aac"
		}
		if b[1]&6 != 0 && b[1]&0x18 != 8 && b[2]&0xF0 != 0xF0 && b[2]&0x0C != 0x0C {
			return "mp3"
		}
	}
	return ""
}

func choose(f *os.File, size int64, r request) (plan, error) {
	header := make([]byte, min(size, int64(1024)))
	_, _ = f.ReadAt(header, 0)
	if r.Family == "qq" {
		return chooseQMC(f, size, header, r)
	}
	if audioExt(header) != "" {
		return plan{0, size, noCipher{}, "plain-audio"}, nil
	}
	switch r.Family {
	case "netease_uc":
		return plan{0, size, xorCipher{[]byte{0xA3}}, "netease-uc"}, nil
	case "qq_tm":
		if bytes.HasPrefix(header, []byte("QQMU")) {
			return plan{0, size, headerCipher{recoverTMHeader(header, size)}, "qq-tm-header"}, nil
		}
		return plan{}, fail("invalid_data", "TM audio header is not recognized")
	case "kuwo":
		return chooseKWM(header, size)
	case "kugou":
		if len(header) >= 24 && binary.LittleEndian.Uint32(header[20:24]) == 5 {
			return chooseKGG(header, size, r)
		}
		p, err := chooseKGM(header, size)
		if err != nil {
			return p, err
		}
		if choices, ok := p.cipher.(kgmChoice); ok {
			data := make([]byte, min(p.length, int64(128)))
			if _, err = f.ReadAt(data, p.offset); err != nil {
				return plan{}, err
			}
			probe := append([]byte(nil), data...)
			choices.modern.Decrypt(probe, 0)
			if audioExt(probe) != "" {
				p.cipher = choices.modern
			} else {
				probe = append([]byte(nil), data...)
				choices.legacy.Decrypt(probe, 0)
				if audioExt(probe) == "" {
					return plan{}, fail("unsupported_version", "Kugou crypto version or key slot is not supported")
				}
				p.cipher = choices.legacy
				p.scheme = "kgm-legacy"
			}
		}
		return p, nil
	case "migu":
		return chooseMigu(header, size, r)
	}
	return plan{}, fail("unsupported_version", "This encrypted scheme is not supported")
}

func recoverTMHeader(header []byte, size int64) []byte {
	// TM overwrites the first eight MP4 bytes. Locate the next complete box
	// instead of assuming every ftyp box is 32 bytes (some are 28 bytes).
	length := uint32(32)
	for pos := 16; pos+8 <= len(header) && pos <= 512; pos += 4 {
		name := string(header[pos+4 : pos+8])
		if name != "free" && name != "mdat" && name != "moov" && name != "skip" && name != "wide" {
			continue
		}
		n := int64(binary.BigEndian.Uint32(header[pos : pos+4]))
		if n >= 8 && int64(pos)+n <= size {
			length = uint32(pos)
			break
		}
	}
	result := []byte{0, 0, 0, 0, 'f', 't', 'y', 'p'}
	binary.BigEndian.PutUint32(result, length)
	return result
}

func chooseQMC(f *os.File, size int64, header []byte, r request) (plan, error) {
	length := size
	var rawKey []byte
	modern := false
	tail := make([]byte, min(size, int64(16)))
	_, _ = f.ReadAt(tail, size-int64(len(tail)))
	last := string(tail[len(tail)-4:])
	switch {
	case len(tail) >= 16 && string(tail[8:]) == "musicex\x00":
		n := int64(binary.LittleEndian.Uint32(tail[:4]))
		v := binary.LittleEndian.Uint32(tail[4:8])
		if v != 1 {
			return plan{}, fail("unsupported_version", "Unsupported QQ musicex footer version")
		}
		if n < 192 || n > 1024*1024 || n >= size {
			return plan{}, fail("invalid_data", "Invalid QQ musicex footer length")
		}
		length = size - n
		modern = true
	case last == "QTag" || last == "STag":
		n := int64(binary.BigEndian.Uint32(tail[len(tail)-8 : len(tail)-4]))
		if n < 1 || n > 1024*1024 || n+8 >= size {
			return plan{}, fail("invalid_data", "Invalid QQ tag length")
		}
		length = size - n - 8
		if last == "QTag" {
			meta := make([]byte, int(n))
			if _, err := f.ReadAt(meta, length); err != nil {
				return plan{}, err
			}
			fields := bytes.Split(meta, []byte(","))
			if len(fields) < 3 {
				return plan{}, fail("invalid_data", "Invalid QQ QTag metadata")
			}
			rawKey = fields[0]
		} else {
			modern = true
		}
	default:
		n := int64(binary.LittleEndian.Uint32(tail[len(tail)-4:]))
		if n > 0 && n <= 65535 && n+4 < size {
			length = size - n - 4
			rawKey = make([]byte, int(n))
			if _, err := f.ReadAt(rawKey, length); err != nil {
				return plan{}, err
			}
			rawKey = bytes.TrimRight(rawKey, "\x00")
		}
	}
	if length < 16 {
		return plan{}, fail("invalid_data", "QQ container has no complete audio payload")
	}
	if audioExt(header) != "" {
		return plan{0, length, noCipher{}, "qq-plain-audio"}, nil
	}
	var key []byte
	var err error
	if r.Key != "" {
		if r.KeyType == "qmc_raw" {
			key, err = base64.StdEncoding.DecodeString(strings.TrimSpace(r.Key))
		} else {
			key, err = deriveKey([]byte(strings.TrimSpace(r.Key)))
		}
	} else if len(rawKey) > 0 {
		key, err = deriveKey(rawKey)
	}
	if err != nil {
		return plan{}, fail("bad_key", "QQ EKey could not be decoded or validated")
	}
	if modern && len(key) == 0 {
		return plan{}, fail("key_required", "QQ STag/musicex requires its matching local EKey")
	}
	if len(key) > 65536 {
		return plan{}, fail("bad_key", "QQ key is too long")
	}
	var c cipher
	scheme := "qmc-static"
	if len(key) > 300 {
		c, err = newRC4Cipher(key)
		scheme = "qmc-rc4"
	} else if len(key) > 0 {
		c, err = newMapCipher(key)
		scheme = "qmc-map"
	} else {
		c = newStaticCipher()
	}
	if err != nil {
		return plan{}, fail("bad_key", "QQ cipher initialization failed")
	}
	test := append([]byte(nil), header[:min(int64(len(header)), length)]...)
	c.Decrypt(test, 0)
	if audioExt(test) == "" {
		if len(key) == 0 && (strings.Contains(strings.ToLower(filepath.Base(r.Source)), ".mflac") || strings.Contains(strings.ToLower(filepath.Base(r.Source)), ".mgg")) {
			return plan{}, fail("key_required", "This QQ file needs its matching local EKey")
		}
		return plan{}, fail("bad_key", "QQ key or encryption scheme does not match this file")
	}
	return plan{0, length, c, scheme}, nil
}

func chooseKWM(header []byte, size int64) (plan, error) {
	if len(header) < 1024 || (!bytes.Equal(header[:16], []byte("yeelion-kuwo-tme")) && !bytes.Equal(header[:16], []byte("yeelion-kuwo\x00\x00\x00\x00"))) {
		return plan{}, fail("unsupported_version", "Unrecognized Kuwo encryption header")
	}
	text := strconv.FormatUint(binary.LittleEndian.Uint64(header[0x18:0x20]), 10)
	base := []byte("MoOtOiTvINGwd2E6n0E1i7L5t2IoOoNk")
	key := make([]byte, 32)
	for i := range key {
		key[i] = base[i] ^ text[i%len(text)]
	}
	return plan{1024, size - 1024, xorCipher{key}, "kwm-legacy"}, nil
}

type kgmLegacy struct {
	key []byte
	vpr bool
}

func (c kgmLegacy) Decrypt(b []byte, off int) {
	for i := range b {
		pos := off + i
		v := c.key[pos%17] ^ b[i]
		v ^= v << 4
		n := pos >> 4
		mask := byte(0)
		for n >= 17 {
			mask ^= kgmTable1[n%272]
			n >>= 4
			mask ^= kgmTable2[n%272]
			n >>= 4
		}
		mask ^= kgmMask[pos%272]
		mask ^= mask << 4
		b[i] = v ^ mask
		if c.vpr {
			b[i] ^= vprDiff[pos%17]
		}
	}
}

type kgmV3 struct{ slot, file []byte }

func (c kgmV3) Decrypt(b []byte, off int) {
	for i := range b {
		p := off + i
		b[i] ^= c.file[p%17]
		b[i] ^= b[i] << 4
		b[i] ^= c.slot[p%16] ^ byte(p) ^ byte(p>>8) ^ byte(p>>16) ^ byte(p>>24)
	}
}
func kgmMD5(b []byte) []byte {
	d := md5.Sum(b)
	out := make([]byte, 16)
	for i := 0; i < 16; i += 2 {
		out[i] = d[14-i]
		out[i+1] = d[15-i]
	}
	return out
}
func chooseKGM(header []byte, size int64) (plan, error) {
	kgm := []byte{0x7C, 0xD5, 0x32, 0xEB, 0x86, 0x02, 0x7F, 0x4B, 0xA8, 0xAF, 0xA6, 0x8E, 0x0F, 0xFF, 0x99, 0x14}
	vpr := []byte{0x05, 0x28, 0xBC, 0x96, 0xE9, 0xE4, 0x5A, 0x43, 0x91, 0xAA, 0xBD, 0xD0, 0x7A, 0xF5, 0x36, 0x31}
	if len(header) < 60 || (!bytes.Equal(header[:16], kgm) && !bytes.Equal(header[:16], vpr)) {
		return plan{}, fail("invalid_data", "Kugou container magic is invalid")
	}
	offset := int64(binary.LittleEndian.Uint32(header[16:20]))
	v := binary.LittleEndian.Uint32(header[20:24])
	if v >= 5 {
		return plan{}, fail("unsupported_version", "Kugou KGG / crypto v5 is not supported by this decoder")
	}
	if offset < 60 || offset > 16*1024*1024 || offset >= size {
		return plan{}, fail("invalid_data", "Kugou audio offset is invalid")
	}
	own := append(append([]byte(nil), header[28:44]...), 0)
	legacy := kgmLegacy{own, bytes.Equal(header[:16], vpr)}
	// Selection is finalized against decrypted audio headers below by makeKGMPlan.
	return makeKGMPlan(offset, size, v, binary.LittleEndian.Uint32(header[24:28]), header[44:60], legacy)
}

func makeKGMPlan(offset, size int64, version, slot uint32, key []byte, legacy kgmLegacy) (plan, error) {
	if version == 3 && slot == 1 {
		return plan{offset, size - offset, kgmChoice{kgmV3{kgmMD5([]byte{0x6C, 0x2C, 0x2F, 0x27}), append(kgmMD5(key), 0x6B)}, legacy}, "kgm-v3"}, nil
	}
	return plan{offset, size - offset, legacy, fmt.Sprintf("kgm-legacy-v%d", version)}, nil
}

type kgmChoice struct{ modern, legacy cipher }

func (c kgmChoice) Decrypt(b []byte, off int) {
	c.modern.Decrypt(b, off)
}

func miguKey(key string) []byte {
	sum := md5.Sum([]byte("AC89EC47A70B76F307CB39A0D74BCCB0" + key))
	return []byte(strings.ToUpper(hex.EncodeToString(sum[:])))
}
func upperHex(b []byte) bool {
	for _, v := range b {
		if !(v >= '0' && v <= '9' || v >= 'A' && v <= 'F') {
			return false
		}
	}
	return true
}
func chooseMigu(header []byte, size int64, r request) (plan, error) {
	if r.Key != "" {
		key := []byte(r.Key)
		if len(key) != 32 {
			return plan{}, fail("bad_key", "Migu file key or mask must have 32 characters")
		}
		if r.KeyType == "migu_mask" {
			if !upperHex(key) {
				return plan{}, fail("bad_key", "Migu mask must be 32 uppercase hexadecimal characters")
			}
		} else {
			if _, err := hex.DecodeString(r.Key); err != nil {
				return plan{}, fail("bad_key", "Migu file key must be hexadecimal")
			}
			key = miguKey(r.Key)
		}
		return plan{0, size, subCipher{key}, "mg3d-file-key"}, nil
	}
	// Legacy MG3D WAV files contain zero-filled, aligned RIFF sections.
	for pos := 32; pos+32 <= min(640, len(header)); pos += 32 {
		key := append([]byte(nil), header[pos:pos+32]...)
		if !upperHex(key) {
			continue
		}
		probe := append([]byte(nil), header...)
		subCipher{key}.Decrypt(probe, 0)
		if !validWave(probe, size) {
			continue
		}
		return plan{0, size, subCipher{key}, "mg3d-wav-recovered"}, nil
	}
	return plan{}, fail("key_required", "MG3D needs its local fileKey; no recoverable WAV key was found")
}
func validWave(b []byte, size int64) bool {
	if len(b) < 64 || string(b[:4]) != "RIFF" || string(b[8:16]) != "WAVEfmt " {
		return false
	}
	n := int(binary.LittleEndian.Uint32(b[16:20]))
	if n != 16 && n != 18 && n != 40 {
		return false
	}
	channels := binary.LittleEndian.Uint16(b[22:24])
	rate := binary.LittleEndian.Uint32(b[24:28])
	if channels < 1 || channels > 32 || rate < 8000 || rate > 768000 {
		return false
	}
	next := 20 + n
	if next+8 > len(b) {
		return false
	}
	for _, ch := range b[next : next+4] {
		if ch < 32 || ch > 126 {
			return false
		}
	}
	length := int64(binary.LittleEndian.Uint32(b[4:8])) + 8
	return length <= size && length >= 44
}

func selfTest() bool {
	b := []byte{0}
	newStaticCipher().Decrypt(b, 0)
	if b[0] != staticCipherBox[27] {
		return false
	}
	return string(miguKey("0123456789abcdef0123456789abcdef")) == "CB4E917FFEB2B4A056445F4B3544495E"
}

// Decode UTF-16LE musicex names in tests and Python-compatible header probes.
func footerName(b []byte) string {
	units := make([]uint16, 0, len(b)/2)
	for i := 0; i+1 < len(b); i += 2 {
		u := binary.LittleEndian.Uint16(b[i : i+2])
		if u == 0 {
			break
		}
		units = append(units, u)
	}
	return string(utf16.Decode(units))
}
