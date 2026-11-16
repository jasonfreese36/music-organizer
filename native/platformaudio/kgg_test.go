// Copyright (c) 2026 Music Organizer contributors. MIT.
package main

import (
	"bytes"
	"crypto/aes"
	blockcipher "crypto/cipher"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

func TestKGGKeyRequiredAndBounds(t *testing.T) {
	h := make([]byte, 1024)
	copy(h, []byte{0x7C, 0xD5, 0x32, 0xEB, 0x86, 0x02, 0x7F, 0x4B, 0xA8, 0xAF, 0xA6, 0x8E, 0x0F, 0xFF, 0x99, 0x14})
	binary.LittleEndian.PutUint32(h[16:20], 1024)
	binary.LittleEndian.PutUint32(h[20:24], 5)
	binary.LittleEndian.PutUint32(h[0x44:0x48], 3)
	copy(h[0x48:], []byte("id1"))
	_, err := chooseKGG(h, 2048, request{})
	if f, ok := err.(*failure); !ok || f.code != "key_required" {
		t.Fatal("valid KGG without key must request key", err)
	}
	binary.LittleEndian.PutUint32(h[0x44:0x48], 0xffffffff)
	if _, err = chooseKGG(h, 2048, request{}); err == nil {
		t.Fatal("invalid key id bounds accepted")
	}
}

func TestKugouDBPagesAndIntegrity(t *testing.T) {
	plain := make([]byte, 3072)
	for i := range plain {
		plain[i] = byte(i*31 + 17)
	}
	copy(plain, sqliteHeader)
	copy(plain[16:24], []byte{4, 0, 1, 1, 0, 64, 32, 32})
	encrypted := append([]byte(nil), plain...)
	for n := uint32(1); n <= 3; n++ {
		start := int(n-1) * 1024
		page := encrypted[start : start+1024]
		skip := 0
		if n == 1 {
			skip = 16
		}
		block, _ := aes.NewCipher(dbPageKey(n))
		blockcipher.NewCBCEncrypter(block, dbPageIV(n)).CryptBlocks(page[skip:], page[skip:])
		if n == 1 {
			copy(page[8:16], page[16:24])
			copy(page[16:24], plain[16:24])
			copy(page[:8], []byte("testsalt"))
		}
	}
	folder := t.TempDir()
	src := filepath.Join(folder, "KGMusicV3.db")
	dest := filepath.Join(folder, "plain.sqlite")
	_ = os.WriteFile(src, encrypted, 0600)
	result, err := decodeKugouDB(request{Source: src, Dest: dest})
	if err != nil || !result.OK {
		t.Fatal(result, err)
	}
	got, _ := os.ReadFile(dest)
	if !bytes.Equal(got, plain) {
		t.Fatal("database pages changed after roundtrip")
	}
	if _, err = decodeKugouDB(request{Source: src, Dest: dest}); err == nil {
		t.Fatal("existing database output overwritten")
	}
	encrypted[24] ^= 0xff
	_ = os.WriteFile(src, encrypted, 0600)
	_ = os.Remove(dest)
	if _, err = decodeKugouDB(request{Source: src, Dest: dest}); err == nil {
		t.Fatal("database integrity failure accepted")
	}
	if _, err = os.Stat(dest); !os.IsNotExist(err) {
		t.Fatal("invalid database left plaintext output")
	}
}

func TestTMBoxLengths(t *testing.T) {
	for _, size := range []int{28, 32, 40} {
		h := make([]byte, 128)
		copy(h, []byte("QQMUxxxx"))
		binary.BigEndian.PutUint32(h[size:size+4], 8)
		copy(h[size+4:], []byte("free"))
		got := recoverTMHeader(h, 2048)
		if int(binary.BigEndian.Uint32(got[:4])) != size || string(got[4:]) != "ftyp" {
			t.Fatal(size, got)
		}
	}
}
