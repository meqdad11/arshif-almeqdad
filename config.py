import os
import json
import time

# ==================== المسارات ====================

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
MEMORY_FILE   = os.path.join(BASE_DIR, "processed_vouchers.json")
LOGO_FILE     = os.path.join(BASE_DIR, "logo_final.png")
ICON_FILE     = os.path.join(BASE_DIR, "icon.ico")

# ==================== الإصدار ====================

CURRENT_VERSION = "1.4.2"
VERSION_URL     = "https://raw.githubusercontent.com/meqdad11/arshif-almeqdad/main/version.json"
DOWNLOAD_URL    = "https://github.com/meqdad11/arshif-almeqdad/releases/latest/download/voucher_processor.exe"

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

# ==================== الإعدادات الافتراضية ====================

DEFAULT_SETTINGS = {
    "header_ratio":        0.30,
    "header_ratio_wide":   0.55,
    "languages":           ["ar", "en"],
    "appearance":          "dark",
    "id_conditions": [
        {"label": "السجل التجاري", "value": "4030100012"},
        {"label": "الرقم الضريبي", "value": "311250175400003"},
    ],
    "tax_expense_markers": ["البصمة", "Albasma"],
    "voucher_types": {
        "سند صرف":         {"folder": "سندات صرف"},
        "سند القبض":        {"folder": "سندات قبض"},
        "سندات قيد يومية": {"folder": "قبود يومية"},
        "مصروفات ضريبية":  {"folder": "مصروفات ضريبية"},
    },
    "last_pdf":     "",
    "last_archive": ""
}

# ==================== تحميل وحفظ الإعدادات ====================

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
