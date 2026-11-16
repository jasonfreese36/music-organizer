import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Music Organizer: portable GUI and diagnostic CLI")
    parser.add_argument("--check-tools", action="store_true")
    parser.add_argument("--organize", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--settings",type=Path)
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--test-sources", action="store_true")
    parser.add_argument("--search-releases", action="store_true")
    parser.add_argument("--artist", default="")
    parser.add_argument("--album", default="")
    parser.add_argument("--country")
    parser.add_argument("--tag-sources")
    parser.add_argument("--cover-sources")
    args = parser.parse_args()
    if args.check_tools or args.scan or args.organize or args.test_sources or args.search_releases or args.preview:
        from media import Tools
        from model import Cancel, Settings, validated_roots, write_atomic
        tools, cancel = Tools(), Cancel()
        result = {}
        try:
            values={}
            if args.settings:
                if args.settings.stat().st_size>2*1024**2:raise ValueError("配置超过 2 MB")
                document=json.loads(args.settings.read_text(encoding="utf-8-sig"))
                values=document.get("settings",document)
                if not isinstance(values,dict):raise ValueError("配置格式无效")
                values=dict(values)
            if args.offline:values["online"]=False
            if args.workers is not None:values["workers"]=args.workers
            if args.country:values["country"]=args.country
            for key in ("tag_sources","cover_sources"):
                raw=getattr(args,key)
                if raw is not None:values[key]=tuple(s.strip() for s in raw.split(",") if s.strip())
            settings=Settings(**values)
            if args.check_tools or args.scan or args.organize or args.preview:
                result["tools"] = tools.verify(cancel)
            if args.test_sources or args.search_releases:
                from catalog import HTTP, Catalog
                from sources import test_sources
                http = HTTP()
                try:
                    if args.test_sources:
                        result["sources"] = test_sources(http, settings, cancel)
                    if args.search_releases:
                        result["search"] = Catalog(http, settings, cancel).search_candidates(args.artist, args.album)
                finally:
                    http.close()
            if args.scan or args.organize or args.preview:
                from inventory import scan
                if not args.source or not args.dest:
                    raise ValueError("--source and --dest are required")
                source, dest = validated_roots(args.source, args.dest)
                items, skipped = scan(source, tools, cancel, settings.workers,settings=settings)
                result["scan"] = dict(files=len(items), skipped=skipped, audio=sum(i.kind == "audio" for i in items),
                                      errors=[dict(path=str(i.rel), error=i.error) for i in items if i.error],encrypted=[dict(source=str(i.rel),**i.crypto) for i in items if i.crypto])
                if args.organize:
                    from engine import Organizer
                    result["organize"] = Organizer(source, dest, items, settings, tools, cancel).run()
                if args.preview:
                    from preview import preview_rows
                    result["preview"]=preview_rows(items,settings)
        except Exception as exc:
            result["error"] = str(exc)
            result["traceback"] = traceback.format_exc()
        raw = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
        if args.report:
            write_atomic(args.report.resolve(), raw)
        elif sys.stdout:
            print(raw.decode("utf-8"))
        return 1 if "error" in result or result.get("organize", {}).get("errors", 0) else 0
    from gui import launch
    launch()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        from tkinter import messagebox
        messagebox.showerror("Music Organizer 启动失败", traceback.format_exc()[-3000:])
        raise
