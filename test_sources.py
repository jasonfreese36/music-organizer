import io
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from PIL import Image

from catalog import Catalog
from model import Cancel, Item, Profile, Settings, Track
from sources import TEST_MBID, enrich, test_source


def run():
    with tempfile.TemporaryDirectory(prefix="music-sources-test-") as folder:
        root = Path(folder)
        dummy = root/"track.flac"
        dummy.write_bytes(b"fixture")
        item = Item(dummy, Path(dummy.name), 7, dummy.stat().st_mtime_ns, "audio")
        original = dict(title="Song", artist="Artist", albumartist="Artist", album="Album", tracknumber="1", date="2020")
        def track():
            return Track(item, dummy, Profile("flac", 44100, 2, 16, 120), dict(original))
        def release(provider, identity="1"):
            return dict(id=identity, provider=provider, source=provider+" https://example.org/"+identity,
                        cover_provider="coverartarchive" if provider=="musicbrainz" else "itunes",
                        album="Album", albumartist="Artist", date="2020-01-02", country="US", format="CD" if provider=="musicbrainz" else "Digital",
                        cover="https://example.org/"+provider+".jpg", label=provider+" Label",
                        songs=[dict(title="Song", artist="Artist", track=1, disc=1, total=1, disctotal=1, seconds=120)])
        picture=io.BytesIO();Image.new("RGB",(64,64),(60,90,120)).save(picture,"PNG");data=picture.getvalue()
        class FakeHTTP:
            def __init__(self):self.calls=[]
            def fetch(self,url,cancel,**kwargs):self.calls.append((url,kwargs));return data
        class Client(Catalog):
            def __init__(self,settings):super().__init__(FakeHTTP(),settings,Cancel());self.calls=[]
            def local_cover(self,*a):return None
            def lookup(self,provider,artist,album,tracks,collect=False,**kwargs):
                self.calls.append(provider)
                r=release(provider)
                return [r,release(provider,"2")] if collect else (r,self.align(tracks,r))
            def musicbrainz(self,*a,**k):return self.lookup("musicbrainz",*a,**k)
            def itunes(self,*a,**k):return self.lookup("itunes",*a,**k)
        a=track();client=Client(Settings(tag_sources=("itunes",),cover_sources=("coverartarchive",)))
        cover=client.enrich([a]);assert client.calls==["itunes","musicbrainz"],client.calls
        assert a.tags["label"]=="itunes Label" and "Cover Art Archive" in cover.source
        client=Client(Settings(tag_sources=("itunes",),cover_sources=("itunes",)))
        client.enrich([track()]);assert client.calls==["itunes"],client.calls
        client=Client(Settings(tag_sources=(),cover_sources=()))
        client.enrich([track()]);assert not client.calls and not client.http.calls
        client=Client(Settings())
        candidates=client.search_candidates("Artist","Album",[track()])
        assert len(candidates["candidates"])==4 and len({r['key'] for r in candidates['candidates']})==4
        chosen_image=root/'chosen.png';chosen_image.write_bytes(data)
        a=track();client=Client(Settings(online=False,tag_sources=(),cover_sources=()))
        chosen=dict(metadata=release("itunes"),cover=dict(path=str(chosen_image),source="Cover Art Archive https://example.org/art",provider="coverartarchive"))
        cover=client.enrich([a],selections={a.edit_key:chosen})
        assert not client.calls and not client.http.calls
        assert a.tags['label']=='itunes Label' and 'Cover Art Archive' in cover.source and a.metadata_source.startswith('用户选择')
        class Probe:
            def __init__(self,broken=False):self.calls=[];self.broken=broken
            def fetch(self,url,cancel,**kwargs):
                self.calls.append((url,kwargs));assert kwargs.get('ttl')==0,'Connectivity test used cache'
                if 'itunes.apple.com' in url:return json.dumps(dict(results=[dict(artworkUrl100='https://example.org/art.png')])).encode()
                if 'musicbrainz.org' in url:return json.dumps(dict(id=TEST_MBID)).encode()
                if 'coverartarchive.org' in url:return json.dumps(dict(images=[dict(front=True,image='https://example.org/art.png')])).encode()
                if self.broken:raise TimeoutError('image CDN timed out')
                return data
        for name in ('musicbrainz','coverartarchive','itunes'):
            p=Probe();r=test_source(p,name,Settings(),Cancel());assert r['state']=='ok',(name,r)
        r=test_source(Probe(True),'itunes',Settings(),Cancel());assert r['state']=='partial' and r['tags'] and not r['covers'],r
        r=test_source(Probe(True),'coverartarchive',Settings(),Cancel());assert r['state']!='ok' and not r['covers'],r
        result=dict(independent_tag_cover_sources=True,disabled_sources_not_called=True,multiple_candidates=True,
                    mixed_provider_selection_works_offline=True,connectivity_bypasses_cache=True,broken_images_not_reported_healthy=True)
        print(json.dumps(result,indent=2))
        return result


if __name__=='__main__':run()
