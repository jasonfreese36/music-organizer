"""Offline native decoders, bounded container probes and user-supplied media keys."""
from i18n import tr
import base64
import hashlib
import json
import os
import re
import struct
import sqlite3
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from media import read_audio,resource
from model import Cancel,Cancelled,bytes_hash,component,write_atomic
from platform_formats import ARCHIVE_NAMES,FAMILY_PLATFORM,KGM_MAGIC,PLATFORMS,VPR_MAGIC,detect_platform,original_stem,sniff_plain,suffix_family

KEY_TYPES={"qmc_ekey","qmc_raw","kgg_ekey","kgg_raw","migu_file_key","migu_mask"}
STATUS={"auto":tr('自动处理'),"decoded":tr('已解密'),"key_required":tr('需要密钥'),"bad_key":tr('密钥不匹配'),"unsupported_version":tr('版本未支持'),"invalid_data":tr('文件损坏或格式不符'),"disabled":tr('未启用'),"read_error":tr('读取失败'),"write_error":tr('写入失败')}


class PlatformError(ValueError):
    def __init__(self,code,message):self.code=code;super().__init__(message)


def vault_path():
    from catalog import state_dir
    return state_dir()/"Platform Keys.json"


def _entry(file,key,kind="qmc_ekey"):
    if not isinstance(file,str) or not file.strip() or len(file)>32768:raise ValueError(tr('密钥记录缺少有效文件名'))
    if not isinstance(key,str) or not 1<=len(key)<=131072 or kind not in KEY_TYPES:raise ValueError(tr('密钥类型或长度无效'))
    key=key.strip()
    if kind.startswith(("qmc","kgg")):
        try:data=base64.b64decode(key,validate=True)
        except Exception as exc:raise ValueError(tr('EKey / 原始密钥需要有效的 Base64 内容')) from exc
        if not 8<=len(data)<=65536:raise ValueError(tr('EKey / 原始密钥长度不符合要求'))
    elif not re.fullmatch(r"[0-9a-fA-F]{32}",key):raise ValueError(tr('咪咕密钥需要 32 个十六进制字符'))
    if kind=="migu_mask" and key!=key.upper():raise ValueError(tr('咪咕直接掩码需要大写十六进制字符'))
    return dict(file=file.strip(),key=key,key_type=kind,platform="qq" if kind.startswith("qmc") else "kugou" if kind.startswith("kgg") else "migu")


