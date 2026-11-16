package main

import (
    "bytes"
    "encoding/binary"
    "encoding/hex"
    "os"
    "path/filepath"
    "testing"
)

func TestMG3DNativeVectors(t *testing.T) {
    if string(miguKey("FEDCBA9876543210FEDCBA9876543210"))!="A21150B4815EE9DEF0586D838797F8AF" {t.Fatal("derived key differs from upstream native vector")}
    data,_:=hex.DecodeString("45444437493e373e4e4f4f4d3e4f425040464847484a5c4b5a4c4f4f5051575465646457695e575e6e6f6f6d5e6f627060666867686a7c6b7a6c6f6f7071777485")
    subCipher{[]byte("CB4E917FFEB2B4A056445F4B3544495E")}.Decrypt(data,31)
    for i,v:=range data {if v!=byte(i) {t.Fatalf("native transform differs at %d",i)}}
}

func TestMG3DRecoveryAndExclusiveOutput(t *testing.T) {
    wave:=make([]byte,4096);copy(wave,[]byte("RIFF"));binary.LittleEndian.PutUint32(wave[4:8],4088);copy(wave[8:],[]byte("WAVEfmt "))
    binary.LittleEndian.PutUint32(wave[16:20],16);binary.LittleEndian.PutUint16(wave[20:22],1);binary.LittleEndian.PutUint16(wave[22:24],2)
    binary.LittleEndian.PutUint32(wave[24:28],44100);copy(wave[36:],[]byte("data"));binary.LittleEndian.PutUint32(wave[40:44],4052)
    key:=miguKey("0123456789abcdef0123456789abcdef");encrypted:=append([]byte(nil),wave...)
    for i:=range encrypted {encrypted[i]+=key[i%32]}
    folder:=t.TempDir();src:=filepath.Join(folder,"test.mg3d");dest:=filepath.Join(folder,"test.wav")
    if err:=os.WriteFile(src,encrypted,0600);err!=nil {t.Fatal(err)}
    r,err:=decode(request{Source:src,Dest:dest,Family:"migu"});if err!=nil||!r.OK||r.Scheme!="mg3d-wav-recovered" {t.Fatal(r,err)}
    got,_:=os.ReadFile(dest);if !bytes.Equal(got,wave) {t.Fatal("stream recovery changed audio")}
    if _,err:=decode(request{Source:src,Dest:dest,Family:"migu"});err==nil {t.Fatal("existing file replaced")}
    got,_=os.ReadFile(dest);if !bytes.Equal(got,wave) {t.Fatal("existing output changed")}
}

func TestQMCRejectsTruncatedFooter(t *testing.T) {
    folder:=t.TempDir();src:=filepath.Join(folder,"test.mflac");dest:=filepath.Join(folder,"out.flac")
    for _,tag:=range []string{"QTag","STag"} {
        data:=make([]byte,128);binary.BigEndian.PutUint32(data[120:124],1000000);copy(data[124:],tag)
        _=os.WriteFile(src,data,0600)
        if _,err:=decode(request{Source:src,Dest:dest,Family:"qq"});err==nil {t.Fatal("invalid footer accepted")}
        if _,err:=os.Stat(dest);!os.IsNotExist(err) {t.Fatal("failed request left a file")}
    }
}

func TestKGGDoesNotUseLegacyCipher(t *testing.T) {
    h:=make([]byte,1024);copy(h,[]byte{0x7C,0xD5,0x32,0xEB,0x86,0x02,0x7F,0x4B,0xA8,0xAF,0xA6,0x8E,0x0F,0xFF,0x99,0x14})
    binary.LittleEndian.PutUint32(h[16:20],1024);binary.LittleEndian.PutUint32(h[20:24],5)
    if _,err:=chooseKGM(h,2000);err==nil {t.Fatal("KGG accepted as old KGM")}
}
