# ui/components/cards.py
"""بطاقات الأرقام (KPI) المستخدمة في صفحات المالية."""

import customtkinter as ctk


class StatCard(ctk.CTkFrame):
    """بطاقة: عنوان صغير + قيمة كبيرة ملوّنة + سطر توضيحي اختياري."""

    def __init__(self, parent, title, value="0", color="#2563eb",
                 subtitle=""):
        super().__init__(
            parent,
            fg_color="white",
            corner_radius=12,
            border_width=1,
            border_color="#e5e7eb",
        )

        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=("Cairo", 13),
            text_color="#6b7280",
        )
        self.title_label.grid(row=0, column=0, padx=12, pady=(10, 0))

        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            font=("Cairo", 20, "bold"),
            text_color=color,
        )
        self.value_label.grid(row=1, column=0, padx=12, pady=(0, 0))

        self.sub_label = ctk.CTkLabel(
            self,
            text=subtitle,
            font=("Cairo", 11),
            text_color="#9ca3af",
        )
        self.sub_label.grid(row=2, column=0, padx=12, pady=(0, 8))

    def set(self, value, subtitle=None, color=None):
        self.value_label.configure(text=value)

        if color:
            self.value_label.configure(text_color=color)

        if subtitle is not None:
            self.sub_label.configure(text=subtitle)
