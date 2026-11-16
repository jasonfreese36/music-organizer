"""Declarative, bounded conversion rules. No user code or expression evaluation."""
from i18n import tr
import copy
import math

FORMATS = {"flac","mp3","aac","alac","wav","dsd","ape","wavpack","tta","tak","wma","vorbis","opus","mp2","ac3","dts","mpc","other"}
FIELDS = {"format","bitrate","sample_rate","bits","channels","size_mb","lossless"}
NUMERIC = {"gt","ge","lt","le","eq"}
ACTION_VALUES = {
    "format":{"inherit","flac","mp3","aac"},
    "resample_mode":{"inherit","preserve","limit","fixed"},
    "channels":{"inherit","preserve","stereo","mono"},
    "mp3_mode":{"inherit","vbr","cbr"},
}


def validate_rules(rules):
    if not isinstance(rules,(list,tuple)) or len(rules)>100:
        raise ValueError(tr('规则最多支持 100 条'))
    result=[]
    for raw in rules:
        if not isinstance(raw,dict):raise ValueError(tr('规则格式无效'))
        r=copy.deepcopy(raw)
        if set(r)-{"name","enabled","match","conditions","actions"}:raise ValueError(tr('规则含未知设置'))
        if not isinstance(r.get("name"),str) or not r["name"].strip() or len(r["name"])>80:raise ValueError(tr('请填写 1–80 字的规则名称'))
        r.setdefault("enabled",True);r.setdefault("match","all")
        if not isinstance(r["enabled"],bool) or r["match"] not in ("all","any"):raise ValueError(tr('规则开关或条件关系无效'))
        conditions=r.get("conditions")
        if not isinstance(conditions,list) or not 1<=len(conditions)<=8:raise ValueError(tr('每条规则需要 1–8 个条件'))
        for c in conditions:
            if not isinstance(c,dict) or set(c)!={"field","op","value"}:raise ValueError(tr('规则条件格式无效'))
            field,op,value=c["field"],c["op"],c["value"]
            if field not in FIELDS:raise ValueError(tr('未知的规则条件'))
            if field in ("format","lossless"):
                if op not in ("is","is_not"):raise ValueError(tr('此条件只支持等于或不等于'))
                if field=="format" and value not in FORMATS or field=="lossless" and not isinstance(value,bool):raise ValueError(tr('规则条件值无效'))
            elif op not in NUMERIC or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1e9:
                raise ValueError(tr('规则数值需要在 0–1,000,000,000 范围内'))
        actions=r.get("actions")
        if not isinstance(actions,dict) or not actions:raise ValueError(tr('请为规则选择至少一个动作'))
        for field,value in actions.items():
            if field in ACTION_VALUES:
                if value not in ACTION_VALUES[field]:raise ValueError(tr('规则动作选项无效'))
            elif field=="sample_rate":
                if type(value)!=int or value not in (8000,16000,22050,24000,32000,44100,48000,88200,96000,176400,192000,352800,384000):raise ValueError(tr('规则采样率无效'))
            elif field=="pcm_bits":
                if type(value)!=int or value not in (0,16,24,32):raise ValueError(tr('规则位深无效'))
            elif field=="mp3_kbps":
                if type(value)!=int or value not in (64,96,128,160,192,224,256,320):raise ValueError(tr('规则 MP3 码率无效'))
            elif field=="mp3_vbr":
                if type(value)!=int or not 0<=value<=9:raise ValueError(tr('规则 VBR 品质无效'))
            elif field=="aac_kbps":
                if type(value)!=int or not 96<=value<=512:raise ValueError(tr('规则 AAC 码率无效'))
            elif field=="reencode_lossy":
                if not isinstance(value,bool):raise ValueError(tr('规则重新编码开关无效'))
            else:raise ValueError(tr('未知的规则动作'))
        if all(v=="inherit" for v in actions.values()):raise ValueError(tr('请为规则选择至少一个实际动作'))
        result.append(r)
    return result


def source_format(profile):
    codec=profile.codec
    if codec.startswith("dsd"):return "dsd"
    if codec.startswith("pcm_"):return "wav"
    if codec.startswith("wma"):return "wma"
    if codec.startswith("musepack"):return "mpc"
    return codec if codec in FORMATS else "other"


def matches(rule,track):
    p=track.profile
    values={"format":source_format(p),"bitrate":p.bitrate/1000 if p.bitrate else None,
            "sample_rate":p.rate,"bits":p.bits if p.lossless and p.bits else None,"channels":p.channels,
            "size_mb":track.source.size/1024**2,"lossless":p.lossless}
    tests=[]
    for c in rule["conditions"]:
        actual=values[c["field"]];expected=c["value"];op=c["op"]
        if actual is None:tests.append(False);continue
        tests.append({"is":lambda:actual==expected,"is_not":lambda:actual!=expected,
                      "gt":lambda:actual>expected,"ge":lambda:actual>=expected,
                      "lt":lambda:actual<expected,"le":lambda:actual<=expected,
                      "eq":lambda:actual==expected}[op]())
    return (all(tests) if rule["match"]=="all" else any(tests))


def select_rule(track,settings):
    return next((r for r in settings.rules if r["enabled"] and matches(r,track)),None)


def effective_settings(track,settings):
    from dataclasses import replace
    rule=select_rule(track,settings)
    if not rule:return settings,""
    actions={k:v for k,v in rule["actions"].items() if v!="inherit"}
    target=actions.pop("format",None)
    if target:
        # A rule explicitly selecting a lossy encoder may also re-encode that format.
        actions["lossless_format"]=target
        actions["lossy_format"]=target
    result=replace(settings,**actions,rules=())
    return result,rule["name"]
