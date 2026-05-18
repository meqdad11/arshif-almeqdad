"""
ui/updater.py
نافذة التحديث التلقائي
"""

import sys
import subprocess
import tempfile
import threading
import urllib.request
import customtkinter as ctk
from tkinter import messagebox
from config import CURRENT_VERSION, DOWNLOAD_URL, PURPLE, PURPLE_LIGHT, PURPLE_GLOW, DANGER


class UpdaterWindow(ctk.CTkToplevel):
    def __init__(self, parent, new_version: str):
        super().__init__(parent)
        self.parent      = parent
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
                     font=("Segoe UI", 11),
                     text_color="#9d8ec0").pack()

        self.progress = ctk.CTkProgressBar(self, width=340, height=12,
                                            progress_color=PURPLE, fg_color="#1a1530")
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

            bat = f'@echo off\ntimeout /t 2 /nobreak >nul\nmove /y "{tmp}" "{exe_path}"\nstart "" "{exe_path}"\ndel "%~f0"\n'
            bat_path = tempfile.mktemp(suffix=".bat")
            with open(bat_path, "w") as f:
                f.write(bat)

            subprocess.Popen(bat_path, shell=True,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

            messagebox.showinfo("تم!", "سيتم إغلاق البرنامج وتثبيت التحديث تلقائياً.")
            self.parent.destroy()

        except Exception as e:
            self.status.configure(text=f"فشل التحديث: {e}")


def check_for_updates(parent, silent=True):
    """تحقق من التحديثات في الخلفية"""
    import json
    from config import VERSION_URL

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
