# ui/components/barcode_dialog.py
"""
نافذة ماسح الباركود بالكاميرا (0.1.9).

    open_barcode_scanner(parent, on_scan, continuous=True)

  on_scan(code) تُستدعى عند قراءة باركود جديد. يمكنها أن تُرجع نصاً قصيراً
  (مثل «✔ قلم — الكمية 3») فيُعرض داخل نافذة الماسح كتأكيد للمستخدم.
  continuous=True: تبقى النافذة مفتوحة لمسح عدة أصناف متتالية (تُغلق بزر
  «إغلاق»)، وإلا تُغلق بعد أول قراءة.

  - تعرض بثاً حياً من الكاميرا، وفك الباركود يجري في خيط منفصل فلا يتجمّد العرض.
  - يُمنع تكرار القراءة نفسها خلال ثانيتين (حتى لا يُحسب الصنف مرتين).
  - إن لم تتوفر مكتبات الكاميرا تظهر رسالة بطريقة التثبيت.
"""

import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from barcode_scanner import (
    INSTALL_HINT,
    available_backend,
    camera_supported,
    decode_frame,
    open_camera,
)

try:
    import cv2
    from PIL import Image
except Exception:                      # تُعالَج برسالة التثبيت
    cv2 = None
    Image = None

_BACKEND_TEXT = {
    "zxing": "المحرّك: zxing-cpp (كل الأنواع)",
    "pyzbar": "المحرّك: pyzbar",
    "opencv": "المحرّك: OpenCV (EAN-13 / EAN-8 / UPC-A / QR فقط — ثبّت zxing-cpp "
              "لباقي الأنواع)",
}

_DISPLAY_W = 640
_DECODE_EVERY = 3            # يُفكّ كل إطار ثالث
_REPEAT_SECONDS = 2.0        # لا تُكرَّر القراءة نفسها قبل ثانيتين
_TICK_MS = 30


def open_barcode_scanner(parent, on_scan, continuous=True):
    """يفتح نافذة الماسح، أو يعرض رسالة التثبيت إن لم تتوفر المكتبات."""
    if not camera_supported() or Image is None:
        messagebox.showinfo(
            "ماسح الكاميرا غير متاح", INSTALL_HINT, parent=parent
        )
        return None

    try:
        return BarcodeScannerDialog(parent, on_scan, continuous=continuous)
    except RuntimeError as error:
        messagebox.showerror("الكاميرا", str(error), parent=parent)
        return None


