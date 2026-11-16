"""Platform audio controls, kept inside Advanced Settings."""
from i18n import tr
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog,messagebox

import customtkinter as ctk

from advanced_ui import Choice,section
from platform_audio import KeyStore,STATUS,add_local_key,parse_key_file
from platform_formats import detect_platform
from theme import color
from ui import ACCENT,BG,FONT,INK,LINE,MUTED,WHITE,button,label


SUPPORT=(
    (tr('网易云音乐'),tr('NCM、UC 缓存自动处理；NCM 内的歌曲资料与封面沿用现有整理流程。')),
    (tr('QQ 音乐'),tr('QMC 静态 / Map / RC4、内嵌 EKey、QTag 与 TM；STag / musicex 需匹配的本地 EKey。')),
    (tr('酷狗音乐'),tr('旧版 KGM / KGMA / VPR 与 KGM crypto v3；KGG / crypto v5 需对应 EKey，可导入本地密钥数据库。')),
    (tr('酷我音乐'),tr('旧版 KWM / KWMA；其他新加密变体会保留原件并记录处理结果。')),
    (tr('咪咕音乐'),tr('MG3D：部分旧版 WAV 可自动恢复，其他受支持文件需单曲 fileKey。MGM 暂未支持。')),
)
KEY_CHOICES={"QQ · EKey":"qmc_ekey",tr('QQ · 已解出的原始密钥 (Base64)'):"qmc_raw",
             tr('酷狗 KGG · EKey'):"kgg_ekey",tr('酷狗 KGG · 原始密钥 (Base64)'):"kgg_raw",
             tr('咪咕 · 单曲 fileKey'):"migu_file_key",tr('咪咕 · 直接掩码'):"migu_mask"}


