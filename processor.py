"""
processor.py
معالجة ملف الـ PDF وفصل السندات
"""

import os
import re
import fitz

from config import save_memory, is_processed, mark_processed
from detector import detect_voucher
from ocr_engine import read_page_text


def process_pdf(pdf_file: str, archive_root: str, settings: dict,
                reader, memory: dict,
                on_progress=None, on_log=None, on_preview=None,
                stop_flag_fn=None):
    """
    المعالجة الرئيسية لملف PDF.

    المعاملات:
    - on_progress(page_num, total)  ← تحديث شريط التقدم
    - on_log(msg)                   ← إضافة سطر للسجل
    - on_preview(page, page_num, total, label) ← تحديث المعاينة
    - stop_flag_fn()                ← دالة ترجع True لو المستخدم ضغط إيقاف

    يرجع: dict نتائج
    """

    def log(msg):
        if on_log: on_log(msg)

    doc   = fitz.open(pdf_file)
    total = len(doc)
    log(f"عدد الصفحات: {total}")

    cur_pdf    = None
    cur_no     = ""
    cur_folder = ""
    n_vouchers = 0
    n_attach   = 0
    n_unknown  = 0
    n_skipped  = 0
    n_memory   = 0
    unk_pages  = []

    def save_current():
        nonlocal n_skipped, n_memory, cur_pdf
        if not cur_pdf:
            return
        sd       = os.path.join(archive_root, cur_folder)
        os.makedirs(sd, exist_ok=True)
        out_path = os.path.join(sd, f"{cur_no}.pdf")

        if is_processed(memory, cur_no):
            n_memory += 1
            log(f"  [🧠] في الذاكرة — تم تخطي: {cur_no}")
            cur_pdf.close()
        elif os.path.exists(out_path):
            n_skipped += 1
            log(f"  [⚠] ملف موجود — تم تخطي: {cur_no}.pdf")
            cur_pdf.close()
        else:
            cur_pdf.save(out_path)
            cur_pdf.close()
            mark_processed(memory, cur_no, cur_folder, archive_root)

        cur_pdf = None

    try:
        for i in range(total):
            if stop_flag_fn and stop_flag_fn():
                log("تم الإيقاف من قبل المستخدم.")
                break

            if on_progress:
                on_progress(i + 1, total)

            page = doc.load_page(i)

            if on_preview:
                on_preview(page, i + 1, total, "")

            # ── قراءة أولى ──
            text = read_page_text(page, reader, settings, wide=False)

            # ── تعرف على السند ──
            is_main, folder = detect_voucher(text, settings)

            # ── قراءة موسعة لو ما لقى ──
            if not is_main and len(page.get_text("text").strip()) < 50:
                text2 = read_page_text(page, reader, settings, wide=True)
                is_main, folder = detect_voucher(text2, settings)
                if is_main:
                    text = text2
                    log(f"  [↕] قراءة موسعة نجحت | ص{i+1}")

            if len(text.strip()) < 20 and cur_pdf is None:
                continue

            if is_main:
                m   = re.search(r'(00\d{7})', text)
                vno = m.group(1) if m else None

                # نفس السند — أضف الصفحة للحالي
                if vno and vno == cur_no:
                    cur_pdf.insert_pdf(doc, from_page=i, to_page=i)
                    log(f"  [=] تابع: {cur_no} | ص{i+1}")
                    continue

                # احفظ السند السابق
                save_current()

                # سند جديد
                if not folder:
                    folder = "سندات منوعة"

                if vno:
                    cur_no = vno
                else:
                    cur_no = f"رقم_مجهول_ص{i+1}"
                    n_unknown += 1
                    unk_pages.append(i + 1)
                    folder = "مجهول"

                cur_folder  = folder
                n_vouchers += 1
                cur_pdf     = fitz.open()
                cur_pdf.insert_pdf(doc, from_page=i, to_page=i)

                lbl = f"{folder} | {cur_no}"
                log(f"[OK] {lbl} | ص{i+1}")

                if on_preview:
                    on_preview(page, i + 1, total, lbl)

            else:
                if cur_pdf:
                    cur_pdf.insert_pdf(doc, from_page=i, to_page=i)
                    n_attach += 1
                    log(f"  [+] مرفق | ص{i+1}")

    finally:
        save_current()
        doc.close()
        save_memory(memory)

    return {
        "total":      total,
        "vouchers":   n_vouchers,
        "attachments": n_attach,
        "unknown":    n_unknown,
        "skipped":    n_skipped,
        "memory":     n_memory,
        "unk_pages":  unk_pages,
    }
