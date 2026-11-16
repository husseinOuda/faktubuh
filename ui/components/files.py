# ui/components/files.py
"""فتح الملفات وتصدير Excel (مشتركة بين صفحات السندات والمصروفات)."""

import os
import subprocess
import sys
from tkinter import filedialog, messagebox


def open_file(path, print_it=False):
    """
    يفتح الملف بالبرنامج الافتراضي أو يطبعه (0.1.7).

    الطباعة صارت مباشرة عبر PyMuPDF + طابعة ويندوز، فلا تحتاج برنامج PDF مرتبطاً
    (كانت os.startfile(..., "print") تفشل بالخطأ WinError 1155).
    """
    path = os.path.abspath(path)

    if path.lower().endswith(".pdf"):
        from ui.components.print_utils import open_pdf_safely, print_pdf_file

        if print_it:
            print_pdf_file(path)
        else:
            open_pdf_safely(path)
        return

    if hasattr(os, "startfile"):
        if print_it:
            os.startfile(path, "print")
        else:
            os.startfile(path)
        return

    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path])


def export_rows_excel(parent, headers, rows, default_name):
    """يحفظ الصفوف في ملف Excel يختاره المستخدم. يرجع المسار أو None."""
    try:
        import pandas as pd

        path = filedialog.asksaveasfilename(
            parent=parent,
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")],
        )

        if not path:
            return None

        pd.DataFrame(rows, columns=headers).to_excel(path, index=False)

        messagebox.showinfo("نجاح", "تم تصدير ملف Excel بنجاح", parent=parent)
        return path

    except Exception as e:
        messagebox.showerror("خطأ", str(e), parent=parent)
        return None
