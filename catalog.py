"""Release-level metadata lookup with persistent caching and service rate limits."""
from i18n import tr
import hashlib
import json
import os
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import certifi

from media import embedded_cover, make_cover
from model import VERSION, Cancelled, IMAGE_EXTS, count_tag, match_name, normalize, number, reparse, year


USER_AGENT = f"MusicOrganizer/{VERSION} (Windows personal audio-library organizer; MusicBrainz + CoverArtArchive)"
SOURCES = {
    "musicbrainz": dict(name="MusicBrainz", description=tr('实体发行与数字发行资料，含厂牌、目录号和多碟信息。'), tags=True, covers=False, url="https://musicbrainz.org"),
    "coverartarchive": dict(name="Cover Art Archive", description=tr('与 MusicBrainz 发行版本对应的唱片封面。'), tags=False, covers=True, url="https://coverartarchive.org"),
    "itunes": dict(name="Apple iTunes", description=tr('按地区检索数字发行、曲目资料与高清封面。'), tags=True, covers=True, url="https://itunes.apple.com"),
}


def state_dir():
    path = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "MusicOrganizer"
    path.mkdir(parents=True, exist_ok=True)
    return path


class HTTP:
    _gate_lock = threading.Lock()
    _next = {}

    def __init__(self, folder=None):
        self.folder = folder or state_dir() / "Cache"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.folder / "network.sqlite", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (url TEXT PRIMARY KEY, stamp REAL, payload BLOB, status INTEGER)")
        self.db.commit()
        self.ssl = ssl.create_default_context(cafile=certifi.where())

    def close(self):
        with self.lock:
            self.db.close()

    def fetch(self, url, cancel, ttl=60*86400, limit=25*1024**2, timeout=12):
        cancel.check()
        with self.lock:
            row = self.db.execute("SELECT stamp, payload, status FROM cache WHERE url=?", (url,)).fetchone()
        if row and time.time() - row[0] < (ttl if row[2] == 200 else min(ttl, 86400)):
            return row[1] if row[2] == 200 else None
        host = urllib.parse.urlsplit(url).hostname or ""
        delay = 1.1 if host == "musicbrainz.org" else 3.1 if host == "itunes.apple.com" else 0.1
        with self._gate_lock:
            slot = max(time.monotonic(), self._next.get(host, 0))
            self._next[host] = slot + delay
        while time.monotonic() < slot:
            if cancel.event.wait(min(0.2, slot - time.monotonic())):
                cancel.check()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,image/*;q=0.9,*/*;q=0.5"})
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=self.ssl) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ValueError(tr('在线资源超过大小限制'))
                status = 200
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 410):
                raise
            raw, status = b"", exc.code
        cancel.check()
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?)", (url, time.time(), raw, status))
            self.db.commit()
        return raw if status == 200 else None

    def json(self, url, cancel, ttl=60*86400):
        data = self.fetch(url, cancel, ttl=ttl, limit=8*1024**2)
        return json.loads(data.decode("utf-8")) if data else None


def credit(credits):
    return "".join((row.get("name") or row.get("artist", {}).get("name", "")) + row.get("joinphrase", "")
                   for row in credits or [] if isinstance(row, dict))


def similarity(left, right):
    a, b = match_name(left), match_name(right)
    if not a or not b:
        return 0
    if a == b:
        return 1
    if min(len(a), len(b)) < 8:
        return 0
    return SequenceMatcher(None, a, b).ratio()


def representative(tracks, key):
    return Counter(t.tags.get(key, "") for t in tracks).most_common(1)[0][0] if tracks else ""


