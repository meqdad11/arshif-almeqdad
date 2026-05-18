"""
ui/app.py
الواجهة الرئيسية للتطبيق
"""

import os
import io
import time
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
import fitz

from config import (
    CURRENT_VERSION, LOGO_FILE, ICON_FILE,
    PURPLE, PURPLE_LIGHT, PURPLE_GLOW,
    SUCCESS, DANGER, WARNING, INFO,
    colors, load_settings, save_settings,
    load_memory, save_memory
)
from ocr_engine import load_reader
from processor import process_pdf
from ui.splash import SplashScreen
from ui.updater import check_for_updates
from ui.settings_win import SettingsWindow


class VoucherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()

        self.settings      = load_settings()
        self.memory        = load_memory()
        self.mode          = self.settings.get("appearance", "dark")
        self.C             = colors(self.mode)
        self.reader        = None
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
            self.reader = load_reader(self.settings["languages"])
        except Exception:
            self.reader = None
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
        # الشريط الجانبي
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=self.C["sidebar"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        if os.path.exists(LOGO_FILE):
            limg = ctk.CTkImage(Image.open(LOGO_FILE).resize((110, 110)), size=(110, 110))
            ctk.CTkLabel(self.sidebar, image=limg, text="").pack(pady=(22, 4))

        ctk.CTkLabel(self.sidebar, text="ارشيف المقداد",
                     font=("Segoe UI", 15, "bold"), text_color=PURPLE_GLOW).pack()
        ctk.CTkLabel(self.sidebar, text=f"v{CURRENT_VERSION}",
                     font=("Segoe UI", 10), text_color=self.C["sub"]).pack(pady=(2, 12))

        ctk.CTkFrame(self.sidebar, height=1, fg_color=PURPLE).pack(fill="x", padx=15, pady=4)

        self._nav_btns = {}
        for label, cmd in [("الرئيسية", self._show_home),
                           ("الذاكرة",   self._show_memory),
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

    # ==================== الرئيسية ====================

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

        tf = ctk.CTkFrame(pc, fg_color="transparent")
        tf.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(tf, text="⏱", font=("Segoe UI", 12), text_color=INFO).pack(side="left")
        self.timer_label = ctk.CTkLabel(tf, text="00:00",
                                         font=("Consolas", 11, "bold"), text_color=INFO)
        self.timer_label.pack(side="left", padx=4)
        self.pages_label = ctk.CTkLabel(tf, text="| الصفحات: 0",
                                         font=("Segoe UI", 10), text_color=self.C["sub"])
        self.pages_label.pack(side="left", padx=8)

        stats = ctk.CTkFrame(pc, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=(0, 10))
        self.stat_vouchers    = ctk.CTkLabel(stats, text="السندات: 0",    text_color=SUCCESS,      font=("Segoe UI", 10, "bold"))
        self.stat_attachments = ctk.CTkLabel(stats, text="المرفقات: 0",   text_color=PURPLE_LIGHT, font=("Segoe UI", 10, "bold"))
        self.stat_unknown     = ctk.CTkLabel(stats, text="المجاهيل: 0",   text_color=DANGER,       font=("Segoe UI", 10, "bold"))
        self.stat_skipped     = ctk.CTkLabel(stats, text="المكررة: 0",    text_color=WARNING,      font=("Segoe UI", 10, "bold"))
        for s in [self.stat_vouchers, self.stat_attachments, self.stat_unknown, self.stat_skipped]:
            s.pack(side="left", padx=10)

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

    # ==================== الذاكرة ====================

    def _build_memory(self):
        self.memory_frame = ctk.CTkFrame(self.content, fg_color=self.C["bg"], corner_radius=0)

        hdr = ctk.CTkFrame(self.memory_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(22, 8))
        ctk.CTkLabel(hdr, text="ذاكرة السندات المعالجة",
                     font=("Segoe UI", 22, "bold"), text_color=self.C["text"]).pack(side="left")
        self.mem_count_lbl = ctk.CTkLabel(hdr, text=f"إجمالي: {len(self.memory)} سند",
                                           font=("Segoe UI", 11), text_color=INFO)
        self.mem_count_lbl.pack(side="left", padx=16)

        bf = ctk.CTkFrame(self.memory_frame, fg_color="transparent")
        bf.pack(fill="x", padx=30, pady=(0, 8))
        self.mem_search_var = ctk.StringVar()
        self.mem_search_var.trace("w", lambda *a: self._refresh_memory_list())
        ctk.CTkEntry(bf, textvariable=self.mem_search_var,
                     placeholder_text="بحث برقم السند...",
                     fg_color=self.C["card"], border_color=PURPLE,
                     text_color=self.C["text"], height=36
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(bf, text="مسح الذاكرة", width=130, height=36,
                      fg_color=DANGER, hover_color="#dc2626",
                      command=self._clear_memory).pack(side="left")

        self.mem_list = ctk.CTkScrollableFrame(self.memory_frame,
                                                fg_color=self.C["card"], corner_radius=15)
        self.mem_list.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        self._refresh_memory_list()

    def _refresh_memory_list(self):
        for w in self.mem_list.winfo_children():
            w.destroy()
        query = self.mem_search_var.get().strip() if hasattr(self, 'mem_search_var') else ""
        items = [(k, v) for k, v in self.memory.items() if not query or query in k]
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
        if messagebox.askyesno("تأكيد", "هل تريد مسح ذاكرة السندات كاملاً؟"):
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

    # ==================== عن البرنامج ====================

    def _build_about(self):
        self.about_frame = ctk.CTkFrame(self.content, fg_color=self.C["bg"], corner_radius=0)
        ctk.CTkLabel(self.about_frame, text="عن البرنامج",
                     font=("Segoe UI", 22, "bold"), text_color=self.C["text"]).pack(pady=(30, 15))

        card = ctk.CTkFrame(self.about_frame, fg_color=self.C["card"], corner_radius=20)
        card.pack(padx=60, pady=5, fill="x")

        if os.path.exists(LOGO_FILE):
            limg = ctk.CTkImage(Image.open(LOGO_FILE).resize((90, 90)), size=(90, 90))
            ctk.CTkLabel(card, image=limg, text="").pack(pady=(20, 6))

        ctk.CTkLabel(card, text="ارشيف المقداد",
                     font=("Segoe UI", 20, "bold"), text_color=PURPLE_GLOW).pack()
        ctk.CTkLabel(card, text=f"الإصدار {CURRENT_VERSION}",
                     font=("Segoe UI", 11), text_color=self.C["sub"]).pack(pady=3)
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
            text="☀️ وضع فاتح" if self.mode == "dark" else "🌙 وضع داكن")
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
        self.timer_label.configure(text_color=INFO)

    def _active_page(self):
        if self.home_frame.winfo_ismapped():   return "الرئيسية"
        if self.memory_frame.winfo_ismapped(): return "الذاكرة"
        return "عن البرنامج"

    # ==================== عداد الوقت ====================

    def _start_timer(self):
        self._timer_run  = True
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

    # ==================== المؤشر ====================

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

    def _update_preview(self, page, page_num, total, label=""):
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
            img = Image.open(io.BytesIO(pix.tobytes()))
            img.thumbnail((180, 200))
            ctk_img = ctk.CTkImage(img, size=img.size)
            self.preview_label.configure(image=ctk_img, text="")
            self.preview_label._image = ctk_img
            info = f"ص {page_num}/{total}"
            if label: info += f"\n{label}"
            self.preview_info.configure(text=info)
        except: pass

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

        threading.Thread(target=self._run_process, daemon=True).start()

    def _run_process(self):
        if self.reader is None:
            self._log("جاري تحميل نموذج EasyOCR...")
            self.progress_label.configure(text="تحميل النموذج...")
            self.reader = load_reader(self.settings["languages"])
            self._log("تم تحميل النموذج!")
        else:
            self._log("نموذج EasyOCR جاهز!")

        def on_progress(page_num, total):
            self.progress.set(page_num / total)
            self.progress_label.configure(text=f"صفحة {page_num} من {total}")
            self.pages_label.configure(text=f"| الصفحات: {page_num}")

        def on_preview(page, page_num, total, label):
            self.after(0, lambda p=page, pi=page_num, t=total, lb=label:
                       self._update_preview(p, pi, t, lb))

        def on_log(msg):
            self._log(msg)
            # تحديث الإحصائيات من اللوق
            if msg.startswith("[OK]"):
                n = int(self.stat_vouchers.cget("text").split(": ")[1]) + 1
                self.stat_vouchers.configure(text=f"السندات: {n}")
            elif msg.strip().startswith("[+]"):
                n = int(self.stat_attachments.cget("text").split(": ")[1]) + 1
                self.stat_attachments.configure(text=f"المرفقات: {n}")
            elif "[⚠]" in msg:
                n = int(self.stat_skipped.cget("text").split(": ")[1]) + 1
                self.stat_skipped.configure(text=f"المكررة: {n}")
            elif "مجهول" in msg and msg.startswith("[OK]"):
                n = int(self.stat_unknown.cget("text").split(": ")[1]) + 1
                self.stat_unknown.configure(text=f"المجاهيل: {n}")

        results = process_pdf(
            pdf_file     = self.pdf_path.get(),
            archive_root = self.archive_path.get(),
            settings     = self.settings,
            reader       = self.reader,
            memory       = self.memory,
            on_progress  = on_progress,
            on_log       = on_log,
            on_preview   = on_preview,
            stop_flag_fn = lambda: self.stop_flag,
        )

        self._stop_spinner()
        self._stop_timer()
        self._clear_preview()

        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        m, s_e  = divmod(elapsed, 60)
        dur_str = f"{m} دقيقة و{s_e} ثانية"

        self._log("\n" + "="*48)
        self._log("التقرير النهائي:")
        self._log(f"  الصفحات   : {results['total']}")
        self._log(f"  السندات   : {results['vouchers']}")
        self._log(f"  المرفقات  : {results['attachments']}")
        self._log(f"  المجاهيل  : {results['unknown']}")
        self._log(f"  المكررة   : {results['skipped']}")
        self._log(f"  الذاكرة   : {results['memory']}")
        self._log(f"  المدة     : {dur_str}")
        if results['unk_pages']:
            self._log(f"  صفحات مجهولة: {results['unk_pages']}")
        self._log(f"  الحفظ في  : {self.archive_path.get()}")
        self._log("="*48)

        self.progress.set(1)
        self.progress_label.configure(text="اكتملت العملية!")
        self.run_btn.configure(state="normal", fg_color=PURPLE)
        self.stop_btn.configure(state="disabled")

        if not self.stop_flag:
            messagebox.showinfo("تم!",
                f"السندات: {results['vouchers']} | المرفقات: {results['attachments']}\n"
                f"المكررة: {results['skipped']} | الذاكرة: {results['memory']}\n"
                f"المدة: {dur_str}")

    # ==================== الإعدادات ====================

    def _open_settings(self):
        self._nav_color("الإعدادات")
        SettingsWindow(self, self.settings, self._on_saved)

    def _on_saved(self, ns):
        self.settings = ns
        self.reader   = None
        self._log("تم تحديث الإعدادات!")
