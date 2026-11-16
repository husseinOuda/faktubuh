# ui/components/print_utils.py
"""
الطباعة المباشرة لملفات PDF (0.1.7)

المشكلة السابقة: os.startfile(path, "print") يعتمد على برنامج مرتبط بملفات PDF
في ويندوز، وإن لم يوجد يفشل بالخطأ WinError 1155.

الحل: نرسم صفحات الـ PDF بـ PyMuPDF ونرسلها مباشرة إلى الطابعة عبر
واجهة ويندوز (GDI/winspool) باستخدام ctypes — بلا أي مكتبة إضافية
وبلا حاجة لبرنامج PDF مثبّت. وعند الفشل نجرّب بدائل بالترتيب.
"""

import os
import subprocess
import sys

import fitz
from PIL import Image

IS_WINDOWS = sys.platform.startswith("win")

# أقصى دقة للطباعة (نقطة/بوصة): توازن بين الجودة والذاكرة
MAX_PRINT_DPI = 300


# =========================
# تحليل مدى الصفحات: "1-3, 5, 8-"
# =========================
def parse_page_range(text, page_count):
    """يرجع قائمة أرقام صفحات (تبدأ من 0) أو يرفع ValueError."""
    text = (text or "").strip().replace("،", ",").replace("؛", ",")

    if not text:
        raise ValueError("أدخل مدى الصفحات")

    pages = []
    seen = set()

    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            if "-" in part:
                left, _, right = part.partition("-")
                left, right = left.strip(), right.strip()

                start = int(left) if left else 1
                end = int(right) if right else page_count
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"قيمة غير صالحة: {part}") from None

        if start < 1 or end > page_count or start > end:
            raise ValueError(
                f"مدى غير صالح: {part} (عدد الصفحات {page_count})"
            )

        for number in range(start, end + 1):
            if number - 1 not in seen:
                seen.add(number - 1)
                pages.append(number - 1)

    if not pages:
        raise ValueError("أدخل مدى الصفحات")

    return pages


# =========================
# الطابعات المتاحة (ويندوز)
# =========================
def list_printers():
    """يرجع (قائمة الطابعات، الطابعة الافتراضية). فارغة خارج ويندوز."""
    if not IS_WINDOWS:
        return [], ""

    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    PRINTER_ENUM_LOCAL = 0x2
    PRINTER_ENUM_CONNECTIONS = 0x4

    class PRINTER_INFO_4W(ctypes.Structure):
        _fields_ = [
            ("pPrinterName", wintypes.LPWSTR),
            ("pServerName", wintypes.LPWSTR),
            ("Attributes", wintypes.DWORD),
        ]

    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)

    winspool.EnumPrintersW(
        flags, None, 4, None, 0,
        ctypes.byref(needed), ctypes.byref(returned)
    )

    names = []

    if needed.value:
        buffer = ctypes.create_string_buffer(needed.value)

        ok = winspool.EnumPrintersW(
            flags, None, 4, buffer, needed.value,
            ctypes.byref(needed), ctypes.byref(returned)
        )

        if ok:
            array_type = PRINTER_INFO_4W * returned.value
            infos = ctypes.cast(
                buffer, ctypes.POINTER(array_type)
            ).contents

            names = [info.pPrinterName for info in infos if info.pPrinterName]

    default = ""
    size = wintypes.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(size))

    if size.value:
        name_buffer = ctypes.create_unicode_buffer(size.value)

        if winspool.GetDefaultPrinterW(name_buffer, ctypes.byref(size)):
            default = name_buffer.value

    return names, default


