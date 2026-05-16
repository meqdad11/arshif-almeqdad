import os
import re
import sys
import fitz
import easyocr
import numpy as np
from PIL import Image
import io
import threading
import json
import time
import urllib.request
import subprocess
import tempfile
import customtkinter as ctk
from tkinter import filedialog, messagebox
 
# ==================== الإعدادات ====================
 
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
MEMORY_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_vouchers.json")
LOGO_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_final.png")
ICON_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
 
CURRENT_VERSION = "1.3"
 
VERSION_URL  = "https://raw.githubusercontent.com/meqdad11/arshif-almeqdad/main/version.json"
DOWNLOAD_URL = "https://github.com/meqdad11/arshif-almeqdad/releases/latest/download/voucher_processor.exe"
 
DEFAULT_SETTINGS = {
    "header_ratio":        0.30,   # قراءة أولى 30%
    "header_ratio_wide":   0.55,   # قراءة ثانية 55% لو ما لقى
    "languages":           ["ar", "en"],
    "appearance":          "dark",
    # شروط التعرف العامة — يكفي واحد + نوع السند
    "id_conditions": [
        {"label": "السجل التجاري", "value": "4030100012"},
        {"label": "الرقم الضريبي", "value": "311250175400003"},
    ],
    # شروط خاصة للمصروفات الضريبية فقط — اسم الشركة
    "tax_expense_markers": ["البصمة", "Albasma"],
    "voucher_types": {
        "سند الصرف":        {"folder": "سندات صرف"},
        "سند القبض":        {"folder": "سندات قبض"},
        "سندات قيد يومية": {"folder": "قبود يومية"},
        "قيد يومية":        {"folder": "قبود يومية"},
        "يومية":            {"folder": "قبود يومية"},
        "رواتب":            {"folder": "قبود استحقاق رواتب"},
        "مصروفات ضريبية":  {"folder": "مصروفات ضريبية"},
    },
    "last_pdf":     "",
    "last_archive": ""
}
 
