"""Source selection, release comparison and live (uncached) connectivity checks."""
from i18n import tr
import json
import time
from datetime import datetime
from pathlib import Path

from catalog import HTTP, SOURCES, representative, similarity
from media import make_cover
from model import Cancelled, count_tag, match_name, number, year


TEST_MBID = "88f2ae2e-0a47-45db-bdf3-c15a54a5454a"
TEST_APPLE_ID = "1474815798"


def artwork_source(release):
    source=release.get('source','')
    provider=release.get('cover_provider',release.get('provider'))
    name=SOURCES.get(provider,{}).get('name',tr('封面来源'))
    return source if source.startswith(name) else name+' · '+source


def manual_alignment(tracks, release):
    aligned = {}
    used = set()
    for index, track in enumerate(tracks):
        n = number(track.tags.get("tracknumber"))[0]
        d = number(track.tags.get("discnumber", "1"))[0] or 1
        options = []
        for song in release.get("songs", []):
            key = (song["disc"], song["track"])
            if key in used:
                continue
            title = similarity(track.tags.get("title", ""), song["title"])
            position = bool(n and n == song["track"] and d == song["disc"])
            delta = abs(track.profile.seconds - song.get("seconds", 0))
            tolerance = 12 if track.variant.startswith("SACD") else max(5, track.profile.seconds*.01) if track.variant.startswith("Vinyl Rip") else 5
            if song.get("seconds", 0) > 0 and delta <= tolerance and (title >= .94 or position):
                options.append((title >= .94, position, -delta, song))
        options.sort(key=lambda row: row[:3], reverse=True)
        if options and (len(options) == 1 or options[0][:3] != options[1][:3]):
            song = options[0][3]
            aligned[index] = song
            used.add((song["disc"], song["track"]))
    return aligned


def compatible_edition(tracks, release):
    local_year = year(representative(tracks, "date"))
    remote_year = year(release.get("date", ""))
    if local_year and remote_year and local_year != remote_year:
        return False
    local_catalog = representative(tracks, "catalognumber")
    remote_catalog = release.get("catalognumber", "")
    return not (local_catalog and remote_catalog and match_name(local_catalog) != match_name(remote_catalog))


def apply_release(tracks, release, aligned, manual=False):
    same_edition = manual or compatible_edition(tracks, release)
    for index, track in enumerate(tracks):
        for key in ("album", "albumartist"):
            if release.get(key):
                track.tags[key] = release[key]
        song = aligned.get(index)
        if song:
            for key in ("title", "artist"):
                if song.get(key):
                    track.tags[key] = song[key]
            track.tags["tracknumber"] = count_tag(song["track"], song.get("total", 0))
            track.tags["discnumber"] = count_tag(song["disc"], song.get("disctotal", 0))
            if song.get("genre"):
                if manual:
                    track.tags["genre"] = song["genre"]
                else:
                    track.tags.setdefault("genre", song["genre"])
        elif manual:
            track.issues.append(tr('手选发行的部分曲目未对应：保留此音轨的曲名与轨序'))
        for key in ("date", "label", "catalognumber", "barcode"):
            value = release.get(key)
            if same_edition and value and (manual or not track.tags.get(key) or key == "date" and len(track.tags[key]) < len(value)):
                track.tags[key] = value
        if not same_edition:
            track.issues.append(tr('在线版本的年份或目录号不同，保留本地发行字段'))
        track.metadata_source = (tr('用户选择 · ') if manual else "") + release.get("source", "")


def candidate(release, artist, album, tracks, catalog):
    matched = manual_alignment(tracks, release)
    strict = catalog.align(tracks, release) if tracks else None
    identity = (similarity(artist, release.get("albumartist", "")) + similarity(album, release.get("album", ""))) / 2
    score = round(100 * (identity*.7 + (len(matched)/len(tracks) if tracks else identity)*.3))
    return dict(key=f"{release['provider']}:{release['id']}:{release.get('country', '')}",
                provider=release["provider"], release=release, score=score, matched=len(matched), local_tracks=len(tracks),
                exact=bool(strict) and identity >= .95, cover_provider=release.get("cover_provider", ""))


