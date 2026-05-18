"""
ui/splash.py
شاشة التحميل عند فتح البرنامج
"""

import customtkinter as ctk
from config import CURRENT_VERSION, PURPLE, PURPLE_GLOW


class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#0d0b1a")

        w, h = 420, 280
        sw   = self.winfo_screenwidth()
        sh   = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        ctk.CTkLabel(self, text="ارشيف المقداد",
                     font=("Segoe UI", 26, "bold"),
                     text_color=PURPLE_GLOW).pack(pady=(45, 4))

        ctk.CTkLabel(self, text=f"الإصدار {CURRENT_VERSION}",
                     font=("Segoe UI", 11),
                     text_color="#9d8ec0").pack()

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
                     font=("Segoe UI", 9),
                     text_color="#4a3a6e").pack(pady=(10, 0))
        self.update()

    def set_status(self, text: str, progress: float):
        self.status_lbl.configure(text=text)
        self.bar.set(progress)
        self.update()

    def close(self):
        self.destroy()