@lru_cache(maxsize=4)
def _read_kugou_db(filename,size,mtime):
    """Read only the explicitly supplied database; never open or change the original in SQLite."""
    if not 1024<=size<=256*1024**2:raise ValueError(tr('酷狗密钥数据库需要在 1 KB–256 MB 之间'))
    with tempfile.TemporaryDirectory(prefix="MusicOrganizer-Keys-") as scratch:
        target=Path(scratch)/"Keys.sqlite"
        request=dict(source=filename,dest=str(target),family="kugou_db")
        proc=subprocess.run([resource("tools/platformaudio.exe")],input=json.dumps(request,ensure_ascii=False).encode("utf-8"),
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:result=json.loads(proc.stdout)
        except ValueError as exc:raise ValueError(tr('无法读取酷狗密钥数据库')) from exc
        if not result.get("ok"):raise ValueError(tr('酷狗密钥数据库版本不支持或完整性校验失败'))
        if not target.is_file() or target.stat().st_size!=result.get("bytes") or bytes_hash(target,Cancel())!=result.get("sha256"):
            raise ValueError(tr('酷狗密钥数据库副本校验失败'))
        db=sqlite3.connect(target.as_uri()+"?mode=ro",uri=True)
        try:
            db.execute("PRAGMA query_only=ON");db.execute("PRAGMA trusted_schema=OFF")
            rows=db.execute("SELECT EncryptionKeyId, EncryptionKey FROM ShareFileItems WHERE EncryptionKeyId IS NOT NULL AND EncryptionKeyId != '' AND EncryptionKey IS NOT NULL AND EncryptionKey != '' LIMIT 50001").fetchall()
            if len(rows)>50000:raise ValueError(tr('密钥记录超过 50,000 条'))
            return tuple(_entry(str(k),str(v),"kgg_ekey") for k,v in rows)
        except sqlite3.Error as exc:raise ValueError(tr('数据库中没有可读取的酷狗歌曲密钥表')) from exc
        finally:db.close()


def parse_key_file(path):
    path=Path(path)
    stat=path.stat()
    with path.open("rb") as handle:head=handle.read(24)
    if path.suffix.lower()==".db" or head.startswith(b"SQLite format 3\0") or head[20:24]==bytes.fromhex("00402020"):
        return list(_read_kugou_db(str(path.resolve()),stat.st_size,stat.st_mtime_ns))
    if path.stat().st_size>16*1024**2:raise ValueError(tr('密钥文件超过 16 MB'))
    text=path.read_text(encoding="utf-8-sig")
    if text.lstrip().startswith(("{","[")):
        doc=json.loads(text)
        if isinstance(doc,dict) and "entries" in doc:
            if doc.get("schema",1)!=1:raise ValueError(tr('不支持此密钥文件版本'))
            doc=doc["entries"]
        if isinstance(doc,dict):
            rows=[dict(file=k,key=v) if isinstance(v,str) else dict(v,file=k) for k,v in doc.items()]
        elif isinstance(doc,list):rows=doc
        else:raise ValueError(tr('无法识别密钥记录'))
        if len(rows)>50000:raise ValueError(tr('密钥记录超过 50,000 条'))
        result=[]
        for row in rows:
            if not isinstance(row,dict):raise ValueError(tr('密钥记录格式无效'))
            kind=row.get("key_type","migu_file_key" if row.get("platform")=="migu" or row.get("file_key") else "kgg_ekey" if row.get("platform")=="kugou" else "qmc_ekey")
            result.append(_entry(row.get("file",row.get("filename","")),row.get("key",row.get("ekey",row.get("file_key",""))),kind))
        return result
    result=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):continue
        kugou="\t" not in line and "$" in line
        parts=line.split("$" if kugou else "\t",1)
        if len(parts)!=2:raise ValueError(tr('文本密钥文件需为“文件名 TAB QQ EKey”或“酷狗 KeyId$EKey”，每行一条'))
        result.append(_entry(parts[0],parts[1],"kgg_ekey" if kugou else "qmc_ekey"))
        if len(result)>50000:raise ValueError(tr('密钥记录超过 50,000 条'))
    return result


def _norm(value):return os.path.normcase(str(value).replace("/","\\")).casefold()


def _names(value):
    value=str(value).replace("\\","/")
    name=value.rsplit("/",1)[-1]
    return {_norm(value),_norm(name),_norm(original_stem(name))}


class KeyStore:
    def __init__(self,extra="",include_local=True):
        self.entries=[];self.issues=[];self.exact={};self.names={}
        files=([vault_path()] if include_local else [])+([Path(extra)] if extra else [])
        for file in dict.fromkeys(files):
            if file==vault_path() and not file.exists():continue
            try:self.entries.extend(parse_key_file(file))
            except Exception as exc:self.issues.append(f"{file.name}：{exc}")
        for row in self.entries:
            self.exact.setdefault((row["platform"],_norm(row["file"])),[]).append(row)
            for name in _names(row["file"]):self.names.setdefault((row["platform"],name),[]).append(row)

    def lookup(self,path,platform,key_id=""):
        exact=self.exact.get((platform,_norm(Path(path).resolve())),[])
        rows=exact or [r for name in _names(path)|(_names(key_id) if key_id else set()) for r in self.names.get((platform,name),[])]
        unique={(r["key_type"],r["key"]) for r in rows}
        if len(unique)>1:raise PlatformError("bad_key",tr('找到多个不同的匹配密钥，请用“添加单曲密钥”为此文件指定准确记录'))
        if not unique:return None
        kind,key=next(iter(unique));return dict(key_type=kind,key=key)


