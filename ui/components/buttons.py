# ui/components/buttons.py
"""أزرار موحّدة بألوان الهوية لصفحات المالية."""

import customtkinter as ctk

# اسم اللون -> (اللون، لون التمرير)
BUTTON_COLORS = {
    "blue": ("#2563eb", "#1d4ed8"),
    "green": ("#16a34a", "#15803d"),
    "orange": ("#ea580c", "#c2410c"),
    "red": ("#dc2626", "#b91c1c"),
    "gray": ("#6b7280", "#4b5563"),
    "purple": ("#7c3aed", "#6d28d9"),
    "navy": ("#0f2a5c", "#1b3a7a"),
}


def make_button(parent, text, command, color="blue", **kwargs):
    fg, hover = BUTTON_COLORS.get(color, BUTTON_COLORS["blue"])

    options = dict(
        text=text,
        command=command,
        fg_color=fg,
        hover_color=hover,
        height=38,
        corner_radius=10,
        font=("Cairo", 13, "bold"),
    )
    options.update(kwargs)

    return ctk.CTkButton(parent, **options)
