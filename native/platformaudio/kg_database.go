// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Music Organizer contributors.
// Ported from kgg-dec, Copyright (c) 2024 LSR. See LICENSE-KGG-Dec.
// lizipeng0013/kgg-dec.mirror @ b3bb5cb15933fb6c2c859665041d728e24777ca9:
// src/jobs.hpp and src/infra/infra.cpp. No AkiConvert code is used by this port.
package main

import (
	"bytes"
	"crypto/aes"
	blockcipher "crypto/cipher"
	"crypto/md5"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"io"
	"os"
	"strings"
	"unicode/utf8"
)

const keyDBPageSize = 0x400

var kugouDBMaster = []byte{0x1d, 0x61, 0x31, 0x45, 0xb2, 0x47, 0xbf, 0x7f, 0x3d, 0x18, 0x96, 0x72, 0x14, 0x4f, 0xe4, 0xbf}
var sqliteHeader = []byte("SQLite format 3\x00")

type kggLayout struct {
	audio      int64
	identifier string
}

func parseKggLayout(prefix []byte, size int64) (kggLayout, error) {
	magic := []byte{0x7c, 0xd5, 0x32, 0xeb, 0x86, 0x02, 0x7f, 0x4b, 0xa8, 0xaf, 0xa6, 0x8e, 0x0f, 0xff, 0x99, 0x14}
	if len(prefix) < 0x48 || !bytes.Equal(prefix[:16], magic) {
		return kggLayout{}, fail("invalid_data", "Invalid KGG header")
	}
	if binary.LittleEndian.Uint32(prefix[0x14:0x18]) != 5 {
		return kggLayout{}, fail("unsupported_version", "Unsupported KGG version")
	}
	begin := int64(binary.LittleEndian.Uint32(prefix[0x10:0x14]))
	idSize := uint64(binary.LittleEndian.Uint32(prefix[0x44:0x48]))
	end := uint64(0x48) + idSize
	if begin < 0x48 || begin >= size || begin > 16*1024*1024 || idSize == 0 || idSize > 256 || end > uint64(len(prefix)) || end > uint64(begin) {
		return kggLayout{}, fail("invalid_data", "Invalid KGG key identifier or audio bounds")
	}
	identifier := prefix[0x48:end]
	if !utf8.Valid(identifier) || strings.TrimSpace(string(identifier)) == "" {
		return kggLayout{}, fail("invalid_data", "Invalid KGG key identifier")
	}
	return kggLayout{begin, string(identifier)}, nil
}

func chooseKGG(header []byte, size int64, r request) (plan, error) {
	layout, err := parseKggLayout(header, size)
	if err != nil {
		return plan{}, err
	}
	if strings.TrimSpace(r.Key) == "" {
		return plan{}, fail("key_required", "The matching KGG EKey is required")
	}
	var material []byte
	if r.KeyType == "kgg_raw" {
		material, err = base64.StdEncoding.DecodeString(strings.TrimSpace(r.Key))
	} else {
		material, err = deriveKey([]byte(strings.TrimSpace(r.Key)))
	}
	if err != nil || len(material) < 8 || len(material) > 65536 {
		return plan{}, fail("bad_key", "KGG key validation failed")
	}
	var transform cipher
	if len(material) <= 300 {
		transform, err = newMapCipher(material)
	} else {
		transform, err = newRC4Cipher(material)
	}
	if err != nil {
		return plan{}, fail("bad_key", "KGG cipher initialization failed")
	}
	return plan{layout.audio, size - layout.audio, transform, "kgg-v5"}, nil
}

func dbMaterial(number uint32) ([16]byte, [16]byte) {
	var material [24]byte
	copy(material[:16], kugouDBMaster)
	binary.LittleEndian.PutUint32(material[16:20], number)
	binary.LittleEndian.PutUint32(material[20:24], 0x546c4173)
	key := md5.Sum(material[:])
	state := number + 1
	for pos := 0; pos < 16; pos += 4 {
		state = 0x9ef4*state - 0x7fffff07*(state/0xce26)
		if state&0x80000000 != 0 {
			state += 0x7fffff07
		}
		binary.LittleEndian.PutUint32(material[pos:pos+4], state)
	}
	return key, md5.Sum(material[:16])
}
func dbPageKey(number uint32) []byte { key, _ := dbMaterial(number); return key[:] }
func dbPageIV(number uint32) []byte  { _, iv := dbMaterial(number); return iv[:] }

func decryptDBPage(page []byte, number uint32) error {
	if len(page) != keyDBPageSize {
		return fail("invalid_data", "Incomplete Kugou database page")
	}
	segment := page
	var expected [8]byte
	if number == 1 {
		pageSize := uint32(page[16])<<8 | uint32(page[17])<<16
		if binary.LittleEndian.Uint32(page[20:24]) != 0x20204000 || pageSize < 512 || pageSize > 65536 || pageSize&(pageSize-1) != 0 {
			return fail("invalid_data", "Unrecognized Kugou database header")
		}
		copy(expected[:], page[16:24])
		copy(page[16:24], page[8:16])
		segment = page[16:]
	}
	key, iv := dbMaterial(number)
	aesBlock, err := aes.NewCipher(key[:])
	if err != nil {
		return err
	}
	blockcipher.NewCBCDecrypter(aesBlock, iv[:]).CryptBlocks(segment, segment)
	if number == 1 {
		if !bytes.Equal(page[16:24], expected[:]) {
			return fail("bad_key", "Kugou database integrity check failed")
		}
		copy(page[:16], sqliteHeader)
	}
	return nil
}

func decodeKugouDB(r request) (response, error) {
	source, err := os.Open(r.Source)
	if err != nil {
		return response{}, fail("read_error", "Cannot read Kugou key database")
	}
	defer source.Close()
	stat, err := source.Stat()
	if err != nil || !stat.Mode().IsRegular() || stat.Size() < keyDBPageSize || stat.Size() > 256*1024*1024 || stat.Size()%keyDBPageSize != 0 {
		return response{}, fail("invalid_data", "Invalid Kugou key database size")
	}
	page := make([]byte, keyDBPageSize)
	if _, err = io.ReadFull(source, page); err != nil {
		return response{}, err
	}
	encrypted := !bytes.HasPrefix(page, sqliteHeader)
	if encrypted {
		if err = decryptDBPage(page, 1); err != nil {
			return response{}, err
		}
	}
	target, err := os.OpenFile(r.Dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return response{}, fail("write_error", "Cannot create database copy")
	}
	complete := false
	defer func() {
		target.Close()
		if !complete {
			os.Remove(r.Dest)
		}
	}()
	checksum := sha256.New()
	output := io.MultiWriter(target, checksum)
	if _, err = output.Write(page); err != nil {
		return response{}, err
	}
	count := stat.Size() / keyDBPageSize
	for number := int64(2); number <= count; number++ {
		if _, err = io.ReadFull(source, page); err != nil {
			return response{}, err
		}
		if encrypted {
			if err = decryptDBPage(page, uint32(number)); err != nil {
				return response{}, err
			}
		}
		if _, err = output.Write(page); err != nil {
			return response{}, err
		}
	}
	if err = target.Close(); err != nil {
		return response{}, err
	}
	complete = true
	return response{OK: true, Format: "sqlite", Scheme: "kugou-key-database", Bytes: stat.Size(), SHA256: hex.EncodeToString(checksum.Sum(nil))}, nil
}
