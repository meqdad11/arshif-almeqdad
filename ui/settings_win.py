"""
ui/settings_win.py
نافذة الإعدادات
"""

import customtkinter as ctk
from tkinter import messagebox
from config import (DEFAULT_SETTINGS, save_settings,
                    PURPLE, PURPLE_LIGHT, PURPLE_GLOW, DANGER, colors)
from ui.updater import check_for_updates


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings: dict, on_save):
        super().__init__(parent)
        self.settings    = settings
        self.on_save     = on_save
        self.type_rows   = []
        self.cond_rows   = []
        self.marker_rows = []
        C = colors(settings.get("appearance", "dark"))

        self.title("الإعدادات")
        self.geometry("600x760")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()

        ctk.CTkLabel(self, text="الإعدادات",
                     font=("Segoe UI", 18, "bold"),
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
            "header_ratio":        round(self.ratio_var.get() / 100, 2),
            "header_ratio_wide":   round(self.ratio_wide_var.get() / 100, 2),
            "languages":           langs,
            "id_conditions":       conds,
            "tax_expense_markers": markers,
            "voucher_types":       nt,
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