def add_local_key(file,key,kind):
    row=_entry(str(Path(file).resolve()),key,kind)
    path=vault_path()
    rows=parse_key_file(path) if path.exists() else []
    rows=[r for r in rows if not (r["platform"]==row["platform"] and _norm(r["file"])==_norm(row["file"]))]
    rows.append(row)
    write_atomic(path,json.dumps(dict(schema=1,entries=rows),ensure_ascii=False,indent=2).encode("utf-8"))
    return len(rows)


def _mg_recoverable(header,size):
    for pos in range(32,min(640,len(header)-31),32):
        key=header[pos:pos+32]
        if any(c not in b"0123456789ABCDEF" for c in key):continue
        data=bytes((v-key[i%32])&255 for i,v in enumerate(header[:256]))
        if len(data)<64 or data[:4]!=b"RIFF" or data[8:16]!=b"WAVEfmt ":continue
        if struct.unpack_from("<I",data,16)[0] not in (16,18,40):continue
        if not 1<=struct.unpack_from("<H",data,22)[0]<=32 or not 8000<=struct.unpack_from("<I",data,24)[0]<=768000:continue
        if struct.unpack_from("<I",data,4)[0]+8<=size:return True
    return False


def probe_platform(path,family=None,keys=None):
    path=Path(path);family=family or detect_platform(path);platform=FAMILY_PLATFORM.get(family,"")
    if not family:return {}
    size=path.stat().st_size
    with path.open("rb") as f:
        head=f.read(1024)
        info=dict(family=family,platform=platform,name=PLATFORMS.get(platform,tr('平台音频')),state="auto",version="",key_id="",plain=sniff_plain(head),detail=tr('整理时自动还原并校验音频'))
        if size<16:info.update(state="invalid_data",detail=tr('文件过短，保留原件'));return info
        if info["plain"]:info.update(version=tr('普通音频'),detail=tr('文件内已是普通音频，自动恢复正确扩展名'));return info
        if family=="ncm":
            info["version"]="NCM"
            if not head.startswith(b"CTENFDAM"):info.update(state="invalid_data",detail=tr('NCM 文件头不符合格式'))
        elif family=="netease_uc":info["version"]=tr('UC 缓存')
        elif family=="qq":
            f.seek(-min(size,16),2);tail=f.read(16)
            if tail.endswith(b"musicex\x00") and len(tail)==16:
                n,v=struct.unpack_from("<II",tail)
                info.update(version=f"musicex v{v}",state="key_required",detail=tr('QQ 新版文件需要对应的本地 EKey'))
                if v!=1:info.update(state="unsupported_version",detail=tr('此 musicex 版本未支持'))
                elif not 192<=n<min(size,1024**2):info.update(state="invalid_data",detail=tr('musicex 尾部长度无效'))
                else:
                    f.seek(size-n+0x48);name=f.read(100)
                    info["key_id"]=name.decode("utf-16-le",errors="replace").split("\x00",1)[0]
            elif tail.endswith(b"STag"):info.update(version="STag",state="key_required",detail=tr('QQ STag 文件需要对应的本地 EKey'))
            elif tail.endswith(b"QTag"):info["version"]=tr('QTag 内嵌密钥')
            else:info["version"]=tr('QMC / 内嵌密钥')
        elif family=="qq_tm":info["version"]=tr('TM 头部还原')
        elif family=="kugou":
            if len(head)<60 or head[:16] not in (KGM_MAGIC,VPR_MAGIC):info.update(state="invalid_data",detail=tr('酷狗文件头不符合 KGM/VPR 格式'))
            else:
                v=struct.unpack_from("<I",head,20)[0];info["version"]=f"KGM v{v}"
                if v==5:
                    info.update(version="KGG / KGM v5",state="key_required",detail=tr('需要对应本地 EKey；可导入 KGMusicV3.db、kgg.keys 或添加单曲密钥'))
                    n=struct.unpack_from("<I",head,0x44)[0] if len(head)>=0x48 else 0
                    offset=struct.unpack_from("<I",head,16)[0]
                    if not 1<=n<=256 or 0x48+n>min(len(head),offset) or not offset<size:info.update(state="invalid_data",detail=tr('KGG 密钥标识或音频偏移无效'))
                    else:
                        try:info["key_id"]=head[0x48:0x48+n].decode("utf-8")
                        except UnicodeError:info.update(state="invalid_data",detail=tr('KGG 密钥标识编码无效'))
                elif v>5:info.update(state="unsupported_version",detail=tr('此酷狗加密版本尚未支持，原件保留'))
        elif family=="kuwo":info["version"]="KWM"
        elif family=="migu":
            info["version"]="MG3D"
            if not _mg_recoverable(head,size):info.update(state="key_required",detail=tr('未发现旧版 WAV 恢复参数，需要此文件的 fileKey'))
            else:info["detail"]=tr('发现 MG3D WAV 恢复参数，整理时验证并还原')
        elif family=="migu_mgm":info.update(version="MGM",state="unsupported_version",detail=tr('MGM 与 MG3D 是不同方案，此版本尚未支持；原件保留'))
    if keys and info["state"] in ("auto","key_required"):
        try:
            if keys.lookup(path,platform,info["key_id"]):info.update(state="auto",detail=tr('已找到匹配的本地密钥，整理时验证并还原'))
        except PlatformError as exc:info.update(state=exc.code,detail=str(exc))
    return info