class BarcodeScannerDialog(ctk.CTkToplevel):

    def __init__(self, parent, on_scan, continuous=True, camera_index=0):
        # افتح الكاميرا أولاً: إن فشلت لا تُنشأ نافذة فارغة
        self.capture = open_camera(camera_index)

        super().__init__(parent)

        self._parent_top = parent.winfo_toplevel()
        self._prev_grab = None

        try:
            self._prev_grab = self._parent_top.grab_current()
        except tk.TclError:
            pass

        self.on_scan = on_scan
        self.camera_index = camera_index
        self._closed = False
        self._frame_no = 0
        self._decoding = False
        self._result = None
        self._last_code = None
        self._last_time = 0.0
        self._image_ref = None
        self._after_id = None

        self.title("📷 مسح الباركود")
        self.configure(fg_color="#f8fafc")
        self.resizable(False, False)

        self.video = ctk.CTkLabel(self, text="", width=_DISPLAY_W, height=360)
        self.video.pack(padx=16, pady=(16, 8))

        self.status = ctk.CTkLabel(
            self, text="وجّه الباركود نحو الكاميرا ...",
            font=("Cairo", 15, "bold"), text_color="#0f2a5c",
            wraplength=_DISPLAY_W,
        )
        self.status.pack(padx=16, pady=(0, 4))

        ctk.CTkLabel(
            self,
            text=_BACKEND_TEXT.get(available_backend(), ""),
            font=("Cairo", 11), text_color="#6b7280",
            wraplength=_DISPLAY_W,
        ).pack(padx=16)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=16, pady=(8, 16))
        controls.grid_columnconfigure(2, weight=1)

        self.continuous_var = ctk.StringVar(value="on" if continuous else "off")
        ctk.CTkCheckBox(
            controls, text="مسح متواصل", variable=self.continuous_var,
            onvalue="on", offvalue="off", font=("Cairo", 13, "bold"),
        ).grid(row=0, column=0, padx=(0, 12))

        self.camera_var = ctk.StringVar(value=f"كاميرا {camera_index}")
        ctk.CTkOptionMenu(
            controls, values=[f"كاميرا {i}" for i in range(4)],
            variable=self.camera_var, command=self._on_camera_changed,
            width=110, height=34, font=("Cairo", 12),
        ).grid(row=0, column=1)

        ctk.CTkButton(
            controls, text="إغلاق", command=self.close, width=110, height=38,
            fg_color="#6b7280", hover_color="#4b5563",
            font=("Cairo", 14, "bold"),
        ).grid(row=0, column=3)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

        self._place_window()
        self.after(150, self._make_modal)
        self._after_id = self.after(_TICK_MS, self._tick)

    # ---- النافذة ----
    def _place_window(self):
        self.update_idletasks()

        try:
            top = self._parent_top
            width, height = self.winfo_reqwidth(), self.winfo_reqheight()
            x = top.winfo_rootx() + (top.winfo_width() - width) // 2
            y = top.winfo_rooty() + (top.winfo_height() - height) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

    def _make_modal(self):
        if self._closed:
            return

        try:
            self.transient(self._parent_top)
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def close(self):
        if self._closed:
            return

        self._closed = True

        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass

        try:
            self.capture.release()
        except Exception:
            pass

        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()

        # إعادة الحجز إلى النافذة النمطية التي فُتح الماسح منها (إن وُجدت)
        prev = self._prev_grab

        if prev is not None:
            try:
                if prev.winfo_exists():
                    prev.grab_set()
            except tk.TclError:
                pass

    # ---- الكاميرا ----
    def _on_camera_changed(self, label):
        try:
            index = int(label.split()[-1])
        except ValueError:
            return

        try:
            new_capture = open_camera(index)
        except RuntimeError as error:
            messagebox.showerror("الكاميرا", str(error), parent=self)
            self.camera_var.set(f"كاميرا {self.camera_index}")
            return

        try:
            self.capture.release()
        except Exception:
            pass

        self.capture = new_capture
        self.camera_index = index

    def _tick(self):
        if self._closed:
            return

        try:
            ok, frame = self.capture.read()
        except Exception:
            ok, frame = False, None

        if ok and frame is not None:
            self._show(frame)
            self._frame_no += 1

            if not self._decoding and self._frame_no % _DECODE_EVERY == 0:
                self._decoding = True
                threading.Thread(
                    target=self._decode_worker, args=(frame.copy(),),
                    daemon=True,
                ).start()

        code, self._result = self._result, None

        if code:
            self._handle_code(code)

        if not self._closed:
            self._after_id = self.after(_TICK_MS, self._tick)

    def _show(self, frame):
        height, width = frame.shape[:2]
        scale = _DISPLAY_W / float(width)
        size = (_DISPLAY_W, max(int(height * scale), 1))

        rgb = cv2.cvtColor(cv2.resize(frame, size), cv2.COLOR_BGR2RGB)
        image = ctk.CTkImage(
            light_image=Image.fromarray(rgb), size=size
        )

        self._image_ref = image            # يمنع حذف الصورة من الذاكرة
        self.video.configure(image=image)

    def _decode_worker(self, frame):
        try:
            self._result = decode_frame(frame)
        finally:
            self._decoding = False

    # ---- القراءة ----
    def _handle_code(self, code):
        now = time.monotonic()

        if code == self._last_code and now - self._last_time < _REPEAT_SECONDS:
            return

        self._last_code, self._last_time = code, now
        self._beep()

        try:
            message = self.on_scan(code)
        except Exception as error:
            message = f"⚠ {error}"

        self.status.configure(text=message or f"✔ تمت القراءة: {code}")

        if self.continuous_var.get() != "on":
            self.after(350, self.close)

    def _beep(self):
        try:
            import winsound
            winsound.Beep(1400, 110)
        except Exception:
            try:
                self.bell()
            except tk.TclError:
                pass
