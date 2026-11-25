# barcode_scanner.py
"""
ماسح الباركود بالكاميرا (0.1.9) — طبقة فك الباركود والتقاط الصور (بلا واجهة).

المكتبات (كلها اختيارية؛ يُستخدم أول ما هو مثبّت بهذا الترتيب):

    1) zxing-cpp      pip install zxing-cpp          الأفضل: يقرأ كل الأنواع
                                                      (EAN/UPC/Code128/Code39/QR/...)
    2) pyzbar         pip install pyzbar             يقرأ الأنواع الشائعة وQR
    3) OpenCV         pip install opencv-python      يقرأ EAN-13/EAN-8/UPC-A وQR فقط

الكاميرا والعرض يحتاجان دائماً:  pip install opencv-python pillow

ملاحظة: القارئ اليدوي (USB) لا يحتاج شيئاً من هذا؛ فهو يكتب الرقم كلوحة مفاتيح
ثم Enter في حقل الباركود.

الاستخدام:
    from barcode_scanner import available_backend, decode_frame, open_camera
    code = decode_frame(frame)     # نص الباركود أو None
"""

try:
    import cv2
except Exception:                      # opencv غير مثبّت
    cv2 = None

try:
    import zxingcpp
except Exception:
    zxingcpp = None

try:
    from pyzbar import pyzbar
except Exception:                      # غير مثبّت أو ينقصه zbar
    pyzbar = None

INSTALL_HINT = (
    "لتشغيل ماسح الكاميرا ثبّت المكتبات التالية ثم أعد تشغيل البرنامج:\n\n"
    "pip install opencv-python pillow zxing-cpp\n\n"
    "(zxing-cpp يقرأ كل أنواع الباركود. وبدونه يقرأ البرنامج EAN-13 وQR فقط "
    "عبر OpenCV.)"
)


def camera_supported():
    """هل المكتبات الأساسية للكاميرا (OpenCV) متوفرة؟"""
    return cv2 is not None


def available_backend():
    """اسم محرّك فك الباركود المستخدم: zxing | pyzbar | opencv | None."""
    if zxingcpp is not None:
        return "zxing"

    if pyzbar is not None:
        return "pyzbar"

    if cv2 is not None and hasattr(cv2, "barcode"):
        return "opencv"

    if cv2 is not None:
        return "opencv"

    return None


def clean_code(text):
    """ينظّف الباركود المقروء (مسافات/أسطر زائدة)."""
    return str(text or "").strip()


# ======================
# فك الباركود من صورة (إطار OpenCV بصيغة BGR)
# ======================
def _decode_zxing(frame):
    results = zxingcpp.read_barcodes(frame)

    for result in results:
        text = clean_code(result.text)

        if text:
            return text

    return None


def _decode_pyzbar(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if cv2 is not None else frame

    for result in pyzbar.decode(gray):
        text = clean_code(result.data.decode("utf-8", errors="replace"))

        if text:
            return text

    return None


_qr_detector = None
_bar_detector = None


def _decode_opencv(frame):
    """EAN/UPC (إن وُجدت وحدة barcode) وQR. يجرّب عدة مقاييس لأن الدقة تؤثر."""
    global _qr_detector, _bar_detector

    if _bar_detector is None and hasattr(cv2, "barcode"):
        _bar_detector = cv2.barcode.BarcodeDetector()

    if _qr_detector is None:
        _qr_detector = cv2.QRCodeDetector()

    for scale in (1.0, 0.6, 1.6):
        image = frame if scale == 1.0 else cv2.resize(
            frame, None, fx=scale, fy=scale,
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )

        if _bar_detector is not None:
            try:
                ok, info, _types, _points = _bar_detector.detectAndDecodeWithType(
                    image
                )
            except Exception:
                ok, info = False, ()

            if ok:
                for text in info:
                    text = clean_code(text)

                    if text:
                        return text

        try:
            text, _points, _raw = _qr_detector.detectAndDecode(image)
        except Exception:
            text = ""

        text = clean_code(text)

        if text:
            return text

    return None


def decode_frame(frame):
    """يرجع نص أول باركود في الإطار أو None."""
    if frame is None:
        return None

    try:
        if zxingcpp is not None:
            return _decode_zxing(frame)

        if pyzbar is not None:
            return _decode_pyzbar(frame)

        if cv2 is not None:
            return _decode_opencv(frame)

    except Exception:
        return None

    return None


# ======================
# الكاميرا
# ======================
def list_cameras(max_index=4):
    """أرقام الكاميرات المتاحة (0..max_index-1). قد يستغرق ثوانٍ على بعض الأجهزة."""
    if cv2 is None:
        return []

    found = []

    for index in range(max_index):
        capture = _open_capture(index)

        if capture is not None and capture.isOpened():
            found.append(index)
            capture.release()

    return found


def _open_capture(index):
    # CAP_DSHOW أسرع وأكثر ثباتاً على ويندوز؛ وعلى غيره يُستخدم الافتراضي
    for backend in (getattr(cv2, "CAP_DSHOW", None), None):
        try:
            capture = (
                cv2.VideoCapture(index, backend) if backend is not None
                else cv2.VideoCapture(index)
            )
        except Exception:
            continue

        if capture is not None and capture.isOpened():
            return capture

        if capture is not None:
            capture.release()

    return None


def open_camera(index=0):
    """يفتح الكاميرا ويرجع كائن VideoCapture، أو يرفع RuntimeError برسالة عربية."""
    if cv2 is None:
        raise RuntimeError(INSTALL_HINT)

    capture = _open_capture(index)

    if capture is None:
        raise RuntimeError(
            "تعذّر فتح الكاميرا.\n"
            "تأكد أنها متصلة وأن برنامجاً آخر لا يستخدمها، "
            "وأن ويندوز يسمح للتطبيقات بالوصول إلى الكاميرا."
        )

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return capture