def search_candidates(catalog, artist, album, tracks=(), providers=None):
    if not artist.strip() or not album.strip():
        raise ValueError(tr('请填写艺术家和专辑名称'))
    allowed = set(catalog.settings.tag_sources)
    if "coverartarchive" in catalog.settings.cover_sources:
        allowed.add("musicbrainz")
    if "itunes" in catalog.settings.cover_sources:
        allowed.add("itunes")
    if providers is not None:
        allowed.intersection_update(providers)
    if not allowed:
        raise ValueError(tr('请先在“数据源”中启用至少一个在线来源'))
    results, errors = [], []
    for provider in ("musicbrainz", "itunes"):
        if provider not in allowed:
            continue
        catalog.cancel.check()
        catalog.emit("lookup_progress", tr('正在检索 {0}…').format(SOURCES[provider]['name']))
        try:
            releases = getattr(catalog, provider)(artist, album, tracks, collect=True, loose=True, limit=4)
            for release in releases:
                row = candidate(release, artist, album, tracks, catalog)
                results.append(row)
                catalog.emit("candidate", row)
        except Cancelled:
            raise
        except Exception as exc:
            message = f"{SOURCES[provider]['name']}：{exc}"
            errors.append(message)
            catalog.emit("lookup_progress", message)
    results.sort(key=lambda row: (row["exact"], row["score"]), reverse=True)
    return dict(candidates=results, errors=errors)


def enrich(catalog, tracks, overrides=None, selections=None):
    selections = selections or {}
    selected = next((selections[t.edit_key] for t in tracks if t.edit_key in selections), {})
    selected_release = selected.get("metadata")
    selected_cover = selected.get("cover")
    cover, errors, found = None, [], {}
    if selected_cover:
        try:
            path = Path(selected_cover["path"])
            cover = make_cover(path.read_bytes(), tr('用户选择 · ')+selected_cover.get("source", str(path)))
        except (OSError, ValueError, KeyError) as exc:
            errors.append(tr('选定封面缓存无法读取：{0}').format(exc))
            for track in tracks:
                track.issues.append(tr('选定封面缓存不存在，请重新选择该封面'))
    if not cover:
        cover = catalog.local_cover(tracks, overrides)
    artist = representative(tracks, "albumartist")
    album = representative(tracks, "album")
    vinyl = any(t.variant.startswith("Vinyl Rip") for t in tracks)

    def fetch(provider):
        if provider in found:
            return found[provider]
        found[provider] = None
        if vinyl and provider == "itunes":
            return None
        try:
            found[provider] = getattr(catalog, provider)(artist, album, tracks)
        except Cancelled:
            raise
        except Exception as exc:
            errors.append(f"{SOURCES[provider]['name']}：{str(exc)[:180]}")
        return found[provider]

    release, aligned = None, None
    if selected_release:
        release = selected_release
        aligned = manual_alignment(tracks, release)
        apply_release(tracks, release, aligned, manual=True)
    elif catalog.settings.online and artist != "Unknown Artist":
        for provider in catalog.settings.tag_sources:
            if match := fetch(provider):
                release, aligned = match
                break
        if release:
            apply_release(tracks, release, aligned)

    if not cover and catalog.settings.online and artist != "Unknown Artist":
        for provider in catalog.settings.cover_sources:
            parent = "musicbrainz" if provider == "coverartarchive" else "itunes"
            cover_release = release if release and release.get("provider") == parent else None
            if not cover_release:
                match = fetch(parent)
                cover_release = match[0] if match else None
            if not cover_release or not cover_release.get("cover") or not compatible_edition(tracks, cover_release):
                continue
            try:
                data = catalog.http.fetch(cover_release["cover"], catalog.cancel)
                if data:
                    cover = make_cover(data, artwork_source(cover_release))
                    break
            except Cancelled:
                raise
            except Exception as exc:
                errors.append(tr('{0} 封面：{1}').format(SOURCES[provider]['name'], str(exc)[:180]))
    if errors:
        catalog.emit("log", tr('在线资料 {0}：{1}').format(album, '；'.join(errors)))
    for track in tracks:
        if not cover:
            track.issues.append(tr('缺少封面：可在“在线资料”中选择其他发行或手动指定图片'))
        if not release and catalog.settings.online and catalog.settings.tag_sources:
            track.issues.append(tr('启用的标签来源中没有足够吻合的发行，保留原标签'))
    return cover


