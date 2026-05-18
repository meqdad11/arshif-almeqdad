"""
main.py
نقطة البداية — هذا الملف فقط هو اللي يشغّله PyInstaller
"""

from ui.app import VoucherApp

if __name__ == "__main__":
    app = VoucherApp()
    app.mainloop()
