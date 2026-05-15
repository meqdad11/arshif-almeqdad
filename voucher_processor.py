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
import urllib.request
import subprocess
import tempfile
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ==================== الإعدادات ====================

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
LOGO_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_final.png")
ICON_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

CURRENT_VERSION = "1.1"

VERSION_URL  = "https://raw.githubusercontent.com/meqdad11/arshif-almeqdad/main/version.json"
DOWNLOAD_URL = "https://github.com/meqdad11/arshif-almeqdad/releases/latest/download/voucher_processor.exe"

DEFAULT_SETTINGS = {
    "cr_number":    "4030100012",
    "tax_number":   "311250175400003",
    "header_ratio": 0.35,
    "languages":    ["ar", "en"],
    "appearance":   "dark",
    "voucher_types": {
        "صرف":   {"key": "سندات_صرف",      "folder": "سندات صرف"},
        "قبض":   {"key": "سندات_قبض",      "folder": "سندات قبض"},
        "يومية": {"key": "قيد_يومية",       "folder": "قبود يومية"},
        "رواتب": {"key": "استحقاق_رواتب",   "folder": "قبود استحقاق رواتب"},
        "ضريب":  {"key": "مصروفات_ضريبية",  "folder": "مصروفات ضريبية"},
    },
    "last_pdf":     "",
    "last_archive": ""
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        data = json.load(open(SETTINGS_FILE, "r", encoding="utf-8"))
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
        return data
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

def colors(mode):
    if mode == "dark":
        return {"bg": "#0d0b1a", "card": "#1a1530", "sidebar": "#120f22",
                "text": "#e2d9f3", "sub": "#9d8ec0", "log": "#0a0815"}
    return {"bg": "#f0eeff", "card": "#ffffff", "sidebar": "#ddd5ff",
            "text": "#1a0a3d", "sub": "#6b5b9e", "log": "#e8e0ff"}


# ==================== Splash Screen ====================

class SplashScreen(ctk.CTkToplevel):
    """نافذة التحميل عند فتح البرنامج"""

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)          # بدون شريط عنوان
        self.attributes("-topmost", True)
        self.configure(fg_color="#0d0b1a")

        w, h = 420, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # --- المحتوى ---
        ctk.CTkLabel(self, text="ارشيف المقداد",
                     font=("Segoe UI", 26, "bold"),
                     text_color=PURPLE_GLOW).pack(pady=(45, 4))

        ctk.CTkLabel(self, text=f"الإصدار {CURRENT_VERSION}",
                     font=("Segoe UI", 11), text_color="#9d8ec0").pack()

        ctk.CTkFrame(self, height=1, fg_color=PURPLE, width=300).pack(pady=16)

        self.status_lbl = ctk.CTkLabel(self, text="جاري التحميل...",
                                        font=("Segoe UI", 12),
                                        text_color="#9d8ec0")
        self.status_lbl.pack()

        self.bar = ctk.CTkProgressBar(self, width=300, height=10,
                                       progress_color=PURPLE,
                                       fg_color="#1a1530")
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
    """نافذة التحديث التلقائي"""

    def __init__(self, parent, new_version: str):
        super().__init__(parent)
        self.parent = parent
        self.new_version = new_version
        self.title("تحديث متاح")
        self.geometry("420x260")
        self.resizable(False, False)
        self.configure(fg_color="#0d0b1a")
        self.grab_set()

        ctk.CTkLabel(self, text="🎉 تحديث جديد متاح!",
                     font=("Segoe UI", 18, "bold"),
                     text_color=PURPLE_GLOW).pack(pady=(28, 8))

        ctk.CTkLabel(self,
                     text=f"الإصدار الحالي: {CURRENT_VERSION}   ←   الإصدار الجديد: {new_version}",
                     font=("Segoe UI", 11), text_color="#9d8ec0").pack()

        self.progress = ctk.CTkProgressBar(self, width=340, height=12,
                                            progress_color=PURPLE,
                                            fg_color="#1a1530")
        self.progress.pack(pady=18)
        self.progress.set(0)

        self.status = ctk.CTkLabel(self, text="",
                                    font=("Segoe UI", 10), text_color="#9d8ec0")
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

            # تحميل الملف الجديد في مجلد مؤقت
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

            # سكريبت bat يستبدل الـ exe القديم بالجديد بعد إغلاق البرنامج
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
    """تحقق من التحديثات — silent=True لا يظهر رسالة لو ما في تحديث"""
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
        self.settings = settings
        self.on_save  = on_save
        self.type_rows = []
        C = colors(settings.get("appearance", "dark"))

        self.title("الإعدادات")
        self.geometry("540x590")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()

        ctk.CTkLabel(self, text="الإعدادات", font=("Segoe UI", 18, "bold"),
                     text_color=PURPLE_GLOW).pack(pady=(20, 15))

        card = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=15)
        card.pack(padx=20, fill="x")

        def lbl(r, t):
            ctk.CTkLabel(card, text=f"{t}:", text_color=C["sub"],
                         font=("Segoe UI", 10)).grid(row=r, column=0, sticky="e", padx=15, pady=8)

        lbl(0, "السجل التجاري")
        self.cr_var = ctk.StringVar(value=settings["cr_number"])
        ctk.CTkEntry(card, textvariable=self.cr_var, width=260,
                     fg_color=C["sidebar"], border_color=PURPLE,
                     text_color=C["text"]).grid(row=0, column=1, padx=10, pady=8)

        lbl(1, "الرقم الضريبي")
        self.tax_var = ctk.StringVar(value=settings["tax_number"])
        ctk.CTkEntry(card, textvariable=self.tax_var, width=260,
                     fg_color=C["sidebar"], border_color=PURPLE,
                     text_color=C["text"]).grid(row=1, column=1, padx=10, pady=8)

        lbl(2, "نسبة الترويسة")
        sf = ctk.CTkFrame(card, fg_color="transparent")
        sf.grid(row=2, column=1, sticky="w", padx=10)
        self.ratio_var = ctk.DoubleVar(value=settings["header_ratio"] * 100)
        rl = ctk.CTkLabel(sf, text=f"{int(self.ratio_var.get())}%",
                          text_color=PURPLE_LIGHT, width=40)
        rl.pack(side="left")
        ctk.CTkSlider(sf, from_=20, to=50, variable=self.ratio_var, width=200,
                      button_color=PURPLE, progress_color=PURPLE_LIGHT,
                      command=lambda v: rl.configure(text=f"{int(v)}%")).pack(side="left")

        lbl(3, "لغة القراءة")
        lf = ctk.CTkFrame(card, fg_color="transparent")
        lf.grid(row=3, column=1, sticky="w", padx=10)
        self.lang_ar = ctk.BooleanVar(value="ar" in settings["languages"])
        self.lang_en = ctk.BooleanVar(value="en" in settings["languages"])
        ctk.CTkCheckBox(lf, text="عربي", variable=self.lang_ar,
                        fg_color=PURPLE, text_color=C["text"]).pack(side="left", padx=8)
        ctk.CTkCheckBox(lf, text="انجليزي", variable=self.lang_en,
                        fg_color=PURPLE, text_color=C["text"]).pack(side="left", padx=8)

        th = ctk.CTkFrame(self, fg_color="transparent")
        th.pack(padx=20, pady=(12, 4), fill="x")
        ctk.CTkLabel(th, text="أنواع السندات:", text_color=C["sub"]).pack(side="left")
        ctk.CTkButton(th, text="+ إضافة", width=90, fg_color=PURPLE,
                      hover_color=PURPLE_LIGHT, command=self._add_row).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C["card"],
                                              height=130, corner_radius=10)
        self.scroll.pack(padx=20, fill="x")

        for kw, info in settings["voucher_types"].items():
            self._add_row(kw, info["folder"])

        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(pady=14)
        ctk.CTkButton(bf, text="حفظ", width=140, fg_color=PURPLE,
                      hover_color=PURPLE_LIGHT, command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(bf, text="افتراضي", width=140, fg_color="#3b1f6e",
                      hover_color=DANGER, command=self._reset).pack(side="left", padx=8)
        ctk.CTkButton(bf, text="تحقق من التحديثات", width=170, fg_color="#1e1040",
                      hover_color=PURPLE,
                      command=lambda: check_for_updates(self.master, silent=False)
                      ).pack(side="left", padx=8)

    def _add_row(self, kw="", folder=""):
        C = colors(self.settings.get("appearance", "dark"))
        row = ctk.CTkFrame(self.scroll, fg_color=C["sidebar"], corner_radius=8)
        row.pack(fill="x", pady=3, padx=5)
        kv = ctk.StringVar(value=kw)
        fv = ctk.StringVar(value=folder)
        ctk.CTkEntry(row, textvariable=kv, width=100, fg_color=C["bg"],
                     border_color=PURPLE, text_color=C["text"],
                     placeholder_text="الكلمة").pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(row, text="|", text_color=C["sub"]).pack(side="left")
        ctk.CTkEntry(row, textvariable=fv, width=195, fg_color=C["bg"],
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
        nt = {kv.get().strip(): {"key": "_".join(fv.get().split()), "folder": fv.get().strip()}
              for kv, fv in self.type_rows if kv.get().strip() and fv.get().strip()}
        if not nt:
            messagebox.showerror("خطأ", "أضف نوع سند واحد على الأقل!"); return
        self.settings.update({
            "cr_number": self.cr_var.get().strip(),
            "tax_number": self.tax_var.get().strip(),
            "header_ratio": round(self.ratio_var.get() / 100, 2),
            "languages": langs, "voucher_types": nt
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
        self.withdraw()   # إخفاء النافذة الرئيسية حتى تنتهي الـ Splash

        self.settings   = load_settings()
        self.mode       = self.settings.get("appearance", "dark")
        self.C          = colors(self.mode)
        self.reader     = None
        self.stop_flag  = False
        self._spin_run  = False
        self._spin_idx  = 0

        ctk.set_appearance_mode(self.mode)
        self.title("ارشيف المقداد")
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.configure(fg_color=self.C["bg"])
        if os.path.exists(ICON_FILE):
            self.iconbitmap(ICON_FILE)

        self.pdf_path     = ctk.StringVar(value=self.settings.get("last_pdf", ""))
        self.archive_path = ctk.StringVar(value=self.settings.get("last_archive", ""))

        # --- عرض Splash ثم بناء الواجهة ---
        self._show_splash()

    # ==================== Splash ====================

    def _show_splash(self):
        splash = SplashScreen(self)
        splash.set_status("تحميل الإعدادات...", 0.2)
        self.after(400, lambda: self._splash_step2(splash))

    def _splash_step2(self, splash):
        splash.set_status("بناء الواجهة...", 0.55)
        self._build()
        self.after(400, lambda: self._splash_step3(splash))

    def _splash_step3(self, splash):
        splash.set_status("جاهز!", 1.0)
        self.after(500, lambda: self._splash_done(splash))

    def _splash_done(self, splash):
        splash.close()
        self.deiconify()
        self.lift()
        # فحص تحديثات في الخلفية بعد الفتح بثانيتين
        self.after(2000, lambda: check_for_updates(self, silent=True))

    # ==================== بناء الواجهة ====================

    def _build(self):
        # --- الشريط الجانبي ---
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
                           ("الإعدادات", self._open_settings),
                           ("عن البرنامج", self._show_about)]:
            btn = ctk.CTkButton(self.sidebar, text=label, width=190, height=42,
                                fg_color="transparent", hover_color=PURPLE,
                                text_color=self.C["text"], font=("Segoe UI", 12),
                                command=cmd)
            btn.pack(pady=3, padx=15)
            self._nav_btns[label] = btn

        ctk.CTkFrame(self.sidebar, height=1, fg_color=PURPLE).pack(fill="x", padx=15, pady=(12, 4))

        self.mode_btn = ctk.CTkButton(self.sidebar,
                                      text="☀️ وضع فاتح" if self.mode == "dark" else "🌙 وضع داكن",
                                      width=190, height=36,
                                      fg_color=PURPLE, hover_color=PURPLE_LIGHT,
                                      font=("Segoe UI", 11),
                                      command=self._toggle_mode)
        self.mode_btn.pack(pady=6, padx=15)

        # --- منطقة المحتوى ---
        self.content = ctk.CTkFrame(self, fg_color=self.C["bg"], corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

        self._build_home()
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

        # اختيار الملفات
        fc = ctk.CTkFrame(self.home_frame, fg_color=self.C["card"], corner_radius=15)
        fc.pack(fill="x", padx=30, pady=8)
        self._file_row(fc, "ملف PDF:", self.pdf_path, self._choose_pdf)
        self._file_row(fc, "مجلد الأرشيف:", self.archive_path, self._choose_folder)

        # ── المنطقة الوسطى: التقدم + المعاينة ──
        mid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        mid.pack(fill="x", padx=30, pady=5)

        # التقدم (يسار)
        pc = ctk.CTkFrame(mid, fg_color=self.C["card"], corner_radius=15)
        pc.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.progress = ctk.CTkProgressBar(pc, height=14, progress_color=PURPLE,
                                           fg_color=self.C["sidebar"])
        self.progress.pack(fill="x", padx=20, pady=(14, 6))
        self.progress.set(0)

        sf = ctk.CTkFrame(pc, fg_color="transparent")
        sf.pack(fill="x", padx=20, pady=(0, 6))
        self.progress_label = ctk.CTkLabel(sf, text="جاهز للبدء",
                                           text_color=self.C["sub"], font=("Segoe UI", 10))
        self.progress_label.pack(side="left")
        self.spinner_label = ctk.CTkLabel(sf, text="", text_color=PURPLE_LIGHT,
                                          font=("Consolas", 14))
        self.spinner_label.pack(side="left", padx=8)

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

        # المعاينة (يمين)
        pv = ctk.CTkFrame(mid, fg_color=self.C["card"], corner_radius=15, width=200)
        pv.pack(side="left", fill="y", padx=(0, 0))
        pv.pack_propagate(False)

        ctk.CTkLabel(pv, text="معاينة الصفحة", font=("Segoe UI", 10, "bold"),
                     text_color=self.C["sub"]).pack(pady=(10, 4))

        self.preview_label = ctk.CTkLabel(pv, text="", image=None)
        self.preview_label.pack(expand=True)

        self.preview_info = ctk.CTkLabel(pv, text="—",
                                          font=("Segoe UI", 9), text_color=self.C["sub"])
        self.preview_info.pack(pady=(4, 10))

        # السجل
        self.log = ctk.CTkTextbox(self.home_frame, fg_color=self.C["log"],
                                  text_color=self.C["text"], font=("Consolas", 10),
                                  corner_radius=15)
        self.log.pack(fill="both", expand=True, padx=30, pady=(5, 8))
        self.log.configure(state="disabled")

        # أزرار
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
                                      state="disabled",
                                      command=self._stop)
        self.stop_btn.pack(side="left")

    def _show_home(self):
        self.about_frame.pack_forget()
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
        self.home_frame.pack_forget()
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
        self.home_frame.configure(fg_color=self.C["bg"])
        self.about_frame.configure(fg_color=self.C["bg"])
        for btn in self._nav_btns.values():
            btn.configure(text_color=self.C["text"])
        self.log.configure(fg_color=self.C["log"], text_color=self.C["text"])
        self.progress_label.configure(text_color=self.C["sub"])

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
        """تحديث صورة المعاينة من صفحة PDF"""
        try:
            pix  = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
            img  = Image.open(io.BytesIO(pix.tobytes()))
            # قص لأبعاد مناسبة للعرض
            img.thumbnail((180, 200))
            ctk_img = ctk.CTkImage(img, size=img.size)
            self.preview_label.configure(image=ctk_img, text="")
            self.preview_label._image = ctk_img   # منع garbage collection
            info = f"ص {page_num}/{total}"
            if label:
                info += f"\n{label}"
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
        self.stat_vouchers.configure(text="السندات: 0")
        self.stat_attachments.configure(text="المرفقات: 0")
        self.stat_unknown.configure(text="المجاهيل: 0")
        self.stat_skipped.configure(text="المكررة: 0")
        self._clear_preview()
        self._start_spinner()

        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        s            = self.settings
        pdf_file     = self.pdf_path.get()
        archive_root = self.archive_path.get()

        self._log("جاري تحميل نموذج EasyOCR...")
        self.progress_label.configure(text="تحميل النموذج...")
        if self.reader is None:
            self.reader = easyocr.Reader(s["languages"])
        self._log("تم تحميل النموذج!")

        doc         = fitz.open(pdf_file)
        total       = len(doc)
        self._log(f"عدد الصفحات: {total}")

        cur_pdf     = None
        cur_no      = ""
        cur_folder  = ""
        n_vouchers  = 0
        n_attach    = 0
        n_unknown   = 0
        n_skipped   = 0
        unk_pages   = []

        try:
            for i in range(total):
                if self.stop_flag:
                    self._log("تم الإيقاف من قبل المستخدم.")
                    break

                self.progress.set((i + 1) / total)
                self.progress_label.configure(text=f"صفحة {i+1} من {total}")

                page = doc.load_page(i)

                # --- تحديث المعاينة ---
                self.after(0, lambda p=page, pi=i+1, t=total: self._update_preview(p, pi, t))

                text = page.get_text("text")

                if len(text.strip()) < 50:
                    pix  = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img  = Image.open(io.BytesIO(pix.tobytes()))
                    w, h = img.size
                    hdr  = img.crop((0, 0, w, int(h * s["header_ratio"])))
                    text = ' '.join(self.reader.readtext(np.array(hdr), detail=0))
                    del img, pix, hdr

                if len(text.strip()) < 20 and cur_pdf is None:
                    continue

                has_co   = s["cr_number"] in text or s["tax_number"] in text
                has_type = any(w in text for w in s["voucher_types"])
                is_main  = has_co and has_type

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

                        # ✅ كشف التكرار
                        if os.path.exists(out_path):
                            n_skipped += 1
                            self._log(f"  [⚠] مكرر — تم تخطي: {cur_no}.pdf")
                            self.stat_skipped.configure(text=f"المكررة: {n_skipped}")
                            cur_pdf.close()
                        else:
                            cur_pdf.save(out_path)
                            cur_pdf.close()

                    # السند الجديد
                    folder = "سندات منوعة"
                    for kw, info in s["voucher_types"].items():
                        if kw in text:
                            folder = info["folder"]; break

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

                    # تحديث المعاينة مع اسم السند
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
                if os.path.exists(out_path):
                    n_skipped += 1
                    self._log(f"  [⚠] مكرر — تم تخطي: {cur_no}.pdf")
                    self.stat_skipped.configure(text=f"المكررة: {n_skipped}")
                    cur_pdf.close()
                else:
                    cur_pdf.save(out_path)
                    cur_pdf.close()
            doc.close()

        self._stop_spinner()
        self._clear_preview()
        self._log("\n" + "="*48)
        self._log("التقرير النهائي:")
        self._log(f"  الصفحات   : {total}")
        self._log(f"  السندات   : {n_vouchers}")
        self._log(f"  المرفقات  : {n_attach}")
        self._log(f"  المجاهيل  : {n_unknown}")
        self._log(f"  المكررة   : {n_skipped}")
        if unk_pages: self._log(f"  صفحات مجهولة: {unk_pages}")
        self._log(f"  الحفظ في  : {archive_root}")
        self._log("="*48)

        self.progress.set(1)
        self.progress_label.configure(text="اكتملت العملية!")
        self.run_btn.configure(state="normal", fg_color=PURPLE)
        self.stop_btn.configure(state="disabled")
        if not self.stop_flag:
            messagebox.showinfo("تم!", f"السندات: {n_vouchers} | المرفقات: {n_attach} | المكررة: {n_skipped}")

    # ==================== الإعدادات ====================

    def _open_settings(self):
        self._nav_color("الإعدادات")
        SettingsWindow(self, self.settings, self._on_saved)

    def _on_saved(self, ns):
        self.settings = ns
        self.reader   = None
        self._log("تم تحديث الإعدادات!")


if __name__ == "__main__":
    app = VoucherApp()
    app.mainloop()
