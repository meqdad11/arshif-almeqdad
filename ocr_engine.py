"""
ocr_engine.py
كل شي متعلق بقراءة الصفحات عبر EasyOCR
"""

import io
import fitz
import numpy as np
from PIL import Image


def read_page_text(page, reader, settings: dict, wide: bool = False) -> str:
    """
    قراءة نص الصفحة:
    - أولاً: قراءة نصية مباشرة من الـ PDF
    - ثانياً: لو النص قليل → OCR على جزء من الصفحة
    - wide=True → يوسع النسبة للقراءة الثانية الموسعة
    """
    text = page.get_text("text")
    if len(text.strip()) >= 50:
        return text

    ratio = settings.get("header_ratio_wide", 0.55) if wide else settings.get("header_ratio", 0.30)
    pix   = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img   = Image.open(io.BytesIO(pix.tobytes()))
    w, h  = img.size
    crop  = img.crop((0, 0, w, int(h * ratio)))
    text  = ' '.join(reader.readtext(np.array(crop), detail=0))
    del img, pix, crop
    return text


def load_reader(languages: list):
    """تحميل نموذج EasyOCR"""
    import easyocr
    return easyocr.Reader(languages)
