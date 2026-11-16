"""Live service smoke test: metadata, real cover retrieval and cache-only repeat."""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from catalog import Catalog, HTTP
from model import Cancel, Item, Profile, Settings, Track


def test(root):
    root.mkdir(parents=True, exist_ok=True)
    http, cancel = HTTP(root / "Cache"), Cancel()
    try:
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(dict(term="The Beatles Abbey Road", entity="album", country="US", limit=10))
        response = http.json(url, cancel)
        release = next(r for r in response["results"] if r.get("artistName") == "The Beatles" and r.get("collectionType") == "Album")
        lookup_url = "https://itunes.apple.com/lookup?" + urllib.parse.urlencode(dict(id=release["collectionId"], entity="song", limit=200, country="US"))
        doc = http.json(lookup_url, cancel)
        song = next(r for r in doc["results"] if r.get("wrapperType") == "track")
        dummy = root / "source.flac"
        dummy.write_bytes(b"Fixture, no real audio is sent")
        st = dummy.stat()
        tags = dict(title=song["trackName"], artist=song["artistName"], album=song["collectionName"],
                    albumartist=song["artistName"], tracknumber=str(song["trackNumber"]), discnumber=str(song["discNumber"]))
        item = Item(dummy, Path(dummy.name), st.st_size, st.st_mtime_ns, "audio", tags=tags)
        track = Track(item, dummy, Profile("flac", 44100, 2, 16, song["trackTimeMillis"]/1000), dict(tags))
        catalog = Catalog(http, Settings(country="US"), cancel)
        found = catalog.itunes(tags["albumartist"], tags["album"], [track])
        assert found, "Exact iTunes release and duration did not match"
        cover = catalog.enrich([track])
        assert cover and min(cover.width, cover.height) >= 300, track.issues
        # Repeat using only persisted responses: any unexpected network request fails this check.
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("Cache miss on identical repeat")):
            second = catalog.enrich([track])
            assert second and second.data == cover.data
        result = dict(artist=tags["albumartist"], album=tags["album"], title=tags["title"],
                      metadata_source=track.metadata_source, cover_source=cover.source,
                      cover_size=[cover.width, cover.height], cache_repeat=True)
        (root/"test-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        http.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(test(args.root.resolve()), ensure_ascii=False, indent=2))
