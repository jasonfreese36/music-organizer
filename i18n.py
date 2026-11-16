"""Process-wide UI language; release metadata and user text are never translated."""
import json
import os
from pathlib import Path


def _preference():
    selected=os.environ.get("MUSIC_ORGANIZER_LANGUAGE")
    if selected is None:
        path=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData/Local")))/"MusicOrganizer/Settings.json"
        try:selected=json.loads(path.read_text(encoding="utf-8")).get("language")
        except (OSError,ValueError,AttributeError):pass
    return selected if selected in ("zh_CN","en") else "zh_CN"


_language=_preference()
_catalog=None


def get_language():return _language


def select_language(language):
    global _language
    if language not in ("zh_CN","en"):raise ValueError("Invalid language")
    _language=language


def tr(message):
    global _catalog
    if _language=="zh_CN":return message
    if _catalog is None:
        import sys
        root=Path(getattr(sys,"_MEIPASS",Path(__file__).parent))
        _catalog=json.loads((root/"resources/i18n/en.json").read_text(encoding="utf-8"))
    return _catalog.get(message,message)
