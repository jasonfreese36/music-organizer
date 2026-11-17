"""Measure real DSP output and resume behavior on synthesized audio only."""
import argparse
import array
import hashlib
import json
import math
import shutil
import struct
import subprocess
from dataclasses import replace
from pathlib import Path

from apple import compatibility_issue
from conversion import plan_audio
from engine import Organizer
from inventory import infer_track,scan
from media import Tools,payload_hash,read_audio,render
from model import Cancel,Item,Settings


def make_dsf(path,seconds=.5):
    rate=2822400;samples=int(rate*seconds);packed=bytearray((samples+7)//8);error=0.0
    for n in range(samples):
        value=.05+.2*math.sin(2*math.pi*1000*n/rate)+.15*math.sin(2*math.pi*60000*n/rate)
        error+=value
        bit=error>=0
        error-=1 if bit else -1
        if bit:packed[n//8]|=1<<(n%8)
    packed.extend(bytes((-len(packed))%4096))
    data=b"".join(bytes(packed[i:i+4096])*2 for i in range(0,len(packed),4096))
    fmt=b"fmt "+struct.pack("<QIIIIIIQII",52,1,0,2,2,rate,1,samples,4096,0)
    body=fmt+b"data"+struct.pack("<Q",12+len(data))+data
    path.write_bytes(b"DSD "+struct.pack("<QQQ",28,28+len(body),0)+body)


def pcm(path,tools):
    result=subprocess.run([str(tools.ffmpeg),"-v","error","-i",str(path),"-map","0:a:0","-ac","1","-f","f64le","-"],
                          capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    data=array.array("d");data.frombytes(result.stdout)
    return data


def amplitude(data,rate,freq):
    values=data[int(rate*.25):int(rate*.45)]
    real=sum(v*math.cos(2*math.pi*freq*n/rate) for n,v in enumerate(values))
    imag=sum(v*math.sin(2*math.pi*freq*n/rate) for n,v in enumerate(values))
    return 2*math.hypot(real,imag)/len(values)


def run(root):
    root.mkdir(parents=True,exist_ok=True);source=root/"Source";source.mkdir()
    tools=Tools();cancel=Cancel()
    wav=source/"Wideband.wav"
    tools.ff(["-y","-f","lavfi","-i","aevalsrc=0.2*sin(2*PI*1000*t)+0.2*sin(2*PI*23000*t):s=192000:d=0.5",
              "-ac","2","-c:a","pcm_s24le",wav],cancel)
    make_dsf(source/"DSD.dsf")
    items,skips=scan(source,tools,cancel);assert not skips
    before={i.path:hashlib.sha256(i.path.read_bytes()).hexdigest() for i in items}
    track=infer_track(next(i for i in items if i.path==wav))
    base=Settings(online=False,resample_mode="fixed",sample_rate=48000,pcm_bits=24,resample_cutoff_enabled=True)
    hashes=[]
    for index,options in enumerate((
        dict(resampler="swr",swr_filter_type="kaiser",swr_filter_size=64,swr_kaiser_beta=12),
        dict(resampler="swr",swr_filter_type="blackman_nuttall"),
        dict(resampler="swr",swr_filter_type="cubic"),
        dict(resampler="soxr",soxr_precision=20),
        dict(resampler="soxr",soxr_precision=28),
        dict(resampler="soxr",soxr_precision=33,soxr_cheby=True),
    )):
        settings=replace(base,**options);dest=root/f"Algorithm {index}.flac"
        render(track,dest,None,tools,settings,cancel)
        profile=read_audio(dest,tools,cancel)[0]
        assert profile.rate==48000 and profile.bits==24 and abs(profile.seconds-.5)<.001,profile
        hashes.append(payload_hash(dest,cancel))
    assert len(set(hashes))>=4,hashes
    wide=root/"Cutoff 98.flac";narrow=root/"Cutoff 80.flac"
    hq=replace(base,resampler="soxr",soxr_precision=28)
    render(track,wide,None,tools,hq,cancel)
    render(track,narrow,None,tools,replace(hq,resample_cutoff=80),cancel)
    wide_pcm,narrow_pcm=pcm(wide,tools),pcm(narrow,tools)
    assert amplitude(wide_pcm,48000,1000)>.19
    assert amplitude(wide_pcm,48000,23000)>amplitude(narrow_pcm,48000,23000)*10
    cutoff_difference_db=20*math.log10(amplitude(wide_pcm,48000,23000)/amplitude(narrow_pcm,48000,23000))
    dsd=infer_track(next(i for i in items if i.path.suffix==".dsf"))
    raw=root/"DSD Raw.flac";filtered=root/"DSD Filtered.flac"
    plain=Settings(online=False,sacd_rate=176400,resampler="soxr")
    advanced=replace(plain,dsd_advanced=True,dsd_lowpass_hz=30000,dsd_lowpass_order=4,dsd_remove_dc=True,dsd_gain_db=-3)
    render(dsd,raw,None,tools,plain,cancel);render(dsd,filtered,None,tools,advanced,cancel)
    raw_pcm,filtered_pcm=pcm(raw,tools),pcm(filtered,tools)
    low_ratio=amplitude(filtered_pcm,176400,1000)/amplitude(raw_pcm,176400,1000)
    assert abs(20*math.log10(low_ratio)+3)<.08,low_ratio
    high_ratio=amplitude(filtered_pcm,176400,60000)/amplitude(raw_pcm,176400,60000)
    assert 20*math.log10(high_ratio)<-25,high_ratio
    segment=slice(int(176400*.3),int(176400*.45))
    assert abs(sum(filtered_pcm[segment])/len(filtered_pcm[segment]))<abs(sum(raw_pcm[segment])/len(raw_pcm[segment]))/10
    for rate in (44100,48000,88200,96000,192000,352800,384000):
        dest=root/f"DSD {rate}.flac"
        render(dsd,dest,None,tools,replace(advanced,sacd_rate=rate),cancel)
        assert read_audio(dest,tools,cancel)[0].rate==rate
    # Check the ISO extraction boundary with generated audio/XML, then encode
    # the extracted DSD through the real chain. No real-disc validation is implied.
    from formats import extract_sacd
    iso=root/"Generated Contract.iso";iso.write_bytes(b"Extractor contract fixture")
    st=iso.stat();iso_item=Item(iso,Path(iso.name),st.st_size,st.st_mtime_ns,"iso",root=root)
    calls=[]
    class ExtractorFixture:
        sacd=tools.sacd
        def __getattr__(self,name):return getattr(tools,name)
        def run(self,args,cancel,cwd=None):
            calls.append([str(v) for v in args]);folder=Path(cwd)
            if "-s" in args:
                assert "-c" in args and "--flac-rate" not in args
                shutil.copyfile(source/"DSD.dsf",folder/"01 - ISO Tone.dsf")
            else:
                assert "-f" in args and "--flac-rate" in args
                shutil.copyfile(raw,folder/"01 - ISO Tone.flac")
            (folder/"Metadata.xml").write_text('<Root><Album sequence_number="1" set_size="1"/><Disc creation_date="2026" catalog_number="TEST"/><Area speaker_configuration="2 Channel" totaltracks="1"><track id="1"><meta name="TITLE" value="ISO Tone"/><meta name="PERFORMER" value="DSD Artist"/><meta name="ALBUM" value="ISO Album"/></track></Area></Root>',encoding="utf-8")
            return ""
    for enabled in (False,True):
        scratch=root/("ISO Advanced" if enabled else "ISO Legacy");scratch.mkdir()
        selected=advanced if enabled else plain
        members=extract_sacd(iso_item,scratch,ExtractorFixture(),selected,cancel,lambda *a:None)
        assert len(members)==1 and members[0].tags["title"]=="ISO Tone"
        assert members[0].profile.codec.startswith("dsd") if enabled else members[0].profile.codec=="flac"
        if enabled:
            dest=root/"ISO Advanced Result.flac"
            render(members[0],dest,None,tools,selected,cancel)
            assert payload_hash(dest,cancel)==payload_hash(filtered,cancel)
    assert len(calls)==2 and "--max-read-errors" in calls[0]
    # DSD settings honor device ceilings, despite a requested 32-bit / 384 kHz output.
    device=replace(advanced,output_profile="ios",apple_quality="lossless",dsd_pcm_bits=32,sacd_rate=384000)
    dest=root/"Device.m4a";render(dsd,dest,None,tools,device,cancel)
    assert not compatibility_issue(read_audio(dest,tools,cancel)[0],device,dest.suffix)
    # Noise shaping is applied at a supported rate, and rejected without a silent fallback elsewhere.
    shaped=replace(base,sample_rate=44100,pcm_bits=16,dither="shibata")
    render(track,root/"Shaped.flac",None,tools,shaped,cancel)
    try:plan_audio(track,replace(shaped,sample_rate=96000))
    except ValueError:pass
    else:raise AssertionError("Unsupported shaping rate was accepted")
    assert plan_audio(track,replace(base,resample_mode="family",sample_rate=96000)).rate==96000
    assert plan_audio(dsd,replace(plain,resample_mode="family",sample_rate=96000,sacd_rate=176400)).rate==88200
    # Gain, changing cutoff and restoring original PCM update one output in place.
    only=[next(i for i in items if i.path==wav)];target=root/"Library"
    def organize(settings):
        result=Organizer(source,target,only,settings,tools,cancel,cache_folder=root/"Cache").run()
        assert not result["errors"],result
        return result
    organize(hq)
    same=organize(hq);assert same["converted"]==0 and same["written"]==0,same
    changed=organize(replace(hq,resample_cutoff=80));assert changed["converted"]==1,changed
    gained=organize(Settings(online=False,gain_db=-6));assert gained["converted"]==1,gained
    output=next((target/"Albums").rglob("*.flac"))
    original_pcm=pcm(wav,tools);gain_pcm=pcm(output,tools)
    assert abs(20*math.log10(amplitude(gain_pcm,192000,1000)/amplitude(original_pcm,192000,1000))+6)<.01
    restored=organize(Settings(online=False));assert restored["converted"]==1,restored
    assert tools.decoded_hash(output,cancel)==tools.decoded_hash(wav,cancel)
    for field,value in (("resample_cutoff",float("nan")),("gain_db",float("inf")),("soxr_precision",34),
                        ("swr_filter_size",257),("swr_phase_shift",24),("dsd_lowpass_hz",1),("dsd_lowpass_order",3)):
        try:replace(base,**{field:value})
        except ValueError:pass
        else:raise AssertionError((field,value))
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in before.items())
    result=dict(passed=True,encoder_variants=6,cutoff_difference_db=round(cutoff_difference_db,2),
                dsd_gain_db=round(20*math.log10(low_ratio),3),dsd_ultrasonic_change_db=round(20*math.log10(high_ratio),2),
                dsd_dc_removed=True,dsd_rates_tested=8,iso_extractor_contract=True,iso_dsd_chain=True,apple_limits=True,noise_shaping_checked=True,
                parameter_change_updates=True,repeat_skips_encoding=True,original_pcm_restored=True,source_unchanged=True)
    (root/"Test Result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True)
    run(parser.parse_args().root.resolve())
