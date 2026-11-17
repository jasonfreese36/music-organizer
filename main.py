from i18n import tr
import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Music Organizer: portable GUI and diagnostic CLI")
    parser.add_argument("--check-tools", action="store_true")
    parser.add_argument("--check-gui",action="store_true",help="Check GUI controls in temporary preferences and exit")
    parser.add_argument("--language",choices=("zh_CN","en"))
    parser.add_argument("--organize", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--source", type=Path,action="append",help="Source directory; repeat for multiple roots")
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
    if args.language:
        from i18n import select_language
        select_language(args.language)
    if args.check_gui:
        try:
            from gui_check import check_gui
            result={"gui":check_gui()}
        except Exception as exc:result=dict(error=str(exc),traceback=traceback.format_exc())
        raw=json.dumps(result,ensure_ascii=False,indent=2)
        if args.report:
            from model import write_atomic
            write_atomic(args.report.resolve(),raw.encode("utf-8"))
        elif sys.stdout:print(raw)
        return 1 if "error" in result else 0
    if args.check_tools or args.scan or args.organize or args.test_sources or args.search_releases or args.preview:
        from media import Tools
        from model import Cancel, Settings, validated_sources, write_atomic
        tools, cancel = Tools(), Cancel()
        result = {}
        report_allowed=True
        try:
            values={}
            if args.settings:
                if args.settings.stat().st_size>2*1024**2:raise ValueError(tr('配置超过 2 MB'))
                document=json.loads(args.settings.read_text(encoding="utf-8-sig"))
                values=document.get("settings",document)
                if not isinstance(values,dict):raise ValueError(tr('配置格式无效'))
                values=dict(values)
            if args.offline:values["online"]=False
            if args.workers is not None:values["workers"]=args.workers
            if args.country:values["country"]=args.country
            for key in ("tag_sources","cover_sources"):
                raw=getattr(args,key)
                if raw is not None:values[key]=tuple(s.strip() for s in raw.split(",") if s.strip())
            settings=Settings(**values)
            if settings.output_profile!="library" and args.report and args.dest and args.report.resolve().is_relative_to(args.dest.resolve()):
                report_allowed=False
                raise ValueError(tr('设备预设的诊断报告必须保存在设备导入目录之外'))
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
                source, dest = validated_sources(args.source, args.dest)
                if args.report and any(args.report.resolve().is_relative_to(root) for root in source):
                    report_allowed=False
                    raise ValueError(tr('诊断报告不能写入源文件夹'))
                items, skipped = scan(source, tools, cancel, settings.workers,settings=settings)
                result["scan"] = dict(files=len(items), skipped=skipped, audio=sum(i.kind == "audio" for i in items),
                                      sources=[str(p) for p in source],
                                      errors=[dict(path=str(i.library_rel), error=i.error) for i in items if i.error],encrypted=[dict(source=str(i.library_rel),**i.crypto) for i in items if i.crypto])
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
        if args.report and report_allowed:
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
        messagebox.showerror(tr('Music Organizer 启动失败'), traceback.format_exc()[-3000:])
        raise
