import tkinter as tk
from PIL import ImageFilter, ImageTk
from . import windows


class Overlay:
    def __init__(self, root):
        self.root = root
        self.widgets = []
        self.images = []

    def clear(self):
        for widget in self.widgets:
            widget.destroy()
        self.widgets.clear()
        self.images.clear()

    def show(self, image, boxes, origin, mode):
        self.clear()
        try:
            for box in boxes:
                window = tk.Toplevel(self.root)
                self.widgets.append(window)
                window.withdraw()
                window.overrideredirect(True)
                window.attributes("-topmost", True)
                window.configure(bg="#3d4652")
                window.geometry(f"{box.width}x{box.height}{origin[0]+box.x:+d}{origin[1]+box.y:+d}")
                if mode == "blur":
                    crop = image.crop((box.x, box.y, box.x+box.width, box.y+box.height)).filter(ImageFilter.GaussianBlur(18))
                    photo = ImageTk.PhotoImage(crop)
                    self.images.append(photo)
                    tk.Label(window, image=photo, bd=0).pack(fill="both", expand=True)
                elif mode == "placeholder":
                    tk.Label(window, text="숨긴 메시지입니다", bg="#3d4652", fg="white", font=("맑은 고딕", 9)).pack(fill="both", expand=True)
                hwnd = windows.prepare_overlay(window)
                windows.show_without_focus(hwnd, origin[0]+box.x, origin[1]+box.y, box.width, box.height)
        except Exception:
            self.clear()
            raise