# ==================== الذاكرة ====================
 
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            return json.load(open(MEMORY_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {}
 
def save_memory(mem):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)
 
def is_processed(mem, voucher_no):
    return voucher_no in mem
 
def mark_processed(mem, voucher_no, folder, archive_root):
    mem[voucher_no] = {
        "folder":   folder,
        "path":     os.path.join(archive_root, folder, f"{voucher_no}.pdf"),
        "archived": time.strftime("%Y-%m-%d %H:%M")
    }
 
# ==================== الإعدادات ====================
 
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            data = json.load(open(SETTINGS_FILE, "r", encoding="utf-8"))
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()
 
def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
 
# ==================== الألوان ====================
 
PURPLE       = "#7c3aed"
PURPLE_LIGHT = "#a855f7"
PURPLE_GLOW  = "#c084fc"
SUCCESS      = "#4ade80"
DANGER       = "#f87171"
WARNING      = "#fbbf24"
INFO         = "#38bdf8"
 
def colors(mode):
    if mode == "dark":
        return {"bg": "#0d0b1a", "card": "#1a1530", "sidebar": "#120f22",
                "text": "#e2d9f3", "sub": "#9d8ec0", "log": "#0a0815"}
    return {"bg": "#f0eeff", "card": "#ffffff", "sidebar": "#ddd5ff",
            "text": "#1a0a3d", "sub": "#6b5b9e", "log": "#e8e0ff"}
 
 
# ==================== منطق التعرف على السند ====================
 
def detect_voucher(text, settings):
    """
    يرجع (is_main, folder) أو (False, None)
 
    المنطق:
    1. المصروفات الضريبية: اسم الشركة + "مصروفات ضريبية"
    2. بقية السندات: شرط تعرف عام (رقم ضريبي أو سجل) + نوع السند
    """
 
    # ── المصروفات الضريبية ──
    tax_markers = settings.get("tax_expense_markers", [])
    has_company = any(m in text for m in tax_markers)
    if has_company and "مصروفات ضريبية" in text:
        return True, settings["voucher_types"].get(
            "مصروفات ضريبية", {"folder": "مصروفات ضريبية"})["folder"]
 
    # ── بقية السندات ──
    id_conditions = [c["value"] for c in settings.get("id_conditions", []) if c.get("value")]
    has_id = any(cond in text for cond in id_conditions)
    if not has_id:
        return False, None
 
    # ترتيب البحث مهم: الأطول أولاً عشان "سند القبض" يُلقى قبل "قبض"
    type_priority = [
        "سند الصرف", "سند القبض",
        "سندات قيد يومية", "قيد يومية",
        "رواتب", "يومية"
    ]
    for vtype in type_priority:
        if vtype in text and vtype in settings["voucher_types"]:
            return True, settings["voucher_types"][vtype]["folder"]
 
    # بحث احتياطي في بقية الأنواع
    for vtype, info in settings["voucher_types"].items():
        if vtype not in type_priority and vtype in text:
            return True, info["folder"]
 
    return False, None
 
 
def read_page_text(page, reader, settings, wide=False):
    """قراءة الصفحة — نصية أولاً، OCR ثانياً"""
    text = page.get_text("text")
    if len(text.strip()) >= 50:
        return text
 
    ratio = settings["header_ratio_wide"] if wide else settings["header_ratio"]
    pix   = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img   = Image.open(io.BytesIO(pix.tobytes()))
    w, h  = img.size
    crop  = img.crop((0, 0, w, int(h * ratio)))
    text  = ' '.join(reader.readtext(np.array(crop), detail=0))
    del img, pix, crop
    return text
 
 
# ==================== Splash Screen ====================
 
class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#0d0b1a")
 
        w, h = 420, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
 
        ctk.CTkLabel(self, text="ارشيف المقداد",
                     font=("Segoe UI", 26, "bold"), text_color=PURPLE_GLOW).pack(pady=(45, 4))
        ctk.CTkLabel(self, text=f"الإصدار {CURRENT_VERSION}",
                     font=("Segoe UI", 11), text_color="#9d8ec0").pack()
        ctk.CTkFrame(self, height=1, fg_color=PURPLE, width=300).pack(pady=16)
 
        self.status_lbl = ctk.CTkLabel(self, text="جاري التحميل...",
                                        font=("Segoe UI", 12), text_color="#9d8ec0")
        self.status_lbl.pack()
 
        self.bar = ctk.CTkProgressBar(self, width=300, height=10,
                                       progress_color=PURPLE, fg_color="#1a1530")
        self.bar.pack(pady=14)
        self.bar.set(0)
 
        ctk.CTkLabel(self, text="© 2026 المقداد حسن",
                     font=("Segoe UI", 9), text_color="#4a3a6e").pack(pady=(10, 0))
        self.update()
 
    def set_status(self, text: str, progress: float):
        self.status_lbl.configure(text=text)
        self.bar.set(progress)
        self.update()
 
    def close(self):
        self.destroy()
 
 
# ==================== Auto Updater ====================
 
class UpdaterWindow(ctk.CTkToplevel):
    def __init__(self, parent, new_version: str):
        super().__init__(parent)
        self.parent = parent
        self.title("تحديث متاح")
        self.geometry("420x260")
        self.resizable(False, False)
        self.configure(fg_color="#0d0b1a")
        self.grab_set()
 
        ctk.CTkLabel(self, text="🎉 تحديث جديد متاح!",
                     font=("Segoe UI", 18, "bold"), text_color=PURPLE_GLOW).pack(pady=(28, 8))
        ctk.CTkLabel(self,
                     text=f"الإصدار الحالي: {CURRENT_VERSION}   ←   الإصدار الجديد: {new_version}",
                     font=("Segoe UI", 11), text_color="#9d8ec0").pack()
 
        self.progress = ctk.CTkProgressBar(self, width=340, height=12,
                                            progress_color=PURPLE, fg_color="#1a1530")
        self.progress.pack(pady=18)
        self.progress.set(0)
 
        self.status = ctk.CTkLabel(self, text="", font=("Segoe UI", 10), text_color="#9d8ec0")
        self.status.pack()
 
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(pady=18)
        self.update_btn = ctk.CTkButton(bf, text="تحديث الآن", width=150, height=40,
                                         fg_color=PURPLE, hover_color=PURPLE_LIGHT,
                                         command=self._start_update)
        self.update_btn.pack(side="left", padx=8)
        ctk.CTkButton(bf, text="لاحقاً", width=100, height=40,
                      fg_color="#3b1f6e", hover_color=DANGER,
                      command=self.destroy).pack(side="left", padx=8)
 
    def _start_update(self):
        self.update_btn.configure(state="disabled")
        threading.Thread(target=self._download, daemon=True).start()
 
    def _download(self):
        try:
            self.status.configure(text="جاري التحميل...")
            exe_path = sys.executable if getattr(sys, 'frozen', False) else None
            if not exe_path:
                self.status.configure(text="التحديث التلقائي يعمل فقط مع ملف الـ EXE")
                return
            tmp = tempfile.mktemp(suffix=".exe")
 
            def reporthook(count, block_size, total_size):
                if total_size > 0:
                    pct = min(count * block_size / total_size, 1.0)
                    self.progress.set(pct)
                    self.status.configure(text=f"تحميل {int(pct*100)}%...")
                    self.update()
 
            urllib.request.urlretrieve(DOWNLOAD_URL, tmp, reporthook)
            self.status.configure(text="تم التحميل، جاري التثبيت...")
            self.progress.set(1)
            self.update()
 
            bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
move /y "{tmp}" "{exe_path}"
start "" "{exe_path}"
del "%~f0"
"""
            bat_path = tempfile.mktemp(suffix=".bat")
            with open(bat_path, "w") as f:
                f.write(bat_content)
 
            subprocess.Popen(bat_path, shell=True,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            messagebox.showinfo("تم!", "سيتم إغلاق البرنامج وتثبيت التحديث تلقائياً.")
            self.parent.destroy()
        except Exception as e:
            self.status.configure(text=f"فشل التحديث: {e}")
 
 
def check_for_updates(parent, silent=True):
    def _check():
        try:
            with urllib.request.urlopen(VERSION_URL, timeout=5) as r:
                data = json.loads(r.read().decode())
            latest = data.get("version", CURRENT_VERSION)
            if latest != CURRENT_VERSION:
                parent.after(0, lambda: UpdaterWindow(parent, latest))
            elif not silent:
                parent.after(0, lambda: messagebox.showinfo(
                    "التحديثات", f"أنت تستخدم أحدث إصدار ({CURRENT_VERSION})"))
        except Exception:
            if not silent:
                parent.after(0, lambda: messagebox.showwarning(
                    "التحديثات", "تعذر الاتصال بخادم التحديثات"))
    threading.Thread(target=_check, daemon=True).start()
 
 
# ==================== نافذة الإعدادات ====================
 
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings, on_save):
        super().__init__(parent)
        self.settings  = settings
        self.on_save   = on_save
        self.type_rows = []
        self.cond_rows = []
        self.marker_rows = []
        C = colors(settings.get("appearance", "dark"))
 
        self.title("الإعدادات")
        self.geometry("600x760")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
 
        ctk.CTkLabel(self, text="الإعدادات", font=("Segoe UI", 18, "bold"),
                     text_color=PURPLE_GLOW).pack(pady=(18, 10))
 
        # ── بطاقة عامة ──
        card = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=15)
        card.pack(padx=20, fill="x")
 
        def lbl(r, t):
            ctk.CTkLabel(card, text=f"{t}:", text_color=C["sub"],
                         font=("Segoe UI", 10)).grid(row=r, column=0, sticky="e", padx=15, pady=6)
 
        lbl(0, "نسبة الترويسة (قراءة أولى)")
        sf = ctk.CTkFrame(card, fg_color="transparent")
        sf.grid(row=0, column=1, sticky="w", padx=10)
        self.ratio_var = ctk.DoubleVar(value=settings["header_ratio"] * 100)
        rl = ctk.CTkLabel(sf, text=f"{int(self.ratio_var.get())}%",
                          text_color=PURPLE_LIGHT, width=40)
        rl.pack(side="left")
        ctk.CTkSlider(sf, from_=20, to=60, variable=self.ratio_var, width=200,
                      button_color=PURPLE, progress_color=PURPLE_LIGHT,
                      command=lambda v: rl.configure(text=f"{int(v)}%")).pack(side="left")
 
        lbl(1, "نسبة الترويسة (قراءة موسعة)")
        sf2 = ctk.CTkFrame(card, fg_color="transparent")
        sf2.grid(row=1, column=1, sticky="w", padx=10)
        self.ratio_wide_var = ctk.DoubleVar(value=settings.get("header_ratio_wide", 0.55) * 100)
        rl2 = ctk.CTkLabel(sf2, text=f"{int(self.ratio_wide_var.get())}%",
                           text_color=PURPLE_LIGHT, width=40)
        rl2.pack(side="left")
        ctk.CTkSlider(sf2, from_=40, to=80, variable=self.ratio_wide_var, width=200,
                      button_color=PURPLE, progress_color=PURPLE_LIGHT,
                      command=lambda v: rl2.configure(text=f"{int(v)}%")).pack(side="left")
 
        lbl(2, "لغة القراءة")
        lf = ctk.CTkFrame(card, fg_color="transparent")
        lf.grid(row=2, column=1, sticky="w", padx=10)
        self.lang_ar = ctk.BooleanVar(value="ar" in settings["languages"])
        self.lang_en = ctk.BooleanVar(value="en" in settings["languages"])
        ctk.CTkCheckBox(lf, text="عربي", variable=self.lang_ar,
                        fg_color=PURPLE, text_color=C["text"]).pack(side="left", padx=8)
        ctk.CTkCheckBox(lf, text="انجليزي", variable=self.lang_en,
                        fg_color=PURPLE, text_color=C["text"]).pack(side="left", padx=8)
 
        # ── شروط التعرف العامة ──
        self._section(C, "شروط التعرف العامة", "(رقم ضريبي أو سجل تجاري)", self._add_cond)
        self.cond_scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"], height=90, corner_radius=10)
        self.cond_scroll.pack(padx=20, fill="x")
        for cond in settings.get("id_conditions", []):
            self._add_cond(cond.get("label", ""), cond.get("value", ""))
 
        # ── علامات المصروفات الضريبية ──
        self._section(C, "علامات المصروفات الضريبية", "(اسم الشركة)", self._add_marker)
        self.marker_scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"], height=80, corner_radius=10)
        self.marker_scroll.pack(padx=20, fill="x")
        for marker in settings.get("tax_expense_markers", []):
            self._add_marker(marker)
 
        # ── أنواع السندات ──
        self._section(C, "أنواع السندات", "", self._add_row)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"], height=110, corner_radius=10)
        self.scroll.pack(padx=20, fill="x")
        for kw, info in settings["voucher_types"].items():
            self._add_row(kw, info["folder"])
 
        # ── أزرار ──
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(pady=14)
        ctk.CTkButton(bf, text="حفظ", width=120, fg_color=PURPLE,
                      hover_color=PURPLE_LIGHT, command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(bf, text="افتراضي", width=120, fg_color="#3b1f6e",
                      hover_color=DANGER, command=self._reset).pack(side="left", padx=5)
        ctk.CTkButton(bf, text="تحقق من التحديثات", width=160, fg_color="#1e1040",
                      hover_color=PURPLE,
                      command=lambda: check_for_updates(self.master, silent=False)
                      ).pack(side="left", padx=5)
 
    def _section(self, C, title, subtitle, add_cmd):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(padx=20, pady=(10, 3), fill="x")
        ctk.CTkLabel(h, text=title, text_color=C["sub"],
                     font=("Segoe UI", 11, "bold")).pack(side="left")
        if subtitle:
            ctk.CTkLabel(h, text=subtitle, font=("Segoe UI", 9),
                         text_color=C["sub"]).pack(side="left", padx=6)
        ctk.CTkButton(h, text="+ إضافة", width=90, fg_color=PURPLE,
                      hover_color=PURPLE_LIGHT, command=add_cmd).pack(side="right")
 
    def _add_cond(self, label="", value=""):
        C = colors(self.settings.get("appearance", "dark"))
        row = ctk.CTkFrame(self.cond_scroll, fg_color=C["sidebar"], corner_radius=8)
        row.pack(fill="x", pady=3, padx=5)
        lv = ctk.StringVar(value=label)
        vv = ctk.StringVar(value=value)
        ctk.CTkEntry(row, textvariable=lv, width=110, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="الاسم").pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(row, text="|", text_color=C["sub"]).pack(side="left")
        ctk.CTkEntry(row, textvariable=vv, width=200, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="القيمة").pack(side="left", padx=5)
        ctk.CTkButton(row, text="حذف", width=55, fg_color=DANGER, hover_color="#dc2626",
                      command=lambda r=row, d=(lv, vv): self._del_cond(r, d)).pack(side="left", padx=5)
        self.cond_rows.append((lv, vv))
 
    def _del_cond(self, row, data):
        row.destroy()
        if data in self.cond_rows: self.cond_rows.remove(data)
 
    def _add_marker(self, value=""):
        C = colors(self.settings.get("appearance", "dark"))
        row = ctk.CTkFrame(self.marker_scroll, fg_color=C["sidebar"], corner_radius=8)
        row.pack(fill="x", pady=3, padx=5)
        vv = ctk.StringVar(value=value)
        ctk.CTkEntry(row, textvariable=vv, width=330, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="اسم الشركة أو جزء منه").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(row, text="حذف", width=55, fg_color=DANGER, hover_color="#dc2626",
                      command=lambda r=row, d=vv: self._del_marker(r, d)).pack(side="left", padx=5)
        self.marker_rows.append(vv)
 
    def _del_marker(self, row, data):
        row.destroy()
        if data in self.marker_rows: self.marker_rows.remove(data)
 
    def _add_row(self, kw="", folder=""):
        C = colors(self.settings.get("appearance", "dark"))
        row = ctk.CTkFrame(self.scroll, fg_color=C["sidebar"], corner_radius=8)
        row.pack(fill="x", pady=3, padx=5)
        kv = ctk.StringVar(value=kw)
        fv = ctk.StringVar(value=folder)
        ctk.CTkEntry(row, textvariable=kv, width=140, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="نوع السند").pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(row, text="|", text_color=C["sub"]).pack(side="left")
        ctk.CTkEntry(row, textvariable=fv, width=170, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="اسم المجلد").pack(side="left", padx=5)
        ctk.CTkButton(row, text="حذف", width=55, fg_color=DANGER, hover_color="#dc2626",
                      command=lambda r=row, d=(kv, fv): self._del(r, d)).pack(side="left", padx=5)
        self.type_rows.append((kv, fv))
 
    def _del(self, row, data):
        row.destroy()
        if data in self.type_rows: self.type_rows.remove(data)
 
    def _save(self):
        langs = (["ar"] if self.lang_ar.get() else []) + (["en"] if self.lang_en.get() else [])
        if not langs:
            messagebox.showerror("خطأ", "اختر لغة واحدة على الأقل!"); return
 
        conds = [{"label": lv.get().strip(), "value": vv.get().strip()}
                 for lv, vv in self.cond_rows if vv.get().strip()]
        if not conds:
            messagebox.showerror("خطأ", "أضف شرط تعرف واحد على الأقل!"); return
 
        markers = [vv.get().strip() for vv in self.marker_rows if vv.get().strip()]
 
        nt = {kv.get().strip(): {"folder": fv.get().strip()}
              for kv, fv in self.type_rows if kv.get().strip() and fv.get().strip()}
        if not nt:
            messagebox.showerror("خطأ", "أضف نوع سند واحد على الأقل!"); return
 
        self.settings.update({
            "header_ratio":       round(self.ratio_var.get() / 100, 2),
            "header_ratio_wide":  round(self.ratio_wide_var.get() / 100, 2),
            "languages":          langs,
            "id_conditions":      conds,
            "tax_expense_markers": markers,
            "voucher_types":      nt
        })
        save_settings(self.settings)
        self.on_save(self.settings)
        messagebox.showinfo("تم", "تم حفظ الإعدادات!")
        self.destroy()
 
    def _reset(self):
        if messagebox.askyesno("تأكيد", "إعادة الإعدادات الافتراضية؟"):
            save_settings(DEFAULT_SETTINGS)
            self.on_save(DEFAULT_SETTINGS.copy())
            self.destroy()
 
 
# ==================== الواجهة الرئيسية ====================
 
class VoucherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
 
        self.settings      = load_settings()
        self.memory        = load_memory()
        self.mode          = self.settings.get("appearance", "dark")
        self.C             = colors(self.mode)
        self.reader        = None
        self._reader_ready = False
        self.stop_flag     = False
        self._spin_run     = False
        self._spin_idx     = 0
        self._timer_run    = False
        self._start_time   = None
 
        ctk.set_appearance_mode(self.mode)
        self.title("ارشيف المقداد")
        self.configure(fg_color=self.C["bg"])
        if os.path.exists(ICON_FILE):
            self.iconbitmap(ICON_FILE)
 
        self.pdf_path     = ctk.StringVar(value=self.settings.get("last_pdf", ""))
        self.archive_path = ctk.StringVar(value=self.settings.get("last_archive", ""))
 
        self._show_splash()
 
    # ==================== Splash ====================
 
    def _show_splash(self):
        splash = SplashScreen(self)
        splash.set_status("تحميل الإعدادات...", 0.2)
        self.after(300, lambda: self._splash_step2(splash))
 
    def _splash_step2(self, splash):
        splash.set_status("بناء الواجهة...", 0.5)
        self._build()
        splash.set_status("تحميل نموذج القراءة...", 0.75)
        threading.Thread(target=self._preload_ocr, args=(splash,), daemon=True).start()
 
    def _preload_ocr(self, splash):
        try:
            self.reader = easyocr.Reader(self.settings["languages"])
            self._reader_ready = True
        except Exception:
            self._reader_ready = False
        self.after(0, lambda: self._splash_done(splash))
 
    def _splash_done(self, splash):
        splash.set_status("جاهز!", 1.0)
        self.after(400, lambda: self._open_main(splash))
 
    def _open_main(self, splash):
        splash.close()
        self.state("zoomed")
        self.deiconify()
        self.lift()
        self.after(2000, lambda: check_for_updates(self, silent=True))
 
    # ==================== بناء الواجهة ====================
 
    def _build(self):
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=self.C["sidebar"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
 
        if os.path.exists(LOGO_FILE):
            from PIL import Image as PI
            limg = ctk.CTkImage(PI.open(LOGO_FILE).resize((110, 110)), size=(110, 110))
            ctk.CTkLabel(self.sidebar, image=limg, text="").pack(pady=(22, 4))
 
        ctk.CTkLabel(self.sidebar, text="ارشيف المقداد",
                     font=("Segoe UI", 15, "bold"), text_color=PURPLE_GLOW).pack()
        ctk.CTkLabel(self.sidebar, text=f"v{CURRENT_VERSION}", font=("Segoe UI", 10),
                     text_color=self.C["sub"]).pack(pady=(2, 12))
 
        ctk.CTkFrame(self.sidebar, height=1, fg_color=PURPLE).pack(fill="x", padx=15, pady=4)
 
        self._nav_btns = {}
        for label, cmd in [("الرئيسية", self._show_home),
                           ("الذاكرة", self._show_memory),
                           ("الإعدادات", self._open_settings),
                           ("عن البرنامج", self._show_about)]:
            btn = ctk.CTkButton(self.sidebar, text=label, width=190, height=42,
                                fg_color="transparent", hover_color=PURPLE,
                                text_color=self.C["text"], font=("Segoe UI", 12),
                                command=cmd)
            btn.pack(pady=3, padx=15)
            self._nav_btns[label] = btn
 
        ctk.CTkFrame(self.sidebar, height=1, fg_color=PURPLE).pack(fill="x", padx=15, pady=(12, 4))
 
        self.mode_btn = ctk.CTkButton(
            self.sidebar,
            text="☀️ وضع فاتح" if self.mode == "dark" else "🌙 وضع داكن",
            width=190, height=36, fg_color=PURPLE, hover_color=PURPLE_LIGHT,
            font=("Segoe UI", 11), command=self._toggle_mode)
        self.mode_btn.pack(pady=6, padx=15)
 
        self.content = ctk.CTkFrame(self, fg_color=self.C["bg"], corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)
 
        self._build_home()
        self._build_memory()
        self._build_about()
        self._show_home()
 
    def _nav_color(self, active):
        for label, btn in self._nav_btns.items():
            btn.configure(fg_color=PURPLE if label == active else "transparent")
 
    # ==================== صفحة الرئيسية ====================
 
    def _build_home(self):
        self.home_frame = ctk.CTkFrame(self.content, fg_color=self.C["bg"], corner_radius=0)
 
        hdr = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(22, 5))
        ctk.CTkLabel(hdr, text="فصل السندات المحاسبية",
                     font=("Segoe UI", 22, "bold"), text_color=self.C["text"]).pack(side="left")
        ctk.CTkLabel(hdr, text="صرف • قبض • قيد • رواتب • ضريبي",
                     font=("Segoe UI", 11), text_color=self.C["sub"]).pack(side="left", padx=12)
 
        fc = ctk.CTkFrame(self.home_frame, fg_color=self.C["card"], corner_radius=15)
        fc.pack(fill="x", padx=30, pady=8)
        self._file_row(fc, "ملف PDF:", self.pdf_path, self._choose_pdf)
        self._file_row(fc, "مجلد الأرشيف:", self.archive_path, self._choose_folder)
 
        mid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        mid.pack(fill="x", padx=30, pady=5)
 
        pc = ctk.CTkFrame(mid, fg_color=self.C["card"], corner_radius=15)
        pc.pack(side="left", fill="both", expand=True, padx=(0, 6))
 
        self.progress = ctk.CTkProgressBar(pc, height=14, progress_color=PURPLE,
                                           fg_color=self.C["sidebar"])
        self.progress.pack(fill="x", padx=20, pady=(14, 6))
        self.progress.set(0)
 
        sf = ctk.CTkFrame(pc, fg_color="transparent")
        sf.pack(fill="x", padx=20, pady=(0, 4))
        self.progress_label = ctk.CTkLabel(sf, text="جاهز للبدء",
                                           text_color=self.C["sub"], font=("Segoe UI", 10))
        self.progress_label.pack(side="left")
        self.spinner_label = ctk.CTkLabel(sf, text="", text_color=PURPLE_LIGHT,
                                          font=("Consolas", 14))
        self.spinner_label.pack(side="left", padx=8)
 
        # ── عداد الوقت ──
        tf = ctk.CTkFrame(pc, fg_color="transparent")
        tf.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(tf, text="⏱", font=("Segoe UI", 12), text_color=INFO).pack(side="left")
        self.timer_label = ctk.CTkLabel(tf, text="00:00", font=("Consolas", 11, "bold"),
                                         text_color=INFO)
        self.timer_label.pack(side="left", padx=4)
        self.pages_label = ctk.CTkLabel(tf, text="| الصفحات: 0",
                                         font=("Segoe UI", 10), text_color=self.C["sub"])
        self.pages_label.pack(side="left", padx=8)
 
        stats = ctk.CTkFrame(pc, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=(0, 10))
        self.stat_vouchers = ctk.CTkLabel(stats, text="السندات: 0",
                                          text_color=SUCCESS, font=("Segoe UI", 10, "bold"))
        self.stat_vouchers.pack(side="left", padx=10)
        self.stat_attachments = ctk.CTkLabel(stats, text="المرفقات: 0",
                                             text_color=PURPLE_LIGHT, font=("Segoe UI", 10, "bold"))
        self.stat_attachments.pack(side="left", padx=10)
        self.stat_unknown = ctk.CTkLabel(stats, text="المجاهيل: 0",
                                         text_color=DANGER, font=("Segoe UI", 10, "bold"))
        self.stat_unknown.pack(side="left", padx=10)
        self.stat_skipped = ctk.CTkLabel(stats, text="المكررة: 0",
                                          text_color=WARNING, font=("Segoe UI", 10, "bold"))
        self.stat_skipped.pack(side="left", padx=10)
 
        pv = ctk.CTkFrame(mid, fg_color=self.C["card"], corner_radius=15, width=200)
        pv.pack(side="left", fill="y")
        pv.pack_propagate(False)
        ctk.CTkLabel(pv, text="معاينة الصفحة", font=("Segoe UI", 10, "bold"),
                     text_color=self.C["sub"]).pack(pady=(10, 4))
        self.preview_label = ctk.CTkLabel(pv, text="", image=None)
        self.preview_label.pack(expand=True)
        self.preview_info = ctk.CTkLabel(pv, text="—",
                                          font=("Segoe UI", 9), text_color=self.C["sub"])
        self.preview_info.pack(pady=(4, 10))
 
        self.log = ctk.CTkTextbox(self.home_frame, fg_color=self.C["log"],
                                  text_color=self.C["text"], font=("Consolas", 10),
                                  corner_radius=15)
        self.log.pack(fill="both", expand=True, padx=30, pady=(5, 8))
        self.log.configure(state="disabled")
 
        btn_row = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=30, pady=(0, 18))
 
        self.run_btn = ctk.CTkButton(btn_row, text="▶  بدء المعالجة",
                                     height=46, font=("Segoe UI", 13, "bold"),
                                     fg_color=PURPLE, hover_color=PURPLE_LIGHT,
                                     command=self._start)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
 
        self.stop_btn = ctk.CTkButton(btn_row, text="⏹ إيقاف", width=120, height=46,
                                      font=("Segoe UI", 12, "bold"),
                                      fg_color=DANGER, hover_color="#dc2626",
                                      state="disabled", command=self._stop)
        self.stop_btn.pack(side="left")
 
    def _show_home(self):
        for f in [self.about_frame, self.memory_frame]:
            f.pack_forget()
        self.home_frame.pack(fill="both", expand=True)
        self._nav_color("الرئيسية")
 
    def _file_row(self, parent, label, var, cmd):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(f, text=label, width=115, text_color=self.C["sub"],
                     font=("Segoe UI", 11), anchor="e").pack(side="left")
        ctk.CTkEntry(f, textvariable=var, fg_color=self.C["sidebar"],
                     border_color=PURPLE, text_color=self.C["text"],
                     height=36).pack(side="left", fill="x", expand=True, padx=10)
        ctk.CTkButton(f, text="اختيار", width=80, height=36,
                      fg_color=PURPLE, hover_color=PURPLE_LIGHT, command=cmd).pack(side="left")
 
    # ==================== صفحة الذاكرة ====================
 
    def _build_memory(self):
        self.memory_frame = ctk.CTkFrame(self.content, fg_color=self.C["bg"], corner_radius=0)
 
        hdr = ctk.CTkFrame(self.memory_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(22, 8))
        ctk.CTkLabel(hdr, text="ذاكرة السندات المعالجة",
                     font=("Segoe UI", 22, "bold"), text_color=self.C["text"]).pack(side="left")
 
        # إحصاء
        self.mem_count_lbl = ctk.CTkLabel(hdr, text=f"إجمالي: {len(self.memory)} سند",
                                           font=("Segoe UI", 11), text_color=INFO)
        self.mem_count_lbl.pack(side="left", padx=16)
 
        # بحث + مسح
        bf = ctk.CTkFrame(self.memory_frame, fg_color="transparent")
        bf.pack(fill="x", padx=30, pady=(0, 8))
        self.mem_search_var = ctk.StringVar()
        self.mem_search_var.trace("w", lambda *a: self._refresh_memory_list())
        ctk.CTkEntry(bf, textvariable=self.mem_search_var, placeholder_text="بحث برقم السند...",
                     fg_color=self.C["card"], border_color=PURPLE, text_color=self.C["text"],
                     height=36).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(bf, text="مسح الذاكرة", width=130, height=36,
                      fg_color=DANGER, hover_color="#dc2626",
                      command=self._clear_memory).pack(side="left")
 
        self.mem_list = ctk.CTkScrollableFrame(self.memory_frame, fg_color=self.C["card"],
                                                corner_radius=15)
        self.mem_list.pack(fill="both", expand=True, padx=30, pady=(0, 20))
 
        self._refresh_memory_list()
 
    def _refresh_memory_list(self):
        for w in self.mem_list.winfo_children():
            w.destroy()
 
        query = self.mem_search_var.get().strip() if hasattr(self, 'mem_search_var') else ""
        items = [(k, v) for k, v in self.memory.items()
                 if not query or query in k]
 
        if not items:
            ctk.CTkLabel(self.mem_list,
                         text="لا توجد سندات في الذاكرة" if not query else "لم يُعثر على نتائج",
                         text_color=self.C["sub"], font=("Segoe UI", 12)).pack(pady=30)
            return
 
        for vno, info in items:
            row = ctk.CTkFrame(self.mem_list, fg_color=self.C["sidebar"], corner_radius=10)
            row.pack(fill="x", pady=3, padx=5)
            ctk.CTkLabel(row, text=vno, font=("Consolas", 11, "bold"),
                         text_color=SUCCESS, width=120).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(row, text=info.get("folder", ""),
                         font=("Segoe UI", 10), text_color=self.C["text"]).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=info.get("archived", ""),
                         font=("Segoe UI", 9), text_color=self.C["sub"]).pack(side="right", padx=10)
 
    def _clear_memory(self):
        if messagebox.askyesno("تأكيد", "هل تريد مسح ذاكرة السندات كاملاً؟\nسيُعاد معالجة كل السندات في المرة القادمة."):
            self.memory = {}
            save_memory(self.memory)
            self._refresh_memory_list()
            self.mem_count_lbl.configure(text="إجمالي: 0 سند")
 
    def _show_memory(self):
        for f in [self.home_frame, self.about_frame]:
            f.pack_forget()
        self._refresh_memory_list()
        self.mem_count_lbl.configure(text=f"إجمالي: {len(self.memory)} سند")
        self.memory_frame.pack(fill="both", expand=True)
        self._nav_color("الذاكرة")
 
    # ==================== صفحة عن البرنامج ====================
 
    def _build_about(self):
        self.about_frame = ctk.CTkFrame(self.content, fg_color=self.C["bg"], corner_radius=0)
 
        ctk.CTkLabel(self.about_frame, text="عن البرنامج",
                     font=("Segoe UI", 22, "bold"), text_color=self.C["text"]).pack(pady=(30, 15))
 
        card = ctk.CTkFrame(self.about_frame, fg_color=self.C["card"], corner_radius=20)
        card.pack(padx=60, pady=5, fill="x")
 
        if os.path.exists(LOGO_FILE):
            from PIL import Image as PI
            limg = ctk.CTkImage(PI.open(LOGO_FILE).resize((90, 90)), size=(90, 90))
            ctk.CTkLabel(card, image=limg, text="").pack(pady=(20, 6))
 
        ctk.CTkLabel(card, text="ارشيف المقداد",
                     font=("Segoe UI", 20, "bold"), text_color=PURPLE_GLOW).pack()
        ctk.CTkLabel(card, text=f"الإصدار {CURRENT_VERSION}", font=("Segoe UI", 11),
                     text_color=self.C["sub"]).pack(pady=3)
 
        ctk.CTkFrame(card, height=1, fg_color=PURPLE).pack(fill="x", padx=30, pady=10)
 
        for t in ["نظام ذكي لفصل السندات المحاسبية تلقائياً",
                  "يعتمد على تقنية EasyOCR للذكاء الاصطناعي",
                  "أرشفة • تنظيم • حماية • وصول سريع"]:
            ctk.CTkLabel(card, text=t, text_color=self.C["sub"],
                         font=("Segoe UI", 11)).pack(pady=2)
 
        ctk.CTkFrame(card, height=1, fg_color=PURPLE).pack(fill="x", padx=30, pady=10)
 
        ctk.CTkLabel(card, text="تطوير وبرمجة",
                     font=("Segoe UI", 11, "bold"), text_color=PURPLE_LIGHT).pack()
        ctk.CTkLabel(card, text="المقداد حسن",
                     font=("Segoe UI", 14, "bold"), text_color=self.C["text"]).pack(pady=2)
        ctk.CTkLabel(card, text="meqdadnagham375@gmail.com",
                     font=("Segoe UI", 10), text_color=self.C["sub"]).pack(pady=2)
 
        ctk.CTkFrame(card, height=1, fg_color=self.C["sidebar"]).pack(fill="x", padx=30, pady=8)
 
        ctk.CTkLabel(card, text="مساعد البرمجة",
                     font=("Segoe UI", 11, "bold"), text_color=PURPLE_LIGHT).pack()
        ctk.CTkLabel(card, text="Claude - Anthropic",
                     font=("Segoe UI", 12), text_color=self.C["text"]).pack(pady=2)
 
        ctk.CTkLabel(card, text="جميع الحقوق محفوظة © 2026",
                     font=("Segoe UI", 10), text_color=self.C["sub"]).pack(pady=(10, 22))
 
    def _show_about(self):
        for f in [self.home_frame, self.memory_frame]:
            f.pack_forget()
        self.about_frame.pack(fill="both", expand=True)
        self._nav_color("عن البرنامج")
 
    # ==================== تبديل الوضع ====================
 
    def _toggle_mode(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        self.settings["appearance"] = self.mode
        save_settings(self.settings)
        ctk.set_appearance_mode(self.mode)
        self.C = colors(self.mode)
        self.mode_btn.configure(
            text="☀️ وضع فاتح" if self.mode == "dark" else "🌙 وضع داكن"
        )
        self.configure(fg_color=self.C["bg"])
        self.sidebar.configure(fg_color=self.C["sidebar"])
        self.content.configure(fg_color=self.C["bg"])
        for frame in [self.home_frame, self.memory_frame, self.about_frame]:
            frame.configure(fg_color=self.C["bg"])
 
        for btn in self._nav_btns.values():
            btn.configure(text_color=self.C["text"], fg_color="transparent")
        self._nav_color(self._active_page())
 
        self.log.configure(fg_color=self.C["log"], text_color=self.C["text"])
        self.progress_label.configure(text_color=self.C["sub"])
        self.preview_info.configure(text_color=self.C["sub"])
        self.pages_label.configure(text_color=self.C["sub"])
        self.stat_vouchers.configure(text_color=SUCCESS)
        self.stat_attachments.configure(text_color=PURPLE_LIGHT)
        self.stat_unknown.configure(text_color=DANGER)
        self.stat_skipped.configure(text_color=WARNING)
        self.spinner_label.configure(text_color=PURPLE_LIGHT)
        self.timer_label.configure(text_color=INFO)
 
    def _active_page(self):
        if self.home_frame.winfo_ismapped():   return "الرئيسية"
        if self.memory_frame.winfo_ismapped(): return "الذاكرة"
        return "عن البرنامج"
 
    # ==================== عداد الوقت ====================
 
    def _start_timer(self):
        self._timer_run = True
        self._start_time = time.time()
        self._tick_timer()
 
    def _tick_timer(self):
        if not self._timer_run: return
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        try:
            self.timer_label.configure(text=f"{m:02d}:{s:02d}")
            self.after(1000, self._tick_timer)
        except: pass
 
    def _stop_timer(self):
        self._timer_run = False
 
    # ==================== المؤشر الحي ====================
 
    def _start_spinner(self):
        self._spin_run = True
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        def spin():
            if self._spin_run:
                try:
                    self.spinner_label.configure(text=frames[self._spin_idx % len(frames)])
                    self._spin_idx += 1
                    self.after(120, spin)
                except: pass
        self._spin_idx = 0
        spin()
 
    def _stop_spinner(self):
        self._spin_run = False
        try: self.spinner_label.configure(text="✓")
        except: pass
 
    # ==================== المعاينة ====================
 
    def _update_preview(self, page, page_num: int, total: int, label: str = ""):
        try:
            pix  = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
            img  = Image.open(io.BytesIO(pix.tobytes()))
            img.thumbnail((180, 200))
            ctk_img = ctk.CTkImage(img, size=img.size)
            self.preview_label.configure(image=ctk_img, text="")
            self.preview_label._image = ctk_img
            info = f"ص {page_num}/{total}"
            if label: info += f"\n{label}"
            self.preview_info.configure(text=info)
        except Exception:
            pass
 
    def _clear_preview(self):
        self.preview_label.configure(image=None, text="")
        self.preview_info.configure(text="—")
 
    # ==================== العمليات ====================
 
    def _choose_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if p:
            self.pdf_path.set(p)
            self.settings["last_pdf"] = p
            save_settings(self.settings)
 
    def _choose_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.archive_path.set(p)
            self.settings["last_archive"] = p
            save_settings(self.settings)
 
    def _log(self, msg):
        try:
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        except: pass
 
    def _stop(self):
        self.stop_flag = True
        self.progress_label.configure(text="جاري الإيقاف...")
 
    def _start(self):
        if not self.pdf_path.get():
            messagebox.showerror("خطأ", "يرجى اختيار ملف PDF أولاً!"); return
        if not self.archive_path.get():
            messagebox.showerror("خطأ", "يرجى اختيار مجلد الأرشيف أولاً!"); return
 
        self.stop_flag = False
        self.run_btn.configure(state="disabled", fg_color=self.C["card"])
        self.stop_btn.configure(state="normal")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress.set(0)
        self.timer_label.configure(text="00:00")
        self.pages_label.configure(text="| الصفحات: 0")
        self.stat_vouchers.configure(text="السندات: 0")
        self.stat_attachments.configure(text="المرفقات: 0")
        self.stat_unknown.configure(text="المجاهيل: 0")
        self.stat_skipped.configure(text="المكررة: 0")
        self._clear_preview()
        self._start_spinner()
        self._start_timer()
 
        threading.Thread(target=self._process, daemon=True).start()
 
    def _process(self):
        s            = self.settings
        pdf_file     = self.pdf_path.get()
        archive_root = self.archive_path.get()
 
        if self.reader is None:
            self._log("جاري تحميل نموذج EasyOCR...")
            self.progress_label.configure(text="تحميل النموذج...")
            self.reader = easyocr.Reader(s["languages"])
            self._log("تم تحميل النموذج!")
        else:
            self._log("نموذج EasyOCR جاهز!")
 
        doc   = fitz.open(pdf_file)
        total = len(doc)
        self._log(f"عدد الصفحات: {total}")
 
        cur_pdf    = None
        cur_no     = ""
        cur_folder = ""
        n_vouchers = 0
        n_attach   = 0
        n_unknown  = 0
        n_skipped  = 0
        n_memory   = 0
        unk_pages  = []
 
        try:
            for i in range(total):
                if self.stop_flag:
                    self._log("تم الإيقاف من قبل المستخدم.")
                    break
 
                self.progress.set((i + 1) / total)
                self.progress_label.configure(text=f"صفحة {i+1} من {total}")
                self.pages_label.configure(text=f"| الصفحات: {i+1}")
 
                page = doc.load_page(i)
                self.after(0, lambda p=page, pi=i+1, t=total: self._update_preview(p, pi, t))
 
                # ── قراءة أولى (30%) ──
                text = read_page_text(page, self.reader, s, wide=False)
 
                # ── تحديد نوع السند ──
                is_main, folder = detect_voucher(text, s)
 
                # ── لو ما لقى — قراءة ثانية موسعة (55%) ──
                if not is_main and len(page.get_text("text").strip()) < 50:
                    text2 = read_page_text(page, self.reader, s, wide=True)
                    is_main, folder = detect_voucher(text2, s)
                    if is_main:
                        text = text2
                        self._log(f"  [↕] قراءة موسعة نجحت | ص{i+1}")
 
                if len(text.strip()) < 20 and cur_pdf is None:
                    continue
 
                if is_main:
                    m   = re.search(r'(00\d{7})', text)
                    vno = m.group(1) if m else None
 
                    if vno and vno == cur_no:
                        cur_pdf.insert_pdf(doc, from_page=i, to_page=i)
                        self._log(f"  [=] تابع: {cur_no} | ص{i+1}")
                        continue
 
                    # حفظ السند السابق
                    if cur_pdf:
                        sd = os.path.join(archive_root, cur_folder)
                        os.makedirs(sd, exist_ok=True)
                        out_path = os.path.join(sd, f"{cur_no}.pdf")
 
                        # ✅ تحقق من الذاكرة أولاً
                        if is_processed(self.memory, cur_no):
                            n_memory += 1
                            self._log(f"  [🧠] في الذاكرة — تم تخطي: {cur_no}")
                            cur_pdf.close()
                        elif os.path.exists(out_path):
                            n_skipped += 1
                            self._log(f"  [⚠] ملف موجود — تم تخطي: {cur_no}.pdf")
                            self.stat_skipped.configure(text=f"المكررة: {n_skipped}")
                            cur_pdf.close()
                        else:
                            cur_pdf.save(out_path)
                            cur_pdf.close()
                            mark_processed(self.memory, cur_no, cur_folder, archive_root)
 
                    # السند الجديد
                    if not folder:
                        folder = "سندات منوعة"
 
                    if vno:
                        cur_no = vno
                    else:
                        cur_no = f"رقم_مجهول_ص{i+1}"
                        n_unknown += 1
                        unk_pages.append(i + 1)
                        folder = "مجهول"
 
                    cur_folder = folder
                    n_vouchers += 1
                    cur_pdf = fitz.open()
                    cur_pdf.insert_pdf(doc, from_page=i, to_page=i)
 
                    lbl = f"{folder} | {cur_no}"
                    self._log(f"[OK] {lbl} | ص{i+1}")
                    self.stat_vouchers.configure(text=f"السندات: {n_vouchers}")
                    self.stat_unknown.configure(text=f"المجاهيل: {n_unknown}")
                    self.after(0, lambda p=page, pi=i+1, t=total, lb=lbl:
                               self._update_preview(p, pi, t, lb))
 
                else:
                    if cur_pdf:
                        cur_pdf.insert_pdf(doc, from_page=i, to_page=i)
                        n_attach += 1
                        self._log(f"  [+] مرفق | ص{i+1}")
                        self.stat_attachments.configure(text=f"المرفقات: {n_attach}")
 
        finally:
            if cur_pdf:
                sd = os.path.join(archive_root, cur_folder)
                os.makedirs(sd, exist_ok=True)
                out_path = os.path.join(sd, f"{cur_no}.pdf")
                if is_processed(self.memory, cur_no):
                    n_memory += 1
                    self._log(f"  [🧠] في الذاكرة — تم تخطي: {cur_no}")
                    cur_pdf.close()
                elif os.path.exists(out_path):
                    n_skipped += 1
                    self._log(f"  [⚠] ملف موجود — تم تخطي: {cur_no}.pdf")
                    cur_pdf.close()
                else:
                    cur_pdf.save(out_path)
                    cur_pdf.close()
                    mark_processed(self.memory, cur_no, cur_folder, archive_root)
 
            doc.close()
            save_memory(self.memory)
 
        self._stop_spinner()
        self._stop_timer()
        self._clear_preview()
 
        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        m, s_e = divmod(elapsed, 60)
        duration_str = f"{m} دقيقة و{s_e} ثانية"
 
        self._log("\n" + "="*48)
        self._log("التقرير النهائي:")
        self._log(f"  الصفحات   : {total}")
        self._log(f"  السندات   : {n_vouchers}")
        self._log(f"  المرفقات  : {n_attach}")
        self._log(f"  المجاهيل  : {n_unknown}")
        self._log(f"  المكررة   : {n_skipped}")
        self._log(f"  الذاكرة   : {n_memory}")
        self._log(f"  المدة     : {duration_str}")
        if unk_pages: self._log(f"  صفحات مجهولة: {unk_pages}")
        self._log(f"  الحفظ في  : {archive_root}")
        self._log("="*48)
 
        self.progress.set(1)
        self.progress_label.configure(text="اكتملت العملية!")
        self.run_btn.configure(state="normal", fg_color=PURPLE)
        self.stop_btn.configure(state="disabled")
        if not self.stop_flag:
            messagebox.showinfo("تم!",
                f"السندات: {n_vouchers} | المرفقات: {n_attach}\n"
                f"المكررة: {n_skipped} | الذاكرة: {n_memory}\n"
                f"المدة: {duration_str}")
 
    # ==================== الإعدادات ====================
 
    def _open_settings(self):
        self._nav_color("الإعدادات")
        SettingsWindow(self, self.settings, self._on_saved)
 
    def _on_saved(self, ns):
        self.settings = ns
        self.reader   = None
        self._reader_ready = False
        self._log("تم تحديث الإعدادات!")
 
 
if __name__ == "__main__":
    app = VoucherApp()
    app.mainloop()
