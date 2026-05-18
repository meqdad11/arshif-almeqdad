"""
detector.py
منطق التعرف على نوع السند من النص المقروء
"""


def detect_voucher(text: str, settings: dict):
    """
    يرجع (is_main: bool, folder: str | None)

    المنطق:
    1. المصروفات الضريبية: اسم الشركة + كلمة "مصروفات ضريبية"
    2. بقية السندات: شرط تعرف عام (رقم ضريبي أو سجل) + نوع السند
    """

    # ── المصروفات الضريبية ──
    tax_markers = settings.get("tax_expense_markers", [])
    has_company = any(m in text for m in tax_markers)
    if has_company and "مصروفات ضريبية" in text:
        folder = settings["voucher_types"].get(
            "مصروفات ضريبية", {"folder": "مصروفات ضريبية"})["folder"]
        return True, folder

    # ── بقية السندات ──
    id_conditions = [c["value"] for c in settings.get("id_conditions", []) if c.get("value")]
    has_id = any(cond in text for cond in id_conditions) if id_conditions else False
    if not has_id:
        return False, None

    # الأطول أولاً عشان "سند القبض" يُلقى قبل "قبض"
    type_priority = [
        "سند الصرف", "سند القبض",
        "سندات قيد يومية", "قيد يومية",
        "رواتب", "يومية",
    ]

    for vtype in type_priority:
        if vtype in text and vtype in settings["voucher_types"]:
            return True, settings["voucher_types"][vtype]["folder"]

    # بحث احتياطي في بقية الأنواع المحفوظة
    for vtype, info in settings["voucher_types"].items():
        if vtype not in type_priority and vtype in text:
            return True, info["folder"]

    return False, None
