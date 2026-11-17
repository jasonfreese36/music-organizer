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
            from model import Settings
            assert app._settings_value()==Settings(),"First-run processing defaults changed"
            a=Path(temp)/"A";b=Path(temp)/"B"
            a.mkdir();b.mkdir();(a/"Nested").mkdir()
            a=a.resolve();b=b.resolve()
            from source_ui import SourceManager
            dialog=SourceManager(app);dialog.add_path(a);dialog.add_path(b);dialog.add_path(a);app.update()
            assert len(dialog.paths)==2
            try:dialog.add_path(a/"Nested")
            except ValueError:pass
            else:raise AssertionError("Nested roots accepted")
            dialog.listing.selection_set("1");dialog.move(-1)
            dialog.apply();app.update()
            assert app._source_paths()==[str(b),str(a)]
            assert app.scanned_source is None and app.run_button.cget("state")=="disabled"
            saved=__import__("json").loads(app.config_path.read_text(encoding="utf-8"))
            assert saved["extra_sources"]==[str(a)]
            app.show_page("settings");app.advanced.tabs.set(tr("音频精调"));app.update()
            # Exercise delayed visibility too, rather than just widget values.
            app.advanced.tabs.set(tr("外观"));app.advanced.tabs.set(tr("音频精调"))
            import tkinter as tk
            settled=tk.BooleanVar(value=False);app.after(160,lambda:settled.set(True));app.wait_variable(settled)
            assert app.advanced.tabs.tab(tr("音频精调")).winfo_ismapped(),"Audio tuning tab became hidden"
            fields=app.advanced_values;dsp=app.advanced.dsp_panel
            assert all(w.cget("state")=="disabled" for w in dsp.groups["soxr"])
            dsp.preset("33");app.update()
            assert app._settings_value().soxr_precision==33
            fields["soxr_precision"].set("20.5")
            try:app._settings_value()
            except ValueError:pass
            else:raise AssertionError("Fractional integer setting was truncated")
            fields["soxr_precision"].set(33)
            assert all(w.cget("state")=="disabled" for w in dsp.groups["swr"])
            fields["resample_cutoff_enabled"].set(True);fields["resample_cutoff"].set(98.25)
            fields["dsd_advanced"].set(True);fields["dsd_gain_db"].set(-2.5);app.update()
            assert all(w.cget("state")=="normal" for w in dsp.groups["dsd"])
            app._save()
            saved=__import__("json").loads(app.config_path.read_text(encoding="utf-8"))
            assert saved["advanced"]["resample_cutoff"]==98.25 and saved["advanced"]["dsd_gain_db"]==-2.5
            app.busy=True;app._state();app.update()
            assert app.sources_button.cget("state")=="disabled"
            assert all(w.cget("state")=="disabled" for widgets in dsp.groups.values() for w in widgets)
            app.busy=False;app._state();dsp.preset("default");app.update()
            assert app._settings_value()==Settings()
            result.update(multiple_source_controls=True,source_order=True,source_persistence=True,dsp_controls=True,
                          inactive_engine_disabled=True,fractional_controls_persist=True,busy_controls=True,defaults_preserved=True)
            app.show_page("settings");app.advanced.tabs.set(tr("苹果设备"));app.update()
            fields=app.advanced_values
            fields["output_profile"].set("ios");fields["apple_quality"].set("lossless")
            app.source.set(str(Path(temp)/"Disconnected source"));app.advanced.apple_panel.refresh()
            assert app.advanced.apple_panel.locations.get()
            app.source.set(str(b))
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
