"""Point-and-click conversion rule editor; users never type executable expressions."""
import copy
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from advanced_ui import Choice,RATES
from rules import validate_rules
from theme import color,walk
from ui import ACCENT,FONT,INK,LINE,MUTED,TINT,WHITE,button,card,label,tree

FIELDS={"来源格式":"format","音频码率 (kbps)":"bitrate","采样率 (Hz)":"sample_rate","位深 (bit)":"bits",
        "声道数":"channels","源文件大小 (MB)":"size_mb","是否无损":"lossless"}
FORMATS={"AAC":"aac","MP3":"mp3","FLAC":"flac","ALAC":"alac","WAV / PCM":"wav","DSD":"dsd","APE":"ape","WavPack":"wavpack","TTA":"tta","TAK":"tak",
         "WMA":"wma","Ogg Vorbis":"vorbis","Opus":"opus","MP2":"mp2","AC3":"ac3","DTS":"dts","Musepack":"mpc","其他格式":"other"}
COMPARE={"大于 >":"gt","大于或等于 ≥":"ge","小于 <":"lt","小于或等于 ≤":"le","等于 =":"eq"}
EXAMPLES={
    "AAC > 256 kbps → MP3":dict(name="高码率 AAC 转 MP3",enabled=True,match="all",conditions=[dict(field="format",op="is",value="aac"),dict(field="bitrate",op="gt",value=256)],actions=dict(format="mp3")),
    "高于 96 kHz 的无损 → 96 kHz FLAC":dict(name="高采样率无损降至 96 kHz",enabled=True,match="all",conditions=[dict(field="lossless",op="is",value=True),dict(field="sample_rate",op="gt",value=96000)],actions=dict(format="flac",resample_mode="limit",sample_rate=96000)),
    "所有无损 → MP3 V0":dict(name="无损生成 MP3 便携版",enabled=True,match="all",conditions=[dict(field="lossless",op="is",value=True)],actions=dict(format="mp3",mp3_mode="vbr",mp3_vbr=0)),
}


class ConditionRow(ctk.CTkFrame):
    def __init__(self,master,manager,condition):
        super().__init__(master,fg_color="transparent")
        self.manager=manager
        self.field=tk.StringVar(value=condition["field"])
        self.op=tk.StringVar(value=condition["op"])
        self.value=tk.StringVar(value=str(condition["value"]))
        self.grid_columnconfigure(2,weight=1)
        Choice(self,self.field,FIELDS,width=175,command=self.field_changed).grid(row=0,column=0,padx=(0,7),sticky="w")
        self.right=ctk.CTkFrame(self,fg_color="transparent");self.right.grid(row=0,column=1,columnspan=2,sticky="ew")
        self.right.grid_columnconfigure(1,weight=1)
        self.render(condition["value"])
        button(self,"×",lambda:manager.remove_condition(self),width=32).grid(row=0,column=3,padx=(7,0))
        for variable in (self.field,self.op,self.value):variable.trace_add("write",lambda *a:manager.changed())

    def field_changed(self):
        self.op.set("is" if self.field.get() in ("format","lossless") else "gt")
        self.render("aac" if self.field.get()=="format" else True if self.field.get()=="lossless" else 256 if self.field.get()=="bitrate" else 96000 if self.field.get()=="sample_rate" else 16 if self.field.get()=="bits" else 2)
        self.manager.changed()

    def render(self,value):
        for child in self.right.winfo_children():child.destroy()
        symbolic=self.field.get() in ("format","lossless")
        Choice(self.right,self.op,{"等于":"is","不等于":"is_not"} if symbolic else COMPARE,width=140).grid(row=0,column=0,padx=(0,7))
        if symbolic:
            choices=FORMATS if self.field.get()=="format" else {"无损":True,"有损":False}
            self.value.set(str(value))
            Choice(self.right,self.value,choices,width=125).grid(row=0,column=1,sticky="ew")
        else:
            self.value.set(str(value))
            ctk.CTkEntry(self.right,textvariable=self.value,width=125,height=35,text_color=INK,fg_color=color("#F7F6FB"),border_color=LINE,font=(FONT,12)).grid(row=0,column=1,sticky="ew")

    def data(self):
        field=self.field.get();raw=self.value.get()
        if field=="format":value=raw
        elif field=="lossless":value=raw in ("True","1")
        else:
            try:value=float(raw)
            except ValueError as exc:raise ValueError("条件阈值请填写数值，不用输入单位或比较符号") from exc
        return dict(field=field,op=self.op.get(),value=value)


