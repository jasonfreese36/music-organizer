"""Generated offline platform fixtures; no real music or credentials are modified.

QMC encoders follow the public Unlock Music vectors, KGG container follows
kgg-dec (MIT), and the MG3D known answer follows TuneWeave (MIT).
These fixture writers are deliberately independent of the production decoder.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import sqlite3
import struct
import threading
import time
from dataclasses import replace
from pathlib import Path

from PIL import Image

from engine import Organizer
from inventory import scan
from media import Tools,make_cover,patch_tags,payload_hash,read_audio
from model import Cancel,Cancelled,Settings
from platform_audio import KeyStore,parse_key_file,probe_platform
from platform_formats import KGM_MAGIC,VPR_MAGIC,detect_platform

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"native/platformaudio/testdata"


def snapshot(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}


def qmc(data,key=None):
    """Symmetric static/map/RC4 reference for fixture encoding."""
    if key is None:
        raw=(DATA/"qmc0_static_raw.bin").read_bytes()
        plain=(DATA/"qmc0_static_target.bin").read_bytes()
        mask=bytes(a^b for a,b in zip(raw[:128],plain[:128]))
        assert len(mask)==128
        return bytes(v^mask[(i if i<=32767 else i%32767)%128] for i,v in enumerate(data))
    if len(key)<=300:
        result=bytearray(data)
        for i in range(len(result)):
            pos=i if i<=32767 else i%32767
            idx=(pos*pos+71214)%len(key);shift=(idx+4)%8
            result[i]^=((key[idx]<<shift)|(key[idx]>>shift))&255
        return bytes(result)
    n=len(key);box=[i&255 for i in range(n)];j=0
    for i in range(n):
        j=(j+box[i]+key[i])%n;box[i],box[j]=box[j],box[i]
    h=1
    for v in key:
        if not v:continue
        nxt=(h*v)&0xffffffff
        if nxt==0 or nxt<=h:break
        h=nxt
    def skip(i):return int(h/((i+1)*key[i%n])*100)%n if key[i%n] else 0
    result=bytearray(data)
    for i in range(min(128,len(data))):result[i]^=key[skip(i)]
    pos=128
    while pos<len(data):
        count=min(5120-pos%5120,len(data)-pos);state=box.copy();j=k=0;discard=pos%5120+skip(pos//5120)
        for i in range(discard+count):
            j=(j+1)%n;k=(k+state[j])%n;state[j],state[k]=state[k],state[j]
            if i>=discard:result[pos+i-discard]^=state[(state[j]+state[k])%n]
        pos+=count
    return bytes(result)


def kgm(data,version=3,legacy=False,vpr=False):
    header=bytearray(1024);header[:16]=VPR_MAGIC if vpr else KGM_MAGIC
    struct.pack_into("<III",header,16,1024,version,1)
    header[28:44]=bytes(range(16));header[44:60]=bytes(range(16,32))
    def scramble(v):return (v^(v<<4))&255
    def pairmd5(b):
        d=hashlib.md5(b).digest();return b"".join(d[i:i+2] for i in range(14,-1,-2))
    if not legacy:
        slot=pairmd5(bytes.fromhex("6c2c2f27"));own=pairmd5(header[44:60])+b"\x6b"
        encoded=bytes(scramble(v^slot[i%16]^(i&255)^((i>>8)&255)^((i>>16)&255)^((i>>24)&255))^own[i%17] for i,v in enumerate(data))
    else:
        # Reference constant tables, parsed as data rather than calling the reader.
        source=(ROOT/"native/platformaudio/kgm_tables.go").read_text()
        def table(name):
            section=source.split("var "+name+" =",1)[1].split("}",1)[0]
            return bytes(int(v,16) for v in re.findall(r"0x([0-9A-Fa-f]{2})",section))
        t1,t2,mend,diff=map(table,("kgmTable1","kgmTable2","kgmMask","vprDiff"))
        own=bytes(header[28:44])+b"\0";result=bytearray(data)
        for i,v in enumerate(data):
            n=i>>4;mask=0
            while n>=17:mask^=t1[n%272];n>>=4;mask^=t2[n%272];n>>=4
            mask^=mend[i%272]
            result[i]=scramble(v^(diff[i%17] if vpr else 0)^scramble(mask))^own[i%17]
        encoded=bytes(result)
    return bytes(header)+encoded


def kgg(data,key,key_id="fixture-kgg-key",version=5):
    h=bytearray(1024);h[:16]=KGM_MAGIC;struct.pack_into("<II",h,16,1024,version)
    name=key_id.encode();struct.pack_into("<I",h,0x44,len(name));h[0x48:0x48+len(name)]=name
    return bytes(h)+qmc(data,key)


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    source=root/"Source 中文";originals=root/"Plain fixtures";direct=root/"Direct decoded"
    for folder in (source,originals,direct):folder.mkdir(exist_ok=True)
    cancel=Cancel();tools=Tools();tools.verify(cancel)
    buf=io.BytesIO();Image.new("RGB",(160,160),(32,76,112)).save(buf,"PNG");cover=make_cover(buf.getvalue(),"fixture")
    expected={};entries=[];cases=[]
    def audio(name,ext="flac",silence=False,long=False):
        p=originals/(name+"."+ext)
        duration=12 if long else 3
        signal="anullsrc=r=44100:cl=stereo" if silence else f"anoisesrc=r=44100:d={duration}:a=0.1:seed=77"
        codec={"flac":"flac","mp3":"libmp3lame","m4a":"aac","wav":"pcm_s16le"}[ext]
        tools.ff(["-y","-f","lavfi","-i",signal,"-t",str(duration),"-ac","2","-c:a",codec,p],cancel)
        if ext!="wav":patch_tags(p,dict(title=name,artist="Platform Test",albumartist="Platform Test",album=name,date="2024",tracknumber="1",discnumber="1",genre="Test"),cover)
        return p
    def fixture(name,ext,encoder,plainext="flac",silence=False,long=False):
        plain=audio(name,plainext,silence,long);path=source/(name+ext);path.write_bytes(encoder(plain.read_bytes()))
        if long:assert path.stat().st_size>1024**2,"Fixture must cross native I/O chunk boundary"
        expected[path.name]=plain;cases.append(path);return path
    map_key=(DATA/"mflac_map_key.bin").read_bytes();map_ekey=(DATA/"mflac_map_key_raw.bin").read_text().strip()
    rc4_key=(DATA/"mflac0_rc4_key.bin").read_bytes();rc4_ekey=(DATA/"mflac0_rc4_key_raw.bin").read_text().strip()
    fixture("QQ static",".qmc0",qmc,"mp3")
    fixture("QQ static boundary",".qmcflac",qmc,long=True)
    fixture("QQ map embedded",".mflac",lambda b:qmc(b,map_key)+map_ekey.encode()+struct.pack("<I",len(map_ekey)))
    meta=(rc4_ekey+",123456,2").encode()
    fixture("QQ RC4 QTag",".mflac0",lambda b:qmc(b,rc4_key)+meta+struct.pack(">I",len(meta))+b"QTag",long=True)
    stag=b"12345,2,mid123"
    external=fixture("QQ STag local",".mgg",lambda b:qmc(b,map_key)+stag+struct.pack(">I",len(stag))+b"STag")
    entries.append(dict(file=external.name,key=map_ekey,key_type="qmc_ekey"))
    footer=bytearray(192);filename="musicex-internal-id";footer[0x48:0x48+len(filename)*2]=filename.encode("utf-16-le")
    struct.pack_into("<II8s",footer,176,192,1,b"musicex\0")
    fixture("QQ musicex compound",".mflac0.flac",lambda b:qmc(b,rc4_key)+footer)
    entries.append(dict(file=filename,key=base64.b64encode(rc4_key).decode(),key_type="qmc_raw"))
    fixture("QQ TM",".tm2",lambda b:b"QQMUxxxx"+b[8:],"m4a")
    fixture("NetEase UC",".uc",lambda b:bytes(v^0xa3 for v in b),"mp3")
    fixture("Kugou v3",".kgm",kgm)
    fixture("Kugou legacy",".kgma",lambda b:kgm(b,legacy=True))
    fixture("Kugou VPR",".vpr",lambda b:kgm(b,legacy=True,vpr=True),"mp3")
    v5=fixture("Kugou KGG",".kgg.flac",lambda b:kgg(b,rc4_key))
    entries.append(dict(file="fixture-kgg-key",key=rc4_ekey,key_type="kgg_ekey"))
    def kwm(b):
        h=bytearray(1024);h[:16]=b"yeelion-kuwo-tme";struct.pack_into("<Q",h,24,1234567890)
        digits=b"1234567890";key=bytes(v^digits[i%len(digits)] for i,v in enumerate(b"MoOtOiTvINGwd2E6n0E1i7L5t2IoOoNk"))
        return bytes(h)+bytes(v^key[i%32] for i,v in enumerate(b))
    fixture("Kuwo legacy",".kwm",kwm)
    file_key="0123456789abcdef0123456789abcdef"
    mask=hashlib.md5(("AC89EC47A70B76F307CB39A0D74BCCB0"+file_key).encode()).hexdigest().upper().encode()
    assert mask==b"CB4E917FFEB2B4A056445F4B3544495E"
    def mg3d(b):return bytes((v+mask[i%32])&255 for i,v in enumerate(b))
    fixture("Migu WAV recovery",".mg3d",mg3d,"wav",silence=True)
    keyed=fixture("Migu keyed",".mg3d",mg3d)
    entries.append(dict(file=keyed.name,key=file_key,key_type="migu_file_key"))
    fixture("Already plain",".qmc3",lambda b:b,"mp3")
    keyfile=root/"Keys.json";keyfile.write_text(json.dumps(dict(schema=1,entries=entries)),encoding="utf-8")
    keys=KeyStore(keyfile,include_local=False)
    before=snapshot(source)
    # Whole-file equality catches tail/header/chunk boundary and metadata damage.
    for path in cases:
        info=probe_platform(path,keys=keys);assert info["state"]=="auto",(path,info)
        selected=keys.lookup(path,info["platform"],info.get("key_id","")) or {}
        out=direct/(path.name+".decoded")
        result=json.loads(tools.run([tools.platformaudio],cancel,input_data=json.dumps(dict(source=str(path),dest=str(out),family=info["family"],**selected)).encode()))
        assert result.get("ok"),(path,result)
        assert out.read_bytes()==expected[path.name].read_bytes(),path.name
    # Failure fixtures are archived, reported, and do not prevent good files finishing.
    missing=source/"Missing QQ key.mflac";missing.write_bytes(qmc(originals.joinpath("QQ STag local.flac").read_bytes(),map_key)+stag+struct.pack(">I",len(stag))+b"STag")
    wrong=source/"Wrong Migu key.mg3d";wrong.write_bytes(keyed.read_bytes())
    entries.append(dict(file=wrong.name,key="0"*32,key_type="migu_file_key"))
    unsupported=source/"New Kugou version.kgg";unsupported.write_bytes(kgg(b"x"*1024,map_key,version=6))
    (source/"Unsupported Migu.mgm").write_bytes(b"MGM unsupported encrypted fixture"*8)
    (source/"Malformed QQ.mflac").write_bytes(b"x"*120+struct.pack(">I",1000000)+b"QTag")
    truncated=source/"Truncated.qq.qmcflac";truncated.write_bytes(qmc(originals.joinpath("QQ static boundary.flac").read_bytes()[:25000]))
    keyfile.write_text(json.dumps(dict(schema=1,entries=entries)),encoding="utf-8")
    before=snapshot(source)
    settings=Settings(online=False,workers=4,decrypt_workers=2,platform_key_file=str(keyfile),keep_sidecars=False)
    items,skipped=scan(source,tools,cancel,settings=settings);assert not skipped,skipped
    states={i.path.name:i.crypto["state"] for i in items};assert states[missing.name]=="key_required"
    events=[];dest=root/"Organized"
    active=peak=0;meter_lock=threading.Lock();original_run=tools.run
    def measured(args,*a,**kw):
        nonlocal active,peak
        native=Path(args[0])==tools.platformaudio
        if native:
            with meter_lock:active+=1;peak=max(peak,active)
        try:return original_run(args,*a,**kw)
        finally:
            if native:
                with meter_lock:active-=1
    tools.run=measured
    report=Organizer(source,dest,items,settings,tools,cancel,lambda *a:events.append(a),cache_folder=root/"Cache").run()
    tools.run=original_run
    assert 1<=peak<=2,peak
    data=json.loads((dest/"Library Records/Latest Run.json").read_text(encoding="utf-8"))
    assert report["encrypted_decoded"]==len(cases),(report,data["errors"])
    assert report["errors"]==6,(report,data["errors"])
    assert len(list((dest/"Albums").rglob("*.flac")))+len(list((dest/"Albums").rglob("*.mp3")))+len(list((dest/"Albums").rglob("*.m4a")))==len(cases),report
    for row in data["tracks"]:
        target=dest/row["target"]
        profile,tags,covered=read_audio(target,tools,cancel)
        assert profile.seconds>0
        if tags.get("title")!="Migu WAV recovery":assert covered,(target,tags)
    archived=list((dest/"Disc Archives/Platform Originals").rglob("*"));archived=[p for p in archived if p.is_file()]
    assert len(archived)==len(items),(len(archived),len(items))
    for p in archived:assert hashlib.sha256(p.read_bytes()).hexdigest()==before[p.name]
    for p in (dest/"Library Records").glob("*"):
        if p.is_file():
            text=p.read_text(encoding="utf-8-sig")
            for entry in entries:assert entry["key"] not in text,"Key leaked to report"
    repeat=Organizer(source,dest,items,settings,tools,cancel,cache_folder=root/"Cache").run()
    assert repeat["written"]==0 and repeat["encrypted_decoded"]==len(cases),repeat
    disabled=Organizer(source,root/"Disabled",items,replace(settings,decrypt_enabled=False),tools,cancel,cache_folder=root/"Cache").run()
    assert disabled["errors"]==0 and disabled["encrypted_decoded"]==0 and disabled["written"]==0,disabled
    # Explicit database and native kgg.keys import, without changing original files.
    dbpath=root/"KGMusicV3.db";db=sqlite3.connect(dbpath);db.execute("PRAGMA page_size=1024")
    db.execute("CREATE TABLE ShareFileItems (EncryptionKeyId TEXT, EncryptionKey TEXT)")
    db.execute("INSERT INTO ShareFileItems VALUES (?,?)",("fixture-kgg-key",rc4_ekey));db.commit();db.close()
    dbhash=hashlib.sha256(dbpath.read_bytes()).hexdigest();assert parse_key_file(dbpath)[0]["key"]==rc4_ekey
    assert KeyStore(dbpath,include_local=False).lookup(v5,"kugou","fixture-kgg-key")["key"]==rc4_ekey
    assert hashlib.sha256(dbpath.read_bytes()).hexdigest()==dbhash
    nativekeys=root/"kgg.keys";nativekeys.write_text("fixture-kgg-key$"+rc4_ekey+"\n")
    assert parse_key_file(nativekeys)[0]["platform"]=="kugou"
    # A real native process is interrupted; it cannot publish anything to Albums.
    from unittest.mock import patch
    import media
    large=root/"Cancellation.mflac";chunk=qmc(originals.joinpath("QQ musicex compound.flac").read_bytes()[:65536],rc4_key)
    with large.open("wb") as handle:
        for _ in range(1024):handle.write(chunk)
    stopped=Cancel();children=[];timers=[];real_popen=media.subprocess.Popen
    def spawn(*args,**kwargs):
        process=real_popen(*args,**kwargs);children.append(process)
        timer=threading.Timer(.02,stopped.stop);timer.start();timers.append(timer)
        return process
    request=dict(source=str(large),dest=str(root/"Cancelled.tmp"),family="qq",key_type="qmc_raw",key=base64.b64encode(rc4_key).decode())
    with patch("media.subprocess.Popen",spawn):
        try:tools.run([tools.platformaudio],stopped,input_data=json.dumps(request).encode())
        except Cancelled:pass
        else:raise AssertionError("Cancellation was ignored")
    for timer in timers:timer.join()
    assert children and all(child.poll() is not None for child in children),"Native decoder remained running"
    assert snapshot(source)==before,"Source changed"
    result=dict(five_platforms=True,whole_file_roundtrips=len(cases),qmc_static_map_rc4=True,tag_footers=True,kgg_v5=True,
                migu_recovery_and_key=True,archives_verified=True,failures_isolated=6,truncated_audio_rejected=True,
                repeat_without_duplicates=True,disabled_archive_only=True,explicit_key_database_readonly=True,no_key_in_reports=True,source_unchanged=True,
                bounded_native_workers=peak,cancellation_stops_native_process=True,
                first=report,repeat=repeat)
    (root/"test-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    run(p.parse_args().root.resolve())
