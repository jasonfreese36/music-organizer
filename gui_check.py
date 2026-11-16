"""Exercise the real GUI in an isolated state directory for packaged-build QA."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def check_gui():
    previous=os.environ.get("LOCALAPPDATA")
    app=None
    with tempfile.TemporaryDirectory(prefix="MusicOrganizer-GuiCheck-") as temp:
        try:
            os.environ["LOCALAPPDATA"]=temp
            from gui import App
            from i18n import get_language,tr
            app=App();app.update()
            assert app.winfo_viewable(),"Main window is not viewable"
            assert app.winfo_width()>=600 and app.winfo_height()>=400,"Invalid window geometry"
            result=dict(language=get_language(),viewable=bool(app.winfo_viewable()),width=app.winfo_width(),height=app.winfo_height())
            app.show_page("settings");app.advanced.tabs.set(tr("苹果设备"));app.update()
            fields=app.advanced_values
            fields["output_profile"].set("ios");fields["apple_quality"].set("lossless")
            fields["apple_archive_mode"].set("separate");fields["apple_archive_folder"].set(str(Path(temp)/"Originals"));app.update()
            assert app.advanced.apple_panel.path.cget("state")=="normal"
            assert app._settings_value().apple_quality=="lossless"
            fields["output_profile"].set("ipod");fields["ipod_model"].set("universal");app.update()
            assert fields["apple_quality"].get()=="standard"
            assert "lossless" not in app.advanced.apple_panel.quality.choices.values()
            fields["output_profile"].set("library");app.update()
            assert app.advanced.apple_panel.path.cget("state")=="disabled"
            for mode in ("dark","light"):
                app.appearance.set(mode);app.update()
                import customtkinter as ctk
                assert ctk.get_appearance_mode().lower()==mode
            for page in app.pages:
                app.show_page(page);app.update()
            result.update(device_controls=True,archive_controls=True,model_constraints=True,light_and_dark=True)
            captured=[];environments=[];original=subprocess.Popen
            def capture(command,**kwargs):
                captured.append(command);environments.append(kwargs.get("env",{}))
            try:
                subprocess.Popen=capture
                app.language.set("zh_CN" if get_language()=="en" else "en")
                app._restart_language();app=None
            finally:subprocess.Popen=original
            assert len(captured)==1 and Path(captured[0][0]).is_file(),captured
            assert captured[0][-2]=="--language"
            assert all(not key.startswith("NUITKA_ONEFILE_") and key!="NUITKA_ORIGINAL_ARGV0" for key in environments[0])
            if "__compiled__" in globals() or getattr(sys,"frozen",False):
                assert Path(captured[0][0]).suffix.lower()==".exe" and "pythonw" not in Path(captured[0][0]).name.lower(),captured
            if "__compiled__" in globals():assert Path(captured[0][0]).resolve()==Path(sys.argv[0]).resolve()
            result["restart_command_valid"]=True
            return result
        finally:
            if app is not None:app.destroy()
            if previous is None:os.environ.pop("LOCALAPPDATA",None)
            else:os.environ["LOCALAPPDATA"]=previous