# =========================
# الطباعة المباشرة عبر GDI (ويندوز)
# =========================
def _print_gdi_iter(pdf_path, printer_name, page_indexes, copies):
    """مولّد: يطبع صفحة صفحة ويُنتج (المنجز، الإجمالي) بعد كل صفحة."""
    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    HORZRES, VERTRES = 8, 10
    LOGPIXELSX, LOGPIXELSY = 88, 90
    PHYSICALWIDTH, PHYSICALHEIGHT = 110, 111
    HALFTONE = 4
    DIB_RGB_COLORS = 0
    SRCCOPY = 0x00CC0020

    class DOCINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_int),
            ("lpszDocName", wintypes.LPCWSTR),
            ("lpszOutput", wintypes.LPCWSTR),
            ("lpszDatatype", wintypes.LPCWSTR),
            ("fwType", wintypes.DWORD),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    gdi32.CreateDCW.restype = wintypes.HDC
    gdi32.CreateDCW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p
    ]
    gdi32.StartDocW.argtypes = [wintypes.HDC, ctypes.POINTER(DOCINFOW)]
    gdi32.StartPage.argtypes = [wintypes.HDC]
    gdi32.EndPage.argtypes = [wintypes.HDC]
    gdi32.EndDoc.argtypes = [wintypes.HDC]
    gdi32.AbortDoc.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.StretchDIBits.argtypes = [
        wintypes.HDC,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p,
        wintypes.UINT, wintypes.DWORD,
    ]

    hdc = gdi32.CreateDCW("WINSPOOL", printer_name, None, None)

    if not hdc:
        raise OSError(f"تعذّر الاتصال بالطابعة: {printer_name}")

    doc = fitz.open(pdf_path)
    started = False

    try:
        docinfo = DOCINFOW()
        docinfo.cbSize = ctypes.sizeof(DOCINFOW)
        docinfo.lpszDocName = os.path.basename(pdf_path)
        docinfo.lpszOutput = None
        docinfo.lpszDatatype = None
        docinfo.fwType = 0

        if gdi32.StartDocW(hdc, ctypes.byref(docinfo)) <= 0:
            raise OSError("رفضت الطابعة بدء المهمة")

        started = True

        dpi_x = gdi32.GetDeviceCaps(hdc, LOGPIXELSX) or 300
        dpi_y = gdi32.GetDeviceCaps(hdc, LOGPIXELSY) or 300
        dpi = min(max(dpi_x, dpi_y), MAX_PRINT_DPI)

        # قياس الورقة الفعلية ومنطقة الطباعة (بالبكسل)
        phys_w = gdi32.GetDeviceCaps(hdc, PHYSICALWIDTH)
        phys_h = gdi32.GetDeviceCaps(hdc, PHYSICALHEIGHT)
        print_w = gdi32.GetDeviceCaps(hdc, HORZRES)
        print_h = gdi32.GetDeviceCaps(hdc, VERTRES)
        off_x = gdi32.GetDeviceCaps(hdc, 112)  # PHYSICALOFFSETX
        off_y = gdi32.GetDeviceCaps(hdc, 113)  # PHYSICALOFFSETY

        if not phys_w or not phys_h:
            phys_w, phys_h = print_w, print_h
            off_x = off_y = 0

        total = len(page_indexes) * copies
        done = 0

        for _copy in range(copies):
            for index in page_indexes:
                page = doc.load_page(index)

                scale = dpi / 72.0
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csRGB,
                    alpha=False,
                )

                image = Image.frombytes(
                    "RGB", (pix.width, pix.height), pix.samples
                )

                # عرض الصف في BMP يجب أن يكون مضاعف 4 بايت => العرض مضاعف 4
                width = pix.width - (pix.width % 4)
                if width != pix.width:
                    image = image.crop((0, 0, width, pix.height))

                red, green, blue = image.split()
                data = Image.merge("RGB", (blue, green, red)).tobytes()

                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = width
                bmi.biHeight = -pix.height  # سالب = من الأعلى للأسفل
                bmi.biPlanes = 1
                bmi.biBitCount = 24
                bmi.biCompression = 0

                # ملاءمة الصفحة على الورقة مع الحفاظ على النسبة وتوسيطها
                ratio = min(phys_w / width, phys_h / pix.height)
                dest_w = int(width * ratio)
                dest_h = int(pix.height * ratio)
                dest_x = (phys_w - dest_w) // 2 - off_x
                dest_y = (phys_h - dest_h) // 2 - off_y

                if gdi32.StartPage(hdc) <= 0:
                    raise OSError("فشل بدء صفحة الطباعة")

                gdi32.SetStretchBltMode(hdc, HALFTONE)

                lines = gdi32.StretchDIBits(
                    hdc,
                    dest_x, dest_y, dest_w, dest_h,
                    0, 0, width, pix.height,
                    data, ctypes.byref(bmi),
                    DIB_RGB_COLORS, SRCCOPY,
                )

                gdi32.EndPage(hdc)

                if lines == 0 or lines == -1:
                    raise OSError("فشل إرسال الصفحة إلى الطابعة")

                done += 1
                yield done, total

        gdi32.EndDoc(hdc)
        started = False

    except BaseException:
        # BaseException ليشمل إغلاق المولّد (GeneratorExit) عند إغلاق النافذة
        if started:
            gdi32.AbortDoc(hdc)
        raise

    finally:
        doc.close()
        gdi32.DeleteDC(hdc)