class PlatformPanel:
    def __init__(self,host,advanced):
        self.app=advanced.app
        self.message=tk.StringVar(value=tr('密钥仅在本机使用，整理配置导出不包含密钥。'))
        self.summary=tk.StringVar(value=tr('只读扫描后，在此查看平台文件的支持状态。'))
        pane=section(host,tr('让下载的音乐进入常规曲库'),tr('先备份加密原件，再还原音频、校验并继续补充标签与封面。失败项保留在报告中，其他歌曲继续处理。'))
        advanced.check(pane,tr('自动处理平台加密音频'),"decrypt_enabled")
        advanced.setting(pane,tr('同时解密的文件数'),"decrypt_workers",{str(n):n for n in (1,2,3,4,6,8)},tr('本地流式处理；实际并行数受总音频任务数限制。机械硬盘建议 1–2。'))
        advanced.check(pane,tr('解密后完整解码校验（推荐）'),"decrypt_verify")
        pane=section(host,tr('支持的文件版本'),tr('同一平台可能更换加密方案，扩展名不能保证版本兼容。扫描只检查容器信息，最终以解密和音频校验结果为准。'))
        for name,detail in SUPPORT:
            row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,13))
            label(row,name,size=13,bold=True,width=105).pack(side="left",anchor="n")
            label(row,detail,size=12,color=MUTED,wraplength=690,justify="left").pack(side="left",fill="x",expand=True,padx=(12,0))
        pane=section(host,tr('本地密钥'),tr('导入 JSON / TAB 文本、酷狗 kgg.keys 或 KGMusicV3.db，或为单首歌曲粘贴对应密钥。数据库仅从用户选择的文件读取副本，程序不读取账号密码。'))
        self.key_path=ctk.CTkEntry(pane,textvariable=self.app.advanced_values["platform_key_file"],height=36,
                                 fg_color=color("#F7F6FB"),border_color=LINE,text_color=INK,font=(FONT,12),placeholder_text=tr('尚未选择外部密钥文件'))
        self.key_path.pack(fill="x",padx=22,pady=(0,12));self.app.setting_widgets.append(self.key_path)
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,12))
        for text,action,width in ((tr('导入密钥文件'),self.import_keys,138),(tr('添加单曲密钥'),self.add_key,138),
                                  (tr('重查密钥匹配'),self.app._refresh_platform_keys,138),(tr('移除外部文件'),self.clear_file,138)):
            w=button(row,text,action,width=width);w.pack(side="left",padx=(0,10));self.app.setting_widgets.append(w)
        label(pane,variable=self.message,size=11,color=MUTED,wraplength=850,justify="left").pack(anchor="w",padx=22,pady=(0,18))
        pane=section(host,tr('本次扫描中的平台音频'))
        label(pane,variable=self.summary,size=13,color=ACCENT,wraplength=850,justify="left").pack(anchor="w",padx=22,pady=(0,12))
        self.pending=ctk.CTkTextbox(pane,height=180,fg_color=color("#F7F6FB"),text_color=MUTED,font=(FONT,12),wrap="word",corner_radius=9)
        self.pending.pack(fill="x",padx=22,pady=(0,18));self.pending.configure(state="disabled")
        self.refresh()

    def refresh(self):
        if not self.app.winfo_exists():return
        keys=KeyStore(self.app.advanced_values["platform_key_file"].get())
        issues=" · ".join(keys.issues)
        self.message.set(tr('已载入 {0:,} 条本地密钥记录。密钥不写入日志、报告或导出配置。').format(len(keys.entries))+("\n"+issues if issues else ""))
        items=[i for i in self.app.items if i.crypto]
        counts=Counter(i.crypto.get("state","auto") for i in items)
        self.summary.set(tr('{0:,} 个平台文件').format(len(items))+(" · "+" · ".join(f"{STATUS.get(k,k)} {v}" for k,v in counts.items()) if counts else tr(' · 扫描后显示支持状态')))
        pending=[i for i in items if i.crypto.get("state") not in ("auto","decoded")]
        text="\n\n".join(f"{i.rel}\n{STATUS.get(i.crypto.get('state'), tr('待处理'))} · {i.crypto.get('detail', '')}" for i in pending[:50])
        if len(pending)>50:text+=tr('\n\n另有 {0:,} 项，详见扫描预览和运行报告。').format(len(pending) - 50)
        self.pending.configure(state="normal");self.pending.delete("1.0","end")
        self.pending.insert("1.0",text or (tr('当前没有需要补充密钥或未支持版本的文件。') if items else tr('选择源文件夹并执行只读扫描。')));self.pending.configure(state="disabled")

    def import_keys(self):
        path=filedialog.askopenfilename(parent=self.app,title=tr('导入本地密钥文件'),filetypes=[(tr('密钥记录 / 酷狗数据库'),"*.json *.txt *.tsv *.key *.keys *.db"),(tr('所有文件'),"*.*")])
        if not path:return
        try:
            rows=parse_key_file(path)
            if not rows:raise ValueError(tr('文件中没有有效的密钥记录'))
            self.app.advanced_values["platform_key_file"].set(path)
            self.app._save();self.refresh();self.app._refresh_platform_keys()
        except Exception as exc:messagebox.showerror(tr('无法导入密钥'),str(exc),parent=self.app)

    def clear_file(self):
        self.app.advanced_values["platform_key_file"].set("")
        self.app._save();self.refresh();self.app._refresh_platform_keys()

    def add_key(self):
        if self.app.busy:return
        dialog=ctk.CTkToplevel(self.app);dialog.title(tr('添加单曲密钥'));dialog.geometry("700x440");dialog.resizable(False,False)
        dialog.configure(fg_color=BG);dialog.transient(self.app)
        label(dialog,tr('为一首歌匹配密钥'),size=23,bold=True).pack(anchor="w",padx=28,pady=(24,8))
        label(dialog,tr('选择本机音乐文件，粘贴你已有的对应密钥。咪咕 fileKey 的大小写需与原值一致。'),size=12,color=MUTED,wraplength=640,justify="left").pack(anchor="w",padx=28,pady=(0,18))
        path=tk.StringVar();kind=tk.StringVar(value="qmc_ekey");secret=tk.StringVar();error=tk.StringVar()
        _,selected=self.app._selected()
        if selected and selected.crypto:path.set(str(selected.path))
        row=ctk.CTkFrame(dialog,fg_color="transparent");row.pack(fill="x",padx=28,pady=(0,14))
        entry=ctk.CTkEntry(row,textvariable=path,height=36,fg_color=WHITE,text_color=INK,border_color=LINE);entry.pack(side="left",fill="x",expand=True,padx=(0,10))
        def browse():
            value=filedialog.askopenfilename(parent=dialog,title=tr('选择需要密钥的音频文件'))
            if value:path.set(value)
        button(row,tr('选择文件'),browse,width=100).pack(side="right")
        Choice(dialog,kind,KEY_CHOICES,width=380).pack(anchor="w",padx=28,pady=(0,14))
        label(dialog,tr('对应密钥'),size=12,color=MUTED).pack(anchor="w",padx=28,pady=(0,5))
        key_entry=ctk.CTkEntry(dialog,textvariable=secret,show="•",height=38,fg_color=WHITE,text_color=INK,border_color=LINE,placeholder_text=tr('粘贴对应密钥'))
        key_entry.pack(fill="x",padx=28,pady=(0,12))
        label(dialog,variable=error,size=12,color=MUTED,wraplength=640,justify="left").pack(anchor="w",padx=28,pady=(0,10))
        def close():secret.set("");dialog.destroy()
        def save():
            try:
                file=Path(path.get()).resolve()
                if not file.is_file():raise ValueError(tr('请选择存在的音频文件'))
                family=detect_platform(file)
                if kind.get().startswith("qmc") and family!="qq":raise ValueError(tr('QQ 密钥需要对应的 QMC / MFLAC / MGG 文件'))
                if kind.get().startswith("kgg") and family!="kugou":raise ValueError(tr('酷狗 KGG 密钥需要对应的 KGG / KGM v5 文件'))
                if kind.get().startswith("migu") and family!="migu":raise ValueError(tr('咪咕 fileKey 用于 MG3D 文件；MGM 暂未支持'))
                add_local_key(file,secret.get(),kind.get());close()
                self.app._save();self.refresh();self.app._refresh_platform_keys()
            except Exception as exc:error.set(str(exc))
        row=ctk.CTkFrame(dialog,fg_color="transparent");row.pack(side="bottom",fill="x",padx=28,pady=(12,24))
        button(row,tr('保存密钥'),save,primary=True,width=130).pack(side="right")
        button(row,tr('取消'),close,width=90).pack(side="right",padx=(0,10))
        dialog.protocol("WM_DELETE_WINDOW",close);dialog.bind("<Escape>",lambda e:close())
        from dialogs import center
        center(self.app,dialog)