def decrypt_platform(item,scratch,tools,settings,cancel,keys):
    from inventory import infer_track
    item.check();cancel.check()
    info=probe_platform(item.path,item.crypto.get("family") or None,keys)
    if info["state"] in ("invalid_data","unsupported_version","bad_key"):raise PlatformError(info["state"],info["detail"])
    if info["family"]=="ncm" and not info["plain"]:
        from formats import decrypt_ncm
        tracks=decrypt_ncm(item,scratch,tools,cancel)
        scheme="ncmdump"
    else:
        selected=keys.lookup(item.path,info["platform"],info.get("key_id","")) or {}
        temp=scratch/"Decoded.bin"
        request=dict(source=str(item.path),dest=str(temp),family=info["family"],**selected)
        data=tools.run([tools.platformaudio],cancel,input_data=json.dumps(request,ensure_ascii=False).encode("utf-8"))
        try:result=json.loads(data)
        except ValueError as exc:raise PlatformError("invalid_data",tr('解密工具未返回有效结果')) from exc
        if not result.get("ok"):
            code=result.get("code","invalid_data")
            messages={"key_required":tr('缺少此文件的匹配密钥，请在高级设置 → 平台音频中添加或导入'), "bad_key":tr('密钥与文件不匹配，或此加密变体未支持'), "unsupported_version":tr('此加密版本尚未支持，原件已保留'), "invalid_data":tr('加密容器损坏或不符合格式')}
            raise PlatformError(code,messages.get(code,tr('平台音频读取失败')))
        ext=result.get("format")
        if ext not in {"flac","mp3","m4a","aac","ogg","ape","wma","wav","wv","ra"}:raise PlatformError("invalid_data",tr('解密后格式无法识别'))
        if not temp.is_file() or temp.stat().st_size!=result.get("bytes") or bytes_hash(temp,cancel)!=result.get("sha256"):
            raise PlatformError("invalid_data",tr('解密结果的字节校验失败'))
        target=scratch/(component(original_stem(item.path),90)+"."+ext);os.replace(temp,target)
        profile,tags,cover=read_audio(target,tools,cancel)
        if profile.seconds<=0 or profile.rate<=0 or profile.channels<=0:raise PlatformError("invalid_data",tr('解密结果不包含有效音频'))
        track=infer_track(item,target,profile,tags,cover)
        track.metadata_source=info["name"]+tr(' · 解密后原始标签') if tags else tr('文件名推断')
        tracks=[track];scheme=result["scheme"]
    if settings.decrypt_verify:
        for track in tracks:tools.verify_audio(track.path,track.profile,cancel)
    item.check()
    return tracks,dict(platform=info["platform"],name=info["name"],state="decoded",version=info["version"],scheme=scheme,detail=tr('音频已还原')+(tr('并通过完整解码校验') if settings.decrypt_verify else tr('并通过格式及字节校验')))