class Catalog:
    def __init__(self, http, settings, cancel, emit=lambda *a: None):
        self.http, self.settings, self.cancel, self.emit = http, settings, cancel, emit

    def local_cover(self, tracks, overrides=None):
        if overrides:
            for track in tracks:
                if path := overrides.get(track.edit_key):
                    return make_cover(Path(path).read_bytes(), tr('用户指定：{0}').format(Path(path).name))
        # A front cover inside the same release takes priority over directory illustrations.
        for track in sorted(tracks, key=lambda t: not t.has_cover):
            self.cancel.check()
            if track.has_cover and (cover := embedded_cover(track.path)):
                return cover
            if track.source.has_cover and track.source.path != track.path and (cover := embedded_cover(track.source.path)):
                return cover
        folders = list(dict.fromkeys([t.path.parent for t in tracks] + [t.source.path.parent for t in tracks]))
        for folder in list(folders):
            if folder.name.casefold().startswith(("cd", "disc", "disk")):
                folders.append(folder.parent)
        candidates = []
        for folder in dict.fromkeys(folders):
            try:
                for path in folder.iterdir():
                    if path.suffix.casefold() not in IMAGE_EXTS or not path.is_file() or reparse(path):
                        continue
                    stem = normalize(path.stem)
                    preferred = stem in {"cover", "folder", "front", "album", "albumart", tr('封面'), "albumartsmall"}
                    if not preferred and not ("front" in stem or tr('封面') in stem):
                        continue
                    candidates.append((not preferred, path))
            except OSError:
                continue
        for _, path in sorted(candidates, key=lambda row: (row[0], str(row[1]))):
            try:
                return make_cover(path.read_bytes(), tr('本地图片：{0}').format(path.name))
            except (OSError, ValueError):
                continue
        # A single image in a release directory is a reasonable local candidate.
        for folder in folders:
            try:
                pictures = [p for p in folder.iterdir() if p.is_file() and not reparse(p) and p.suffix.casefold() in IMAGE_EXTS]
                if len(pictures) == 1:
                    return make_cover(pictures[0].read_bytes(), tr('本地唯一图片：{0}').format(pictures[0].name))
            except (OSError, ValueError):
                pass
        return None

    def musicbrainz(self, artist, album, tracks, collect=False, loose=False, limit=4):
        def escape(value):
            return value.replace("\\", "\\\\").replace('"', '\\"')
        query = f'release:"{escape(album)}" AND artist:"{escape(artist)}"'
        catalog_number = representative(tracks, "catalognumber")
        basic_query = query
        vinyl = any(t.variant.startswith("Vinyl Rip") for t in tracks)
        if vinyl:
            query += " AND format:Vinyl"
            basic_query = query
        if catalog_number:
            query += f' AND catno:"{escape(catalog_number)}"'
        url = "https://musicbrainz.org/ws/2/release/?" + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 8})
        result = self.http.json(url, self.cancel, ttl=7*86400) or {}
        if catalog_number and not result.get("releases"):
            url = "https://musicbrainz.org/ws/2/release/?" + urllib.parse.urlencode({"query": basic_query, "fmt": "json", "limit": 8})
            result = self.http.json(url, self.cancel, ttl=7*86400) or {}
        releases = []
        for row in result.get("releases", []):
            if not loose and (similarity(row.get("title", ""), album) < .96 or similarity(credit(row.get("artist-credit")), artist) < .94):
                continue
            releases.append(row)
        requested_year = year(representative(tracks, "date"))
        releases.sort(key=lambda r: (bool(requested_year and year(r.get("date")) != requested_year),
                                      -(int(r.get("score", 0)))))
        results = []
        for row in releases[:limit if collect else 2]:
            detail = self.http.json(f"https://musicbrainz.org/ws/2/release/{row['id']}?inc=recordings+artist-credits+labels&fmt=json", self.cancel)
            if not detail:
                continue
            if vinyl and not any("vinyl" in normalize(media.get("format", "")) for media in detail.get("media", [])):
                continue
            songs = []
            for disc in detail.get("media", []):
                members = disc.get("tracks", [])
                for song in members:
                    rec = song.get("recording", {})
                    songs.append(dict(title=song.get("title") or rec.get("title", ""),
                                      artist=credit(song.get("artist-credit") or rec.get("artist-credit")) or artist,
                                      track=int(song.get("position", 0)), disc=int(disc.get("position", 1)),
                                      total=len(members), disctotal=len(detail.get("media", [])),
                                      seconds=float(song.get("length") or rec.get("length") or 0) / 1000))
            labels = detail.get("label-info") or []
            release = dict(album=detail.get("title", album), albumartist=credit(detail.get("artist-credit")) or artist,
                           date=detail.get("date") or "", label=(labels[0].get("label") or {}).get("name", "") if labels else "",
                           catalognumber=labels[0].get("catalog-number", "") if labels else "",
                           barcode=detail.get("barcode", ""), songs=songs,
                           source=f"MusicBrainz https://musicbrainz.org/release/{row['id']}",
                           cover=f"https://coverartarchive.org/release/{row['id']}/front-500" if detail.get("cover-art-archive", {}).get("front", True) else "",
                           provider="musicbrainz", id=row["id"], country=detail.get("country") or "",
                           format=" / ".join(dict.fromkeys(m.get("format", "") for m in detail.get("media", []) if m.get("format"))),
                           cover_provider="coverartarchive")
            aligned = self.align(tracks, release)
            if collect:
                results.append(release)
                continue
            if aligned:
                return release, aligned
        return results if collect else None

    def itunes(self, artist, album, tracks, collect=False, loose=False, limit=4):
        countries = [self.settings.country] if collect else list(dict.fromkeys([self.settings.country, "US", "JP"]))
        releases = []
        for country in countries:
            params = dict(term=f"{artist} {album}", entity="album", media="music", limit=25, country=country)
            result = self.http.json("https://itunes.apple.com/search?" + urllib.parse.urlencode(params), self.cancel, ttl=7*86400) or {}
            candidates = [r for r in result.get("results", []) if loose or (similarity(r.get("collectionName", ""), album) >= .96
                          and similarity(r.get("artistName", ""), artist) >= .94)]
            requested_year = year(representative(tracks, "date"))
            candidates.sort(key=lambda r: (similarity(r.get("collectionName", ""), album)+similarity(r.get("artistName", ""), artist), not bool(requested_year and year(r.get("releaseDate")) != requested_year)), reverse=True)
            for candidate in candidates[:limit if collect else 2]:
                lookup = self.http.json("https://itunes.apple.com/lookup?" + urllib.parse.urlencode({"id": candidate["collectionId"], "entity": "song", "limit": 200, "country": country}), self.cancel) or {}
                songs = []
                for row in lookup.get("results", []):
                    if row.get("wrapperType") != "track":
                        continue
                    songs.append(dict(title=row.get("trackName", ""), artist=row.get("artistName", artist),
                                      track=int(row.get("trackNumber") or 0), disc=int(row.get("discNumber") or 1),
                                      total=int(row.get("trackCount") or 0), disctotal=int(row.get("discCount") or 1),
                                      seconds=float(row.get("trackTimeMillis") or 0) / 1000,
                                      genre=row.get("primaryGenreName", "")))
                art = candidate.get("artworkUrl100", "")
                art = art.replace("100x100bb", "1200x1200bb")
                release = dict(album=candidate["collectionName"], albumartist=candidate["artistName"],
                               date=(candidate.get("releaseDate") or "")[:10], songs=songs, cover=art,
                               source=f"Apple iTunes {candidate.get('collectionViewUrl', '')}", provider="itunes", id=str(candidate["collectionId"]),
                               country=country, format="Digital", cover_provider="itunes")
                aligned = self.align(tracks, release)
                if collect:
                    releases.append(release)
                    continue
                if aligned:
                    return release, aligned
        return releases if collect else None

    def align(self, tracks, release):
        """Require release identity plus track position, title and length agreement."""
        aligned, strong = {}, 0
        for index, track in enumerate(tracks):
            n, _ = number(track.tags.get("tracknumber"))
            d, _ = number(track.tags.get("discnumber", "1"))
            viable = []
            for song in release["songs"]:
                title_score = similarity(song["title"], track.tags.get("title", ""))
                position_ok = n == song["track"] and (d or 1) == song["disc"]
                tolerance = 12 if track.variant.startswith("SACD") and position_ok and title_score >= .94 else max(5, song["seconds"]*.01) if track.variant.startswith("Vinyl Rip") and position_ok and title_score >= .94 else 3
                length_ok = song["seconds"] > 0 and abs(song["seconds"] - track.profile.seconds) <= tolerance
                if length_ok and (title_score >= .94 or position_ok):
                    viable.append((title_score, position_ok, song))
            viable.sort(key=lambda row: (row[0], row[1]), reverse=True)
            if not viable or len(viable) > 1 and viable[0][:2] == viable[1][:2]:
                return None
            score, position, song = viable[0]
            if score >= .94:
                strong += 1
            elif not position:
                return None
            aligned[index] = song
        # A single track needs its own title match; larger albums may repair damaged titles.
        if strong < max(1, (len(tracks) + 1) // 2):
            return None
        identities = [(s["disc"], s["track"]) for s in aligned.values()]
        if len(set(identities)) != len(identities):
            return None
        return aligned

    def enrich(self, tracks, overrides=None, selections=None):
        from sources import enrich
        return enrich(self, tracks, overrides, selections)

    def search_candidates(self, artist, album, tracks=(), providers=None):
        from sources import search_candidates
        return search_candidates(self, artist, album, tracks, providers)