# =========================
# بدائل عند فشل الطباعة المباشرة
# =========================
def _find_pdf_printer_exe():
    """يبحث عن برنامج PDF معروف يدعم الطباعة من سطر الأوامر."""
    candidates = []

    for base in filter(None, [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]):
        candidates += [
            ("sumatra", os.path.join(base, "SumatraPDF", "SumatraPDF.exe")),
            ("adobe", os.path.join(base, "Adobe", "Acrobat DC", "Acrobat", "Acrobat.exe")),
            ("adobe", os.path.join(base, "Adobe", "Acrobat Reader DC", "Reader", "AcroRd32.exe")),
            ("foxit", os.path.join(base, "Foxit Software", "Foxit PDF Reader", "FoxitPDFReader.exe")),
        ]

    for kind, path in candidates:
        if os.path.exists(path):
            return kind, path

    return None, None


def _print_with_external(pdf_path, printer_name):
    kind, exe = _find_pdf_printer_exe()

    if not exe:
        return False

    if kind == "sumatra":
        args = [exe, "-print-to", printer_name, "-silent", pdf_path] \
            if printer_name else [exe, "-print-to-default", "-silent", pdf_path]
    elif kind == "adobe":
        args = [exe, "/t", pdf_path] + ([printer_name] if printer_name else [])
    else:
        args = [exe, "/t", pdf_path] + ([printer_name] if printer_name else [])

    subprocess.Popen(args)
    return True


def _print_unix(pdf_path, printer_name):
    for command in ("lp", "lpr"):
        try:
            args = [command]
            if printer_name:
                args += ["-d" if command == "lp" else "-P", printer_name]
            args.append(pdf_path)
            subprocess.run(args, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


# =========================
# الواجهة العامة
# =========================
def iter_print_pdf(pdf_path, printer_name="", page_indexes=None, copies=1):
    """
    مولّد للطباعة: يُنتج ("progress", المنجز, الإجمالي) أثناء الطباعة المباشرة
    ثم ("done", الطريقة). يرفع OSError برسالة واضحة إذا فشلت كل الطرق.

    يعمل على خيط الواجهة صفحة بصفحة (PyMuPDF لا يُنصح به عبر خيوط متعددة).
    page_indexes: أرقام صفحات تبدأ من 0 (None = كل الصفحات).
    """
    pdf_path = os.path.abspath(pdf_path)

    if not os.path.exists(pdf_path):
        raise OSError("ملف PDF غير موجود")

    if page_indexes is None:
        with fitz.open(pdf_path) as doc:
            page_indexes = list(range(len(doc)))

    copies = max(1, int(copies or 1))
    errors = []

    if IS_WINDOWS:
        if not printer_name:
            _, printer_name = list_printers()

        # 1) الطباعة المباشرة (لا تحتاج أي برنامج PDF)
        if printer_name:
            try:
                for done, total in _print_gdi_iter(
                    pdf_path, printer_name, page_indexes, copies
                ):
                    yield ("progress", done, total)
                yield ("done", "direct")
                return
            except Exception as e:
                errors.append(f"الطباعة المباشرة: {e}")

        # 2) برنامج PDF مثبّت يدعم الطباعة الصامتة
        try:
            if _print_with_external(pdf_path, printer_name):
                yield ("done", "external")
                return
        except Exception as e:
            errors.append(f"برنامج PDF: {e}")

        # 3) الطريقة القديمة (قد تفشل إن لم يوجد برنامج مرتبط)
        try:
            os.startfile(pdf_path, "print")
            yield ("done", "shell")
            return
        except OSError as e:
            errors.append(f"طباعة ويندوز: {e}")

    else:
        try:
            if _print_unix(pdf_path, printer_name):
                yield ("done", "unix")
                return
        except Exception as e:
            errors.append(str(e))

    raise OSError(
        ("تعذّرت الطباعة.\n\n" + "\n".join(errors))
        if errors else "لا توجد طابعة متاحة"
    )


def print_pdf_file(pdf_path, printer_name="", page_indexes=None, copies=1):
    """نسخة متزامنة من iter_print_pdf (للاستخدام خارج نافذة المعاينة)."""
    method = ""
    for event in iter_print_pdf(pdf_path, printer_name, page_indexes, copies):
        if event[0] == "done":
            method = event[1]
    return method


def open_pdf_safely(pdf_path):
    """يفتح PDF بالبرنامج الافتراضي، وإن لم يوجد برنامج يفتحه في المتصفح."""
    pdf_path = os.path.abspath(pdf_path)

    try:
        if hasattr(os, "startfile"):
            os.startfile(pdf_path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, pdf_path])
        return
    except OSError:
        pass

    import webbrowser
    from pathlib import Path

    if not webbrowser.open(Path(pdf_path).as_uri()):
        raise OSError("لا يوجد برنامج لفتح ملفات PDF على هذا الجهاز")