def test_source(http, source_id, settings, cancel):
    if source_id not in SOURCES:
        raise ValueError(tr('未知数据源'))
    start = time.perf_counter()
    result = dict(source=source_id, name=SOURCES[source_id]["name"], state="error", tags=False, covers=False,
                  checked_at=datetime.now().astimezone().isoformat(timespec="seconds"), detail="", endpoints=[])

    def fresh_json(url):
        result["endpoints"].append(url)
        raw = http.fetch(url, cancel, ttl=0, limit=8*1024**2, timeout=10)
        if not raw:
            raise ValueError(tr('测试接口未返回内容'))
        return json.loads(raw.decode("utf-8"))

    try:
        if source_id == "musicbrainz":
            doc = fresh_json(f"https://musicbrainz.org/ws/2/release/{TEST_MBID}?fmt=json")
            if doc.get("id") != TEST_MBID:
                raise ValueError(tr('返回内容不是发行资料 API 的有效响应'))
            result.update(state="ok", tags=True, detail=tr('发行 API 返回有效资料；未使用缓存'))
        elif source_id == "coverartarchive":
            doc = fresh_json(f"https://coverartarchive.org/release/{TEST_MBID}")
            image = next((i for i in doc.get("images", []) if i.get("front")), None)
            if not image:
                result.update(state="partial", detail=tr('封面 API 已连接，测试发行当前没有正面封面'))
            else:
                url = image.get("thumbnails", {}).get("small") or image["image"]
                result["endpoints"].append(url)
                data = http.fetch(url, cancel, ttl=0, timeout=10)
                if not data:
                    raise ValueError(tr('图片服务未返回封面'))
                picture = make_cover(data, url)
                result.update(state="ok", covers=True, detail=tr('封面 API 与图片下载可用 · {0}×{1}；未使用缓存').format(picture.width, picture.height))
        else:
            doc = fresh_json(f"https://itunes.apple.com/lookup?id={TEST_APPLE_ID}&country={settings.country}")
            if not isinstance(doc.get("results"), list):
                raise ValueError(tr('返回内容不是 iTunes API 的有效响应'))
            result.update(state="partial", tags=True, detail=tr('资料 API 已连接；此地区未返回测试专辑'))
            if doc["results"]:
                result["detail"] = tr('资料 API 可用；测试封面下载…')
                url = next((r.get("artworkUrl100") for r in doc["results"] if r.get("artworkUrl100")), None)
                if url:
                    result["endpoints"].append(url)
                    data = http.fetch(url, cancel, ttl=0, timeout=10)
                    if not data:
                        raise ValueError(tr('封面图片服务未返回内容'))
                    make_cover(data, url)
                    result.update(state="ok", covers=True, detail=tr('发行 API 与封面图片下载均可用；未使用缓存'))
        cancel.check()
    except Cancelled:
        raise
    except Exception as exc:
        cancel.check()
        result["state"] = "partial" if result["tags"] else "error"
        result["detail"] = str(exc)[:500]
    result["milliseconds"] = round((time.perf_counter()-start)*1000)
    return result


def test_sources(http, settings, cancel, emit=lambda *a: None, providers=None):
    results = []
    for source in (tuple(providers) if providers is not None else tuple(SOURCES)):
        cancel.check()
        emit("source_testing",source)
        emit("log", tr('实时测试 {0}（绕过缓存）').format(SOURCES[source]['name']))
        row = test_source(http, source, settings, cancel)
        results.append(row)
        emit("source_test", row)
    return results
