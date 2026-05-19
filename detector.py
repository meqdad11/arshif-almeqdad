"""
detector.py
منطق التعرف على نوع السند من النص المقروء
"""

import re


def normalize(text: str) -> str:
    """تنظيف النص من المسافات الزائدة"""
    return re.sub(r'\s+', ' ', text).strip()


def detect_voucher(text: str, settings: dict):
    """
    يرجع (is_main: bool, folder: str | None)

    المنطق:
    1. المصروفات الضريبية: اسم الشركة + "مصروفات ضريبية"
    2. بقية السندات: شرط تعرف عام (رقم ضريبي أو سجل) + نوع السند
    """

    text_clean = normalize(text)

    # المصروفات الضريبية
    tax_markers = settings.get("tax_expense_markers", [])
    has_company = any(m in text_clean for m in tax_markers)
    if has_company and "مصروفات ضريبية" in text_clean:
        folder = settings["voucher_types"].get(
            "مصروفات ضريبية", {"folder": "مصروفات ضريبية"})["folder"]
        return True, folder

    # بقية السندات
    id_conditions = [c["value"] for c in settings.get("id_conditions", []) if c.get("value")]
    has_id = any(cond in text_clean for cond in id_conditions) if id_conditions else False
    if not has_id:
        return False, None

    # الترتيب مهم: الاطول اولا
    type_priority = [
        "سندات قيد يومية",
        "سند القبض",
        "سند صرف",
        "قيد يومية",
        "رواتب",
        "يومية",
    ]

    for vtype in type_priority:
        if vtype in text_clean:
            if vtype in settings["voucher_types"]:
                return True, settings["voucher_types"][vtype]["folder"]
            for key, info in settings["voucher_types"].items():
                if key in vtype or vtype in key:
                    return True, info["folder"]

    for vtype, info in settings["voucher_types"].items():
        if vtype not in type_priority and vtype in text_clean:
            return True, info["folder"]

    return False, None