class RuleManager(ctk.CTkFrame):
    def __init__(self,master,app):
        super().__init__(master,fg_color="transparent")
        self.app=app;self.index=None;self.dirty=False;self.loading=False;self.condition_rows=[]
        self.grid_columnconfigure(0,weight=0);self.grid_columnconfigure(1,weight=1);self.grid_rowconfigure(1,weight=1)
        intro=ctk.CTkFrame(self,fg_color="transparent");intro.grid(row=0,column=0,columnspan=2,sticky="ew",pady=(5,14))
        label(intro,"条件 → 处理动作",size=16,bold=True).pack(side="left")
        label(intro,"从上到下匹配，只采用第一条命中的启用规则。没有命中时沿用默认转换设置。",size=11,color=MUTED,wraplength=660,justify="right").pack(side="right")
        left=card(self,width=285);left.grid(row=1,column=0,sticky="ns",padx=(0,15));left.grid_propagate(False)
        left.grid_columnconfigure(0,weight=1);left.grid_rowconfigure(1,weight=1)
        label(left,"我的规则",size=15,bold=True).grid(row=0,column=0,sticky="w",padx=18,pady=(18,12))
        holder=ctk.CTkFrame(left,fg_color=WHITE);holder.grid(row=1,column=0,sticky="nsew",padx=10)
        self.list=tree(holder,[("enabled","开关",45),("name","规则 / 优先级",195)],app.scale)
        self.list.bind("<<TreeviewSelect>>",lambda e:self.select())
        order=ctk.CTkFrame(left,fg_color="transparent");order.grid(row=2,column=0,sticky="ew",padx=16,pady=(12,8))
        for name,action,width in (("上移",lambda:self.move(-1),72),("下移",lambda:self.move(1),72),("复制",self.duplicate,72)):
            button(order,name,action,width=width).pack(side="left",padx=(0,6))
        actions=ctk.CTkFrame(left,fg_color="transparent");actions.grid(row=3,column=0,sticky="ew",padx=16,pady=(0,15))
        button(actions,"新增规则",self.add,primary=True,width=140).pack(side="left",padx=(0,7))
        button(actions,"移除",self.remove,width=76).pack(side="left")
        self.right=card(self);self.right.grid(row=1,column=1,sticky="nsew")
        self.right.grid_columnconfigure(0,weight=1);self.right.grid_rowconfigure(0,weight=1)
        self.editor=ctk.CTkScrollableFrame(self.right,fg_color=WHITE,corner_radius=0)
        self.editor.grid(row=0,column=0,sticky="nsew",padx=8,pady=(10,0))
        self.footer=ctk.CTkFrame(self.right,fg_color="transparent");self.footer.grid(row=1,column=0,sticky="ew",padx=20,pady=(10,18))
        self.message=tk.StringVar(value="默认没有规则，不改变 v1.1 的处理方式。")
        label(self.footer,variable=self.message,size=11,color=MUTED,wraplength=410,justify="left").pack(anchor="w",pady=(0,10))
        buttons=ctk.CTkFrame(self.footer,fg_color="transparent");buttons.pack(fill="x")
        button(buttons,"预览命中与路径",app._preview_plan,width=150).pack(side="left")
        self.save_button=button(buttons,"保存规则",self.commit_pending,primary=True,width=125)
        self.save_button.pack(side="right")
        self.reload()

    def changed(self):
        if self.loading or self.index is None:return
        self.dirty=True;self.message.set("有未保存的更改 · 点击保存规则，或直接预览。")

    def reload(self,selected=None):
        self.loading=True;self.dirty=False;self.index=None
        self.list.delete(*self.list.get_children())
        for i,r in enumerate(self.app.custom_rules):self.list.insert("","end",iid=str(i),values=("开" if r["enabled"] else "关",f"{i+1:02d}  {r['name']}"),tags=("stripe",) if i%2 else ())
        if selected is None and self.app.custom_rules:selected=0
        self.index=selected
        if selected is not None:self.list.selection_set(str(selected));self.list.see(str(selected))
        self.build_editor()
        self.loading=False

    def select(self):
        if self.loading or self.app.busy:return
        selected=self.list.selection()
        if not selected:return
        new=int(selected[0])
        if new==self.index:return
        if not self.commit_pending():
            if self.index is not None:self.list.selection_set(str(self.index))
            return
        self.index=new;self.loading=True;self.build_editor();self.loading=False

    def build_editor(self):
        for child in self.editor.winfo_children():child.destroy()
        self.condition_rows=[]
        if self.index is None:
            label(self.editor,"用点选创建第一条规则",size=19,bold=True).pack(anchor="w",padx=16,pady=(24,12))
            label(self.editor,"选择条件、填写阈值，再选择处理动作。\n例如：来源格式为 AAC 且码率大于 256 kbps → 转为 MP3。",size=12,color=MUTED,wraplength=550,justify="left").pack(anchor="w",padx=16,pady=(0,24))
            label(self.editor,"从示例开始",size=13,bold=True).pack(anchor="w",padx=16,pady=(0,12))
            for name in EXAMPLES:button(self.editor,name,lambda n=name:self.add(n),width=390).pack(anchor="w",padx=16,pady=(0,10))
            self.save_button.configure(state="disabled");return
        self.save_button.configure(state="normal")
        rule=self.app.custom_rules[self.index]
        top=ctk.CTkFrame(self.editor,fg_color="transparent");top.pack(fill="x",padx=12,pady=(10,16))
        self.name=tk.StringVar(value=rule["name"]);self.enabled=tk.BooleanVar(value=rule["enabled"]);self.match=tk.StringVar(value=rule["match"])
        ctk.CTkEntry(top,textvariable=self.name,height=38,fg_color=color("#F7F6FB"),border_color=LINE,text_color=INK,font=(FONT,14)).pack(side="left",fill="x",expand=True,padx=(0,16))
        ctk.CTkSwitch(top,text="启用",variable=self.enabled,progress_color=ACCENT,text_color=INK,width=75,font=(FONT,12)).pack(side="right")
        row=ctk.CTkFrame(self.editor,fg_color="transparent");row.pack(fill="x",padx=12,pady=(0,12))
        label(row,"当以下条件",size=13,bold=True).pack(side="left",padx=(0,12))
        Choice(row,self.match,{"全部满足（且）":"all","任一满足（或）":"any"},width=185).pack(side="left")
        self.conditions=ctk.CTkFrame(self.editor,fg_color="transparent");self.conditions.pack(fill="x",padx=12,pady=(0,10))
        for condition in rule["conditions"]:self.add_condition(condition,mark=False)
        button(self.editor,"＋ 添加条件",self.add_condition,width=130).pack(anchor="w",padx=12,pady=(0,22))
        label(self.editor,"执行以下处理",size=14,bold=True).pack(anchor="w",padx=12,pady=(0,12))
        self.action_vars={}
        actions=rule["actions"]
        fields=[("输出格式","format",{"沿用默认":"inherit","FLAC":"flac","MP3":"mp3","AAC (.m4a)":"aac"}),
                ("采样率策略","resample_mode",{"沿用默认":"inherit","保留原采样率":"preserve","仅降到上限":"limit","统一采样率":"fixed"}),
                ("采样率 / 上限 (Hz)","sample_rate",{"沿用默认":"inherit",**RATES}),
                ("FLAC 位深","pcm_bits",{"沿用默认":"inherit","保留原位深":0,"16 bit":16,"24 bit":24,"32 bit":32}),
                ("声道","channels",{"沿用默认":"inherit","保留原声道":"preserve","立体声":"stereo","单声道":"mono"}),
                ("同编码来源","reencode_lossy",{"沿用默认":"inherit","保留已有编码":False,"也重新编码":True}),
                ("MP3 编码模式","mp3_mode",{"沿用默认":"inherit","VBR":"vbr","CBR":"cbr"}),
                ("MP3 CBR (kbps)","mp3_kbps",{"沿用默认":"inherit",**{str(n):n for n in (64,96,128,160,192,224,256,320)}}),
                ("MP3 VBR 品质","mp3_vbr",{"沿用默认":"inherit",**{f"V{n}":n for n in range(10)}}),
                ("AAC (kbps / 立体声)","aac_kbps",{"沿用默认":"inherit",**{str(n):n for n in (96,128,160,192,224,256,320,384,448,512)}})]
        for title,key,choices in fields:
            row=ctk.CTkFrame(self.editor,fg_color="transparent");row.pack(fill="x",padx=12,pady=(0,13))
            label(row,title,size=12).pack(side="left")
            variable=tk.StringVar(value=str(actions.get(key,"inherit")));self.action_vars[key]=(variable,choices)
            Choice(row,variable,choices,width=225).pack(side="right")
            variable.trace_add("write",lambda *a:self.changed())
        label(self.editor,"规则使用来源音频的实际参数，阈值不含封面体积；未知码率不会命中码率条件。更换格式或启用同编码重新编码时才应用有损编码器参数。",size=11,color=MUTED,wraplength=530,justify="left").pack(anchor="w",padx=12,pady=(3,20))
        for variable in (self.name,self.enabled,self.match):variable.trace_add("write",lambda *a:self.changed())
        self.dirty=False;self.message.set(f"优先级 {self.index+1} · 已保存；第一条命中后不继续叠加后续规则。")

    def add_condition(self,condition=None,mark=True):
        if self.app.busy:return
        if len(self.condition_rows)>=8:self.message.set("每条规则最多 8 个条件。");return
        if not isinstance(condition,dict):condition=dict(field="bitrate",op="gt",value=256)
        row=ConditionRow(self.conditions,self,condition);row.pack(fill="x",pady=(0,9));self.condition_rows.append(row)
        if mark:self.changed()

    def remove_condition(self,row):
        if self.app.busy:return
        if len(self.condition_rows)<=1:self.message.set("每条规则至少保留一个条件。");return
        self.condition_rows.remove(row);row.destroy();self.changed()

    def commit_pending(self):
        if not self.dirty or self.index is None:return True
        if self.app.busy:return False
        try:
            actions={}
            for key,(variable,choices) in self.action_vars.items():
                raw=variable.get()
                value=next((v for v in choices.values() if str(v)==raw),raw)
                if value!="inherit":actions[key]=value
            rule=dict(name=self.name.get().strip(),enabled=self.enabled.get(),match=self.match.get(),
                      conditions=[r.data() for r in self.condition_rows],actions=actions)
            validate_rules([rule])
            self.app.custom_rules[self.index]=rule
            self.list.item(str(self.index),values=("开" if rule["enabled"] else "关",f"{self.index+1:02d}  {rule['name']}"))
            self.dirty=False;self.message.set("规则已保存 · 预览可检查命中结果。")
            self.app._save();self.app.advanced.queue_preview()
            return True
        except Exception as exc:
            self.message.set(str(exc));return False

    def add(self,example=None):
        if self.app.busy or not self.commit_pending():return
        if len(self.app.custom_rules)>=100:self.message.set("最多支持 100 条规则。");return
        rule=copy.deepcopy(EXAMPLES[example]) if example in EXAMPLES else dict(name="新规则",enabled=True,match="all",conditions=[dict(field="format",op="is",value="aac")],actions=dict(format="mp3"))
        self.app.custom_rules.append(rule);self.reload(len(self.app.custom_rules)-1);self.app._save();self.app.advanced.queue_preview()

    def remove(self):
        if self.app.busy or self.index is None:return
        del self.app.custom_rules[self.index]
        self.reload();self.app._save();self.app.advanced.queue_preview()

    def move(self,direction):
        if self.app.busy or self.index is None or not self.commit_pending():return
        new=self.index+direction
        if not 0<=new<len(self.app.custom_rules):return
        rules=self.app.custom_rules;rules[self.index],rules[new]=rules[new],rules[self.index]
        self.reload(new);self.app._save()

    def duplicate(self):
        if self.app.busy or self.index is None or not self.commit_pending():return
        if len(self.app.custom_rules)>=100:return
        rule=copy.deepcopy(self.app.custom_rules[self.index]);rule["name"]=(rule["name"][:72]+" 副本")
        self.app.custom_rules.insert(self.index+1,rule);self.reload(self.index+1);self.app._save()

    def set_busy(self,busy):
        for widget in walk(self):
            if isinstance(widget,(ctk.CTkButton,ctk.CTkEntry,ctk.CTkOptionMenu,ctk.CTkSwitch)):
                widget.configure(state="disabled" if busy else "normal")
        if not busy and self.index is None:self.save_button.configure(state="disabled")
