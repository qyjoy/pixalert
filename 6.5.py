import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog, Menu, font
import cv2
import numpy as np
import mss
import pygame
from PIL import Image, ImageTk, ImageEnhance
import threading
import time
import os
import ctypes
import pyautogui
import math
import colorsys
import win32gui
import win32ui
import win32con
import sys
import json


CPU_CORES = os.cpu_count() or 4  
APP_TITLE = f"PixAlert v6.5 - Vision-Click Automation ({CPU_CORES} cores)"
CONFIG_SCHEMA_VERSION = "1.0"  
pyautogui.PAUSE = 0.01

try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception: pass

COLOR_BG = "#1E1E1E"
COLOR_PANEL = "#252525"
COLOR_BORDER = "#333333"
COLOR_ACCENT = "#00E5FF"
COLOR_WARN = "#FF3333"
COLOR_SUCCESS = "#00FF99"
COLOR_TEXT = "#E0E0E0"
COLOR_DIM = "#888888"
COLOR_STATUS_HIT = "#FFC107"

def resource_path(relative_path):
    """Resolve a resource's absolute path, compatible with the dev environment,
    PyInstaller, and Nuitka builds."""
    # 1. PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)

    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))

    return os.path.join(base_path, relative_path)

class SnippingTool(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.withdraw()
        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[0])
            self.src_img_np = np.array(sct_img)
            self.src_img_rgb = cv2.cvtColor(self.src_img_np, cv2.COLOR_BGRA2RGB)
            self.original_pil = Image.fromarray(self.src_img_rgb)
        self.tk_dark_img = ImageTk.PhotoImage(ImageEnhance.Brightness(self.original_pil).enhance(0.4))
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.configure(cursor="cross")
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.tk_dark_img, anchor="nw")
        self.start_x = self.start_y = self.selection_rect_id = self.highlight_img_id = None
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<ButtonPress-3>", self.exit_snip)
        self.bind("<Escape>", self.exit_snip)
        self.deiconify()

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.selection_rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline=COLOR_ACCENT, width=2)

    def on_drag(self, event):
        if not self.start_x: return
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        self.canvas.coords(self.selection_rect_id, x1, y1, x2, y2)
        if x2 - x1 > 0 and y2 - y1 > 0:
            self.tk_region_img = ImageTk.PhotoImage(self.original_pil.crop((x1, y1, x2, y2)))
            if self.highlight_img_id is None: self.highlight_img_id = self.canvas.create_image(x1, y1, image=self.tk_region_img, anchor="nw")
            else:
                self.canvas.coords(self.highlight_img_id, x1, y1)
                self.canvas.itemconfig(self.highlight_img_id, image=self.tk_region_img)
            self.canvas.tag_raise(self.selection_rect_id)

    def on_release(self, event):
        if self.start_x is None: return
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.destroy()
            self.callback(cv2.cvtColor(self.src_img_np[y1:y2, x1:x2], cv2.COLOR_BGRA2BGR))
        else: self.exit_snip()

    def exit_snip(self, event=None):
        self.destroy()

class RegionPickerTool(tk.Toplevel):
    """
    Region-picker tool.
    Interaction is identical to SnippingTool (drag to select + live preview
    highlight), but instead of returning a cropped image it returns a
    rectangle (x1, y1, x2, y2) expressed in pixel coordinates relative to
    the top-left corner (0,0) of the supplied static background image.

    This design guarantees that, whether the background image came from a
    "full screen capture" or a "background window capture", the returned
    region coordinates always line up exactly with the coordinate system
    the scanning thread will actually use for that frame - no extra window-
    offset math is needed downstream, which avoids region drift when a
    window is moved.
    """
    def __init__(self, parent, source_pil_image, callback):
        super().__init__(parent)
        self.callback = callback
        self.withdraw()

        self.original_pil = source_pil_image.convert("RGB")
        img_w, img_h = self.original_pil.size

        screen_w = max(200, self.winfo_screenwidth() - 120)
        screen_h = max(200, self.winfo_screenheight() - 160)
        self.scale = min(1.0, screen_w / max(1, img_w), screen_h / max(1, img_h))
        disp_w, disp_h = max(1, int(img_w * self.scale)), max(1, int(img_h * self.scale))

        self.display_pil = (self.original_pil.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
                             if self.scale != 1.0 else self.original_pil)

        self.title("Drag to select a dedicated scan region")
        self.attributes('-topmost', True)
        self.resizable(False, False)
        self.configure(cursor="cross", bg="#000000")

        self.tk_dark_img = ImageTk.PhotoImage(ImageEnhance.Brightness(self.display_pil).enhance(0.45))
        self.canvas = tk.Canvas(self, width=disp_w, height=disp_h, highlightthickness=0, cursor="cross")
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.tk_dark_img, anchor="nw")
        self.canvas.create_text(disp_w // 2, 18, text="Drag to select this target's scan region (right-click / Esc to cancel)",
                                 fill=COLOR_ACCENT, font=("Segoe UI", 10, "bold"))

        self.start_x = self.start_y = self.selection_rect_id = self.highlight_img_id = None
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<ButtonPress-3>", self.exit_pick)
        self.bind("<Escape>", self.exit_pick)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (disp_w // 2)
        y = (self.winfo_screenheight() // 2) - (disp_h // 2)
        self.geometry(f"{disp_w}x{disp_h}+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.focus_force()

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.selection_rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline=COLOR_SUCCESS, width=2)

    def on_drag(self, event):
        if self.start_x is None: return
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        self.canvas.coords(self.selection_rect_id, x1, y1, x2, y2)
        if x2 - x1 > 0 and y2 - y1 > 0:
            self.tk_region_img = ImageTk.PhotoImage(self.display_pil.crop((x1, y1, x2, y2)))
            if self.highlight_img_id is None:
                self.highlight_img_id = self.canvas.create_image(x1, y1, image=self.tk_region_img, anchor="nw")
            else:
                self.canvas.coords(self.highlight_img_id, x1, y1)
                self.canvas.itemconfig(self.highlight_img_id, image=self.tk_region_img)
            self.canvas.tag_raise(self.selection_rect_id)

    def on_release(self, event):
        if self.start_x is None: return
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        if (x2 - x1) > 3 and (y2 - y1) > 3:
            inv = (1.0 / self.scale) if self.scale else 1.0
            rx1, ry1 = int(x1 * inv), int(y1 * inv)
            rx2, ry2 = int(x2 * inv), int(y2 * inv)
            self.destroy()
            self.callback((rx1, ry1, rx2, ry2))
        else:
            self.exit_pick()

    def exit_pick(self, event=None):
        self.destroy()
        self.callback(None)

class RadarWidget(tk.Canvas):
    def __init__(self, parent, freq_var, target_label, size=60, bg=COLOR_PANEL):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0)
        self.freq_var, self.target_label = freq_var, target_label
        self.hue, self.size, self.center, self.angle, self.is_active = 0.0, size, size // 2, 0, False
        self.create_oval(5, 5, size-5, size-5, outline="#444", width=1)
        self.create_line(self.center, 5, self.center, size-5, fill="#333")
        self.create_line(5, self.center, size-5, self.center, fill="#333")

    def start(self):
        self.is_active = True
        self.animate()

    def stop(self):
        self.is_active = False
        self.delete("sweep")

    def animate(self):
        if not self.is_active: return
        self.delete("sweep")
        rad = math.radians(self.angle)
        end_x, end_y = self.center + (self.size//2 - 4) * math.cos(rad), self.center + (self.size//2 - 4) * math.sin(rad)
        rgb = colorsys.hls_to_rgb(self.hue, 0.5, 1.0)
        rainbow_hex = "#%02x%02x%02x" % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        self.create_line(self.center, self.center, end_x, end_y, fill=rainbow_hex, width=2, tags="sweep")
        if self.target_label: self.target_label.config(fg=rainbow_hex)
        cycle = max(0.1, self.freq_var.get())
        self.hue = (self.hue + (0.05 / cycle)) % 1.0
        self.angle = (self.angle + (18.0 / cycle)) % 360
        self.after(50, self.animate)

class LockOverlay:
    def __init__(self, x, y, w, h, duration_sec, text_info, stroke_width=3, show_circle=True):
        self.target_w, self.target_h, self.total_duration_sec = w, h, duration_sec
        self.duration_ms = int(duration_sec * 1000)
        self.lock_in_ms, self.hold_ms, self.fade_ms = int(self.duration_ms * 0.15), int(self.duration_ms * 0.70), int(self.duration_ms * 0.15)
        self.padding = max(w, h) + 50
        self.win_w, self.win_h = w + self.padding * 2, h + self.padding * 2
        self.top = tk.Toplevel()
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.geometry(f"{self.win_w}x{self.win_h}+{x - self.padding}+{y - self.padding}")
        self.bg_key = '#000001'
        self.top.configure(bg=self.bg_key)
        if os.name == 'nt': self.top.attributes('-transparentcolor', self.bg_key, '-alpha', 0.85)
        else: self.top.attributes('-alpha', 0.7)
        self.canvas = tk.Canvas(self.top, bg=self.bg_key, width=self.win_w, height=self.win_h, highlightthickness=0)
        self.canvas.pack()
        self.animation_step, self.lock_step_delay = 0, 16
        self.total_anim_steps = max(1, self.lock_in_ms // self.lock_step_delay)
        self.show_circle = show_circle
        self.oval_id = self.canvas.create_oval(0,0,0,0, outline=COLOR_WARN if show_circle else '', width=stroke_width if show_circle else 0)
        self.text_id = self.canvas.create_text(0, 0, text=text_info, font=("Consolas", 11, "bold"), fill=COLOR_WARN, anchor="sw")
        self.hue = 0.0
        self.animate_color()
        self.animate_lock_in()

    def animate_color(self):
        try:
            rgb = colorsys.hls_to_rgb(self.hue, 0.5, 1.0)
            color_hex = "#%02x%02x%02x" % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            if self.show_circle: self.canvas.itemconfig(self.oval_id, outline=color_hex)
            self.canvas.itemconfig(self.text_id, fill=color_hex)
            self.hue = (self.hue + ((0.03 / max(0.1, self.total_duration_sec)) * 2.0)) % 1.0
            if self.top.winfo_exists(): self.top.after(30, self.animate_color)
        except: pass

    def animate_lock_in(self):
        if self.animation_step <= self.total_anim_steps:
            t = self.animation_step / self.total_anim_steps
            current_scale = 3 - (1.4 * (1 - (1 - t) * (1 - t)))
            cur_w, cur_h = self.target_w * current_scale, self.target_h * current_scale
            cx, cy = self.win_w / 2, self.win_h / 2
            if self.show_circle: self.canvas.coords(self.oval_id, cx - cur_w / 2, cy - cur_h / 2, cx + cur_w / 2, cy + cur_h / 2)
            self.canvas.coords(self.text_id, cx - cur_w / 2, cy - cur_h / 2 - 4)
            self.animation_step += 1
            self.top.after(self.lock_step_delay, self.animate_lock_in)
        else: self.top.after(self.hold_ms, self.animate_fade_out)

    def animate_fade_out(self):
        try:
            alpha = self.top.attributes('-alpha')
            if alpha > 0.1:
                self.top.attributes('-alpha', alpha - max(0.02, 1.0 / max(1, self.fade_ms // 30)))
                if self.show_circle:
                    self.canvas.move(self.oval_id, -0.5, -0.5)
                    x1, y1, x2, y2 = self.canvas.coords(self.oval_id)
                    self.canvas.coords(self.oval_id, x1, y1, x2+1, y2+1)
                self.canvas.move(self.text_id, -0.5, -0.5)
                self.top.after(30, self.animate_fade_out)
            else: self.top.destroy()
        except: self.top.destroy()

class DetectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("500x810")
        self.root.resizable(False, False)
        self.root.configure(bg=COLOR_BG)
        pygame.mixer.init()

        self.targets, self.screenshot_counter = [], 0
        self.success_audio_path = self.fail_audio_path = self.last_detect_time = None
        self.last_detect_val = 0.0
        self.is_running = self.is_preview_hidden = False
        self.is_clicking = False  # Prevents overlapping click threads from fighting over the mouse

        self.scan_freq, self.confidence_val = tk.DoubleVar(value=3.0), tk.DoubleVar(value=0.75)
        self.btn_preview_text = tk.StringVar(value="\U0001F441 Hide preview")
        self.enable_sound, self.enable_click, self.enable_fail_sound = tk.BooleanVar(value=True), tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        self.stroke_width, self.allow_multi_target = tk.IntVar(value=5), tk.BooleanVar(value=False)
        self.enable_overlay_circle, self.enable_overlay_text = tk.BooleanVar(value=False), tk.BooleanVar(value=False)

        # --- Background window mode state ---
        self.enable_window_mode = tk.BooleanVar(value=False)
        self.target_hwnds = []  # [{'hwnd':xx, 'title':xx, 'class_name':xx, 'status':'alive', 'miss_count':0}]
        self.strategy_var = tk.StringVar(value="Auto-reconnect")  # Recovery strategy

        self.click_count, self.click_interval = tk.IntVar(value=1), tk.DoubleVar(value=0.1)

        self.setup_styles()
        self.setup_ui()
        self.update_fail_audio_visibility()
        self.on_multi_mode_change()
        self.update_stroke_visibility()
        self.on_win_mode_toggle()
        self.log_msg("PixAlert ready. Add a target image to begin.", "success")
        t_hotkey = threading.Thread(target=self.global_hotkey_loop)
        t_hotkey.daemon = True
        t_hotkey.start()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabelframe", background=COLOR_PANEL, foreground=COLOR_ACCENT, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=COLOR_PANEL, foreground=COLOR_ACCENT, font=("Segoe UI", 10, "bold"))
        style.configure("TFrame", background=COLOR_PANEL)
        style.configure("TButton", background="#333", foreground="white", borderwidth=0, font=("Segoe UI", 9))
        style.map("TButton", background=[('active', COLOR_ACCENT)], foreground=[('active', 'black')])
        style.configure("TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT, font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=COLOR_PANEL, foreground=COLOR_TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[('active', COLOR_PANEL)])

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.main_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.content_panel = tk.Frame(self.main_frame, bg=COLOR_PANEL)
        self.content_panel.pack(fill="both", expand=True)

        header_frame = tk.Frame(self.content_panel, bg=COLOR_PANEL, height=70)
        header_frame.pack(fill="x", padx=15, pady=1)
        tk.Label(header_frame, text="PixAlert", font=("Comic Sans MS", 15, "bold"), bg=COLOR_PANEL, fg=COLOR_ACCENT).pack(side="left", anchor="center")
        tk.Label(header_frame, text="Vision-Click", font=("Segoe UI", 9), bg=COLOR_PANEL, fg=COLOR_DIM).pack(side="left", anchor="s", padx=5, pady=(0,5))
        self.radar = RadarWidget(header_frame, freq_var=self.scan_freq, target_label=None, size=50, bg=COLOR_PANEL)
        self.radar.pack(side="right")
        # Config import/export so the app doesn't need to be reconfigured (targets, sounds, etc.) every launch
        ttk.Button(header_frame, text="\U0001F4C2 Load cfg", width=10, command=self.load_config).pack(side="right", padx=(0, 4))
        ttk.Button(header_frame, text="\U0001F4BE Save cfg", width=10, command=self.save_config).pack(side="right", padx=(0, 8))

        group_img = ttk.LabelFrame(self.content_panel, text=" 1. Target library ", padding=10)
        group_img.pack(fill="x", padx=10, pady=5)
        btn_frame = ttk.Frame(group_img)
        btn_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_frame, text="\u2702 Snip", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="\U0001F4C2 Import (multi)", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="\U0001F5D1 Delete", command=self.delete_selected_target).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, textvariable=self.btn_preview_text, command=self.toggle_preview_visibility).pack(side="left", fill="x", expand=True, padx=(2, 0))

        content_frame = tk.Frame(group_img, bg=COLOR_PANEL)
        content_frame.pack(fill="x", expand=True)
        list_frame = tk.Frame(content_frame, bg=COLOR_PANEL)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.target_listbox = tk.Listbox(list_frame, height=5, bg="#1a1a1a", fg=COLOR_TEXT, selectbackground=COLOR_ACCENT, selectforeground="black", bd=0, highlightthickness=1, highlightbackground="#333", font=("Arial", 9))
        self.target_listbox.pack(side="left", fill="both", expand=True)
        self.target_listbox.bind('<<ListboxSelect>>', self.on_target_select)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.target_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.target_listbox.config(yscrollcommand=scrollbar.set)

        self.context_menu = Menu(self.root, tearoff=0, bg=COLOR_PANEL, fg=COLOR_TEXT)
        self.context_menu.add_command(label="\u270E Rename", command=self.rename_selected_target)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="\U0001F3AF Set scan region", command=self.set_scan_region_for_selected)
        self.context_menu.add_command(label="\u2716 Clear scan region (full screen/window)", command=self.clear_scan_region_for_selected)
        self.target_listbox.bind("<Button-3>", self.show_context_menu)

        self.preview_container = tk.Frame(content_frame, width=160, height=120, bg="#111", relief="solid", borderwidth=1)
        self.preview_container.pack(side="right", fill="none", expand=False)
        self.preview_container.pack_propagate(False)
        self.lbl_preview = tk.Label(self.preview_container, text="No preview", bg="#111", fg="#555")
        self.lbl_preview.pack(fill="both", expand=True)

        group_audio = ttk.LabelFrame(self.content_panel, text=" 2. Trigger actions ", padding=10)
        group_audio.pack(fill="x", padx=10, pady=5)
        action_switch_row = ttk.Frame(group_audio)
        action_switch_row.pack(fill="x", pady=(0, 0))

        checks = [
            ("Match sound", self.enable_sound, None),
            ("AutoClick", self.enable_click, self.toggle_click_settings),
            ("No-match sound", self.enable_fail_sound, self.update_fail_audio_visibility),
            ("Duplicates", self.allow_multi_target, self.on_multi_mode_change),
            ("Draw Circle", self.enable_overlay_circle, self.update_stroke_visibility),
            ("Show confidence", self.enable_overlay_text, None),
        ]

        for i, (text, var, cmd) in enumerate(checks):
            cb = ttk.Checkbutton(
                action_switch_row,
                text=text,
                variable=var,
                command=cmd
            )
            cb.grid(
                row=i // 4,
                column=i % 4,
                sticky="w",
                padx=5,
                pady=2
            )

        self.click_settings_frame = tk.Frame(group_audio, bg=COLOR_PANEL)
        click_params_row = ttk.Frame(self.click_settings_frame)
        click_params_row.pack(fill="x", pady=2)
        ttk.Label(click_params_row, text="Click count:").pack(side="left")
        ttk.Spinbox(click_params_row, from_=1, to=50, textvariable=self.click_count, width=3, state="readonly").pack(side="left", padx=(2, 15))
        ttk.Label(click_params_row, text="Click interval (s):").pack(side="left")
        ttk.Spinbox(click_params_row, from_=0.00, to=5.00, increment=0.01, format="%.2f", textvariable=self.click_interval, width=5, state="readonly").pack(side="left", padx=2)

        audio_row = ttk.Frame(group_audio)
        audio_row.pack(fill="x", pady=(8,0))
        self.lbl_audio_name = ttk.Label(audio_row, text="Match sound: default", width=25, anchor="w", foreground=COLOR_SUCCESS)
        self.lbl_audio_name.pack(side="left")
        ttk.Button(audio_row, text="Choose sound...", command=self.load_success_audio, width=12).pack(side="right")
        self.fail_audio_row = ttk.Frame(group_audio)
        self.fail_audio_row.pack(fill="x", pady=(5,0))
        self.lbl_fail_audio_name = ttk.Label(self.fail_audio_row, text="No-match sound: default", width=25, anchor="w", foreground=COLOR_WARN)
        self.lbl_fail_audio_name.pack(side="left")
        ttk.Button(self.fail_audio_row, text="Choose sound...", command=self.load_fail_audio, width=12).pack(side="right")

        group_settings = ttk.LabelFrame(self.content_panel, text=" 3. Settings ", padding=10)
        group_settings.pack(fill="x", padx=10, pady=5)

        win_mode_row = ttk.Frame(group_settings)
        win_mode_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(win_mode_row, text="Background window mode", variable=self.enable_window_mode, command=self.on_win_mode_toggle).pack(side="left", padx=(0, 10))
        self.btn_select_wins = ttk.Button(win_mode_row, text="Select windows (0)", width=10, command=self.open_window_selector)
        self.btn_clear_wins = ttk.Button(win_mode_row, text="\u21BA Reset selection", command=self.clear_window_selection)
        self.btn_check_alive = ttk.Button(win_mode_row, text="\U0001F50D Check/reconnect", command=self.manual_check_alive)
        self.cb_strategy = ttk.Combobox(win_mode_row, textvariable=self.strategy_var, values=["Auto-reconnect", "Auto-drop"], state="readonly", width=12, font=("Segoe UI", 8))

        f_row = ttk.Frame(group_settings)
        f_row.pack(fill="x", pady=2)
        ttk.Label(f_row, text="Scan interval (s):", width=14).pack(side="left")
        ttk.Scale(f_row, from_=0.1, to=10.0, variable=self.scan_freq, orient="horizontal", length=220).pack(side="left", padx=10)
        self.lbl_freq_val = ttk.Label(f_row,text=f"{self.scan_freq.get():.1f} s", width=6, font=("Consolas", 10, "bold"), foreground=COLOR_ACCENT)
        self.lbl_freq_val.pack(side="left")
        self.scan_freq.trace_add("write", lambda *args: self.lbl_freq_val.config(text=f"{self.scan_freq.get():.1f} s"))

        c_row = ttk.Frame(group_settings)
        c_row.pack(fill="x", pady=2)
        ttk.Label(c_row, text="Match threshold:", width=14).pack(side="left")
        ttk.Scale(c_row, from_=0.5, to=0.99, variable=self.confidence_val, orient="horizontal", length=220).pack(side="left", padx=10)
        self.lbl_conf_val = ttk.Label(c_row,text=f"{self.confidence_val.get():.2f}", width=6, font=("Consolas", 10, "bold"), foreground=COLOR_ACCENT)
        self.lbl_conf_val.pack(side="left")
        self.confidence_val.trace_add("write", lambda *args: self.lbl_conf_val.config(text=f"{self.confidence_val.get():.2f}"))

        self.stroke_row = ttk.Frame(group_settings)
        self.stroke_row.pack(fill="x", pady=2)
        ttk.Label(self.stroke_row, text="Stroke width:", width=14).pack(side="left")
        ttk.Scale(self.stroke_row, from_=1, to=10, variable=self.stroke_width, orient="horizontal", length=220).pack(side="left", padx=10)
        self.lbl_stroke_val = ttk.Label(self.stroke_row, text=f"{self.stroke_width.get()}", width=3, font=("Consolas", 10, "bold"), foreground=COLOR_ACCENT)
        self.lbl_stroke_val.pack(side="left")
        self.stroke_width.trace_add("write", lambda *args: self.lbl_stroke_val.config(text=f"{self.stroke_width.get()}"))

        group_log = ttk.LabelFrame(self.content_panel, text=" Event log ", padding=1)
        group_log.pack(fill="both", expand=True, pady=5, padx=10)
        log_ctrl_frame = tk.Frame(group_log, bg=COLOR_PANEL)
        log_ctrl_frame.pack(fill="x", side="bottom")
        tk.Button(log_ctrl_frame, text="Copy all", command=self.copy_log_to_clipboard, bg="#333", fg="#888", relief="flat", font=("Arial", 8)).pack(side="right", padx=(5, 0))
        tk.Button(log_ctrl_frame, text="Clear log", command=self.clear_log, bg="#333", fg="#888", relief="flat", font=("Arial", 8)).pack(side="right")
        self.log_text = scrolledtext.ScrolledText(group_log, height=1, state='disabled', font=("Consolas", 9), bg="#111", fg="#aaa", bd=0)
        self.log_text.pack(fill="both", expand=True, side="top", padx=2, pady=2)
        self.log_text.tag_config("success", foreground=COLOR_SUCCESS, font=("Consolas", 9, "bold"))
        self.log_text.tag_config("fail", foreground=COLOR_WARN, font=("Consolas", 9, "bold"))
        self.log_text.tag_config("warn", foreground="#FFC107")

        self.btn_control = tk.Button(self.content_panel, text="Start scan", command=self.toggle_detection, bg=COLOR_ACCENT, fg="black", font=("Segoe UI", 12, "bold"), relief="flat", activebackground="white", activeforeground="black", cursor="hand2")
        self.btn_control.pack(fill="x", pady=(5, 0), padx=10, ipady=5)
        self.status_bar = tk.Label(self.content_panel, text="Ready", bd=1, relief="flat", anchor="w", bg="#333", fg="white", padx=5, font=("Segoe UI", 9))
        self.status_bar.pack(side="bottom", fill="x", pady=(5,0))

    def on_win_mode_toggle(self):
        if self.enable_window_mode.get():
            self.btn_select_wins.pack(side="left")
            self.btn_clear_wins.pack(side="left", padx=(5, 0))
            self.btn_check_alive.pack(side="left", padx=(5, 0))
            self.cb_strategy.pack(side="left", padx=(5, 0))
            self.enable_click.set(False)
            self.toggle_click_settings()
            if hasattr(self, 'chk_click'): self.chk_click.config(state="disabled")
        else:
            self.btn_select_wins.pack_forget()
            self.btn_clear_wins.pack_forget()
            self.btn_check_alive.pack_forget()
            self.cb_strategy.pack_forget()
            if not self.allow_multi_target.get() and hasattr(self, 'chk_click'):
                self.chk_click.config(state="normal")

    def clear_window_selection(self):
        if self.target_hwnds:
            self.target_hwnds.clear()
            self.btn_select_wins.config(text="Select windows (0)")
            self.log_msg("Target window selection cleared.")

    def manual_check_alive(self):
        if not self.target_hwnds: return self.log_msg("No windows selected, nothing to check.")
        self.log_msg("[Manual check] Analyzing window status...")
        reconnect_count, alive_count = 0, 0
        for item in self.target_hwnds:
            if win32gui.IsWindow(item['hwnd']):
                item['status'], item['miss_count'] = 'alive', 0
                alive_count += 1
            else:
                new_hwnd = 0
                while True:
                    new_hwnd = win32gui.FindWindowEx(0, new_hwnd, item['class_name'], item['title'])
                    if not new_hwnd or (win32gui.IsWindowVisible(new_hwnd) and not any(t['hwnd'] == new_hwnd and t['status'] == 'alive' for t in self.target_hwnds if t != item)):
                        break

                if new_hwnd:
                    item['hwnd'], item['status'], item['miss_count'] = new_hwnd, 'alive', 0
                    reconnect_count += 1
                    self.log_msg(f"  [>] Recovered: {item['title']}", "success")
                else:
                    item['status'] = 'lost'
                    self.log_msg(f"  [X] Still lost: {item['title']}", "warn")
        total = len(self.target_hwnds)
        self.log_msg(f"[Manual check] Total:{total} | Alive:{alive_count+reconnect_count} | Lost:{total-alive_count-reconnect_count}", "success" if alive_count+reconnect_count>0 else "warn")

    def open_window_selector(self):
        win = tk.Toplevel(self.root)
        win.title("Select target windows (multi-select)")
        self.root.update_idletasks()
        win.geometry(f"500x350+{self.root.winfo_x()+self.root.winfo_width()//2-250}+{self.root.winfo_y()+self.root.winfo_height()//2-175}")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=COLOR_BG)
        tk.Label(win, text="Select one or more windows to monitor in the background:", bg=COLOR_BG, fg=COLOR_TEXT).pack(pady=5)
        list_frame = tk.Frame(win, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, bg="#1a1a1a", fg=COLOR_TEXT, selectbackground=COLOR_ACCENT, selectforeground="black", yscrollcommand=scrollbar.set, font=("Segoe UI", 9))
        scrollbar.config(command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        hwnds_data = []
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title: hwnds_data.append((hwnd, title, win32gui.GetClassName(hwnd)))
        win32gui.EnumWindows(callback, None)

        for hwnd, title, cls in hwnds_data: listbox.insert(tk.END, f"[{hex(hwnd)}] {title}")

        def confirm():
            if listbox.curselection():
                self.target_hwnds = [{'hwnd': hwnds_data[i][0], 'title': hwnds_data[i][1], 'class_name': hwnds_data[i][2], 'status': 'alive', 'miss_count': 0} for i in listbox.curselection()]
                self.btn_select_wins.config(text=f"Select windows ({len(self.target_hwnds)})")
                self.log_msg(f"Selected {len(self.target_hwnds)} target window(s)")
            win.destroy()
        ttk.Button(win, text="Confirm", command=confirm).pack(pady=10)

    def wake_up_silently(self, hwnd):
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            time.sleep(0.1)

    def get_render_child_hwnd(self, parent_hwnd):
        child_hwnds = []
        try: win32gui.EnumChildWindows(parent_hwnd, lambda h, _: child_hwnds.append(h) or True, None)
        except Exception: pass
        best_child, max_area = parent_hwnd, 0
        for ch in child_hwnds:
            l, t, r, b = win32gui.GetWindowRect(ch)
            if (r - l) * (b - t) > max_area:
                max_area = (r - l) * (b - t)
                best_child = ch
        return best_child

    def capture_bg_window(self, hwnd):
        """Capture a window's client area via PrintWindow, so it can be
        scanned even if it's covered by other windows or not focused."""
        l, t, r, b = win32gui.GetClientRect(hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0: return None
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)
        img = None
        if ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3) == 1:
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype=np.uint8).copy()
            img.shape = (saveBitMap.GetInfo()['bmHeight'], saveBitMap.GetInfo()['bmWidth'], 4)
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        return img

    def global_hotkey_loop(self):
        """Background thread: listens for the Ctrl+Q hotkey to stop scanning."""
        while True:
            if (ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000) and (ctypes.windll.user32.GetAsyncKeyState(0x51) & 0x8000):
                if self.is_running:
                    self.root.after(0, self.toggle_detection)
                    time.sleep(0.5)
            time.sleep(0.05)

    def on_multi_mode_change(self, *args):
        if self.allow_multi_target.get():
            self.enable_click.set(False)
            self.toggle_click_settings()
            if hasattr(self, 'chk_click'): self.chk_click.config(state='disabled')
        elif not self.enable_window_mode.get():
            if hasattr(self, 'chk_click'): self.chk_click.config(state='normal')

    def toggle_click_settings(self):
        if self.enable_click.get(): self.click_settings_frame.pack(fill="x", pady=(5, 0), after=self.chk_click.master)
        else: self.click_settings_frame.pack_forget()

    def update_stroke_visibility(self):
        if self.enable_overlay_circle.get(): self.stroke_row.pack(fill="x", pady=5)
        else: self.stroke_row.pack_forget()

    def update_fail_audio_visibility(self):
        if self.enable_fail_sound.get(): self.fail_audio_row.pack(fill="x", pady=(5, 0))
        else: self.fail_audio_row.pack_forget()

    def log_msg(self, msg, tag=None):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def copy_log_to_clipboard(self):
        log_content = self.log_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        self.log_msg("Log copied to clipboard.", "success")

    def _target_to_config_dict(self, target, images_dir, idx):
        """Serialize a single target to a JSON-friendly dict, saving its image as a PNG file."""
        file_name = f"target_{idx + 1:03d}.png"
        try:
            ok, buf = cv2.imencode(".png", target['image'])
            if ok:
                buf.tofile(os.path.join(images_dir, file_name))
            else:
                raise IOError("cv2.imencode failed")
        except Exception as e:
            self.log_msg(f"Failed to export target image [{target['name']}]: {e}", "fail")
            file_name = None
        return {
            "name": target['name'],
            "image_file": file_name,
            "region": list(target['region']) if target.get('region') else None,
        }

    def save_config(self):
        """Export the current target library, sound paths and scan parameters as a JSON config file (including target images)."""
        path = filedialog.asksaveasfilename(
            title="Save config",
            defaultextension=".json",
            filetypes=[("Config file", "*.json")],
            initialfile="my_config.json",
        )
        if not path:
            return
        try:
            base_dir = os.path.dirname(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            images_dir = os.path.join(base_dir, f"{base_name}_images")
            os.makedirs(images_dir, exist_ok=True)

            cfg = {
                "config_schema_version": CONFIG_SCHEMA_VERSION,
                "app_title": APP_TITLE,
                "settings": {
                    "scan_freq": self.scan_freq.get(),
                    "confidence_val": self.confidence_val.get(),
                    "enable_sound": self.enable_sound.get(),
                    "enable_click": self.enable_click.get(),
                    "enable_fail_sound": self.enable_fail_sound.get(),
                    "allow_multi_target": self.allow_multi_target.get(),
                    "enable_overlay_circle": self.enable_overlay_circle.get(),
                    "enable_overlay_text": self.enable_overlay_text.get(),
                    "stroke_width": self.stroke_width.get(),
                    "click_count": self.click_count.get(),
                    "click_interval": self.click_interval.get(),
                    "enable_window_mode": self.enable_window_mode.get(),
                    "strategy": self.strategy_var.get(),
                },
                "audio": {
                    "success_audio_path": self.success_audio_path,
                    "fail_audio_path": self.fail_audio_path,
                },
                "windows": [
                    {"title": it['title'], "class_name": it['class_name']} for it in self.target_hwnds
                ],
                "targets": [self._target_to_config_dict(t, images_dir, i) for i, t in enumerate(self.targets)],
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            self.log_msg(f"Config exported: {path}", "success")
            messagebox.showinfo("Saved", f"Config file:\n{path}\n\nTarget images saved to:\n{images_dir}", parent=self.root)
        except Exception as e:
            self.log_msg(f"Failed to export config: {e}", "fail")
            messagebox.showerror("Error", f"Failed to export config:\n{e}", parent=self.root)

    def load_config(self):
        """Restore the target library, sound paths and scan parameters from a JSON config file."""
        path = filedialog.askopenfilename(title="Load config", filetypes=[("Config file", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read config file:\n{e}", parent=self.root)
            return

        if self.is_running:
            self.toggle_detection()

        base_dir = os.path.dirname(path)
        base_name = os.path.splitext(os.path.basename(path))[0]
        images_dir = os.path.join(base_dir, f"{base_name}_images")

        s = cfg.get("settings", {})
        self.scan_freq.set(s.get("scan_freq", self.scan_freq.get()))
        self.confidence_val.set(s.get("confidence_val", self.confidence_val.get()))
        self.enable_sound.set(s.get("enable_sound", self.enable_sound.get()))
        self.enable_click.set(s.get("enable_click", self.enable_click.get()))
        self.enable_fail_sound.set(s.get("enable_fail_sound", self.enable_fail_sound.get()))
        self.allow_multi_target.set(s.get("allow_multi_target", self.allow_multi_target.get()))
        self.enable_overlay_circle.set(s.get("enable_overlay_circle", self.enable_overlay_circle.get()))
        self.enable_overlay_text.set(s.get("enable_overlay_text", self.enable_overlay_text.get()))
        self.stroke_width.set(s.get("stroke_width", self.stroke_width.get()))
        self.click_count.set(s.get("click_count", self.click_count.get()))
        self.click_interval.set(s.get("click_interval", self.click_interval.get()))
        self.strategy_var.set(s.get("strategy", self.strategy_var.get()))

        a = cfg.get("audio", {})
        sp, fp = a.get("success_audio_path"), a.get("fail_audio_path")
        if sp and os.path.exists(sp):
            self.success_audio_path = sp
            self.lbl_audio_name.config(text=f"Match sound: {os.path.basename(sp)}")
        elif sp:
            self.log_msg(f"Warning: match sound file not found -> {sp}", "warn")
        if fp and os.path.exists(fp):
            self.fail_audio_path = fp
            self.lbl_fail_audio_name.config(text=f"No-match sound: {os.path.basename(fp)}")
        elif fp:
            self.log_msg(f"Warning: no-match sound file not found -> {fp}", "warn")

        # Rebuild the target library
        self.targets.clear()
        missing_imgs = 0
        for i, td in enumerate(cfg.get("targets", [])):
            img_file = td.get("image_file")
            img = None
            if img_file:
                img_path = os.path.join(images_dir, img_file)
                if os.path.exists(img_path):
                    try:
                        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
                    except Exception:
                        img = None
            if img is None:
                missing_imgs += 1
                continue
            im_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            im_pil.thumbnail((160, 140), Image.Resampling.LANCZOS)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            region = tuple(td["region"]) if td.get("region") else None
            self.targets.append({
                'name': td.get("name", f"Target {i + 1}"), 'image': img, 'gray': gray,
                'preview': ImageTk.PhotoImage(im_pil), 'h': gray.shape[0], 'w': gray.shape[1],
                'region': region,
            })
        self.refresh_target_listbox()
        if self.targets:
            self.target_listbox.selection_set(0)
            self.on_target_select(None)
        else:
            self.lbl_preview.config(image="", text="No preview")

        # Background window mode: try to re-find windows by title/class
        # (handles can't be persisted, since they're invalidated on restart)
        self.target_hwnds = []
        win_list = cfg.get("windows", [])
        found_count = 0
        for w in win_list:
            try:
                hwnd = win32gui.FindWindowEx(0, 0, w.get("class_name") or None, w.get("title") or None)
            except Exception:
                hwnd = 0
            if hwnd:
                self.target_hwnds.append({'hwnd': hwnd, 'title': w.get("title"), 'class_name': w.get("class_name"), 'status': 'alive', 'miss_count': 0})
                found_count += 1
        self.btn_select_wins.config(text=f"Select windows ({len(self.target_hwnds)})")

        self.enable_window_mode.set(s.get("enable_window_mode", False))
        self.on_win_mode_toggle()
        self.on_multi_mode_change()
        self.toggle_click_settings()
        self.update_fail_audio_visibility()
        self.update_stroke_visibility()

        if missing_imgs:
            self.log_msg(f"Warning: {missing_imgs} target image(s) missing or corrupted (don't delete the {base_name}_images folder)", "warn")
        if win_list:
            self.log_msg(f"Background windows recovered: {found_count}/{len(win_list)} (re-select any that weren't found)", "success" if found_count else "warn")
        self.log_msg(f"Config loaded: {path}", "success")
        messagebox.showinfo("Loaded", f"Config loaded!\nTargets: {len(self.targets)}\nWindows recovered: {found_count}/{len(win_list)}", parent=self.root)

    def start_snipping(self):
        self.root.iconify()
        self.root.after(200, lambda: SnippingTool(self.root, lambda img: self.add_target(img, is_screenshot=True)))

    def load_image_file(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if file_paths:
            count = 0
            for path in file_paths:
                try:
                    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        self.add_target(img, name=os.path.basename(path), is_screenshot=False)
                        count += 1
                except: pass
            self.log_msg(f"Batch import complete: {count} image(s)")

    def add_target(self, img, name=None, is_screenshot=False):
        self.root.deiconify()
        if img is None: return
        final_name = f"Snip {self.screenshot_counter + 1}" if is_screenshot else (name if name else "Imported image")
        if is_screenshot: self.screenshot_counter += 1
        im_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        im_pil.thumbnail((160, 140), Image.Resampling.LANCZOS)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        self.targets.append({'name': final_name, 'image': img, 'gray': gray, 'preview': ImageTk.PhotoImage(im_pil), 'h': gray.shape[0], 'w': gray.shape[1], 'region': None})
        self.refresh_target_listbox()
        self.target_listbox.selection_clear(0, tk.END)
        self.target_listbox.selection_set(tk.END)
        self.on_target_select(None)
        self.log_msg(f"Added: {final_name}")

    def refresh_target_listbox(self):
        self.target_listbox.delete(0, tk.END)
        for i, t in enumerate(self.targets):
            has_region = bool(t.get('region'))
            tag = " \U0001F3AF[region]" if has_region else ""
            self.target_listbox.insert(tk.END, f"{i+1}. {t['name']} ({t['w']}x{t['h']}){tag}")
            # Targets with a dedicated scan region are shown in green
            self.target_listbox.itemconfig(i, fg=COLOR_SUCCESS if has_region else COLOR_TEXT)
        self.status_bar.config(text=f"Targets in library: {len(self.targets)}")

    def delete_selected_target(self):
        selection = self.target_listbox.curselection()
        if not selection: return
        removed_name = self.targets.pop(selection[0])['name']
        self.refresh_target_listbox()
        self.log_msg(f"Deleted: {removed_name}")
        if self.targets:
            self.target_listbox.selection_set(min(selection[0], len(self.targets) - 1))
            self.on_target_select(None)
        else:
            self.lbl_preview.config(image="", text="No preview")
            if self.is_running: self.toggle_detection()

    def show_context_menu(self, event):
        try:
            self.target_listbox.selection_clear(0, tk.END)
            self.target_listbox.selection_set(self.target_listbox.nearest(event.y))
            self.on_target_select(None)
            self.context_menu.post(event.x_root, event.y_root)
        except Exception: pass

    def rename_selected_target(self):
        if not self.target_listbox.curselection(): return
        index = self.target_listbox.curselection()[0]
        new_name = simpledialog.askstring("Rename", "Enter a new name:", initialvalue=self.targets[index]['name'], parent=self.root)
        if new_name and new_name.strip():
            self.log_msg(f"Renamed [{self.targets[index]['name']}] -> [{new_name.strip()}]")
            self.targets[index]['name'] = new_name.strip()
            self.refresh_target_listbox()
            self.target_listbox.selection_set(index)

    def set_scan_region_for_selected(self):
        """
        Let the user draw a dedicated scan region for the selected target.
        To keep the picked rectangle aligned with the exact frame the scan
        thread will use (avoiding drift if a window moves), this prefers
        the live background-window frame as the picker's backdrop; if
        background mode isn't on or no window is available, it falls back
        to a single full-screen capture (in which case the region
        coordinates are plain screen coordinates).
        """
        selection = self.target_listbox.curselection()
        if not selection:
            return messagebox.showwarning("Notice", "Select a target in the list first.")
        index = selection[0]

        if self.is_running:
            return messagebox.showwarning("Notice", "Stop scanning before setting a scan region.")

        self.root.iconify()

        def do_capture_and_pick():
            frame_img = None
            # Prefer the live background window frame as the backdrop
            if self.enable_window_mode.get() and self.target_hwnds:
                alive_item = next((it for it in self.target_hwnds if win32gui.IsWindow(it['hwnd'])), None)
                if alive_item:
                    try:
                        self.wake_up_silently(alive_item['hwnd'])
                        raw = self.capture_bg_window(self.get_render_child_hwnd(alive_item['hwnd']))
                        if raw is not None and np.mean(raw) >= 2.0:
                            frame_img = Image.fromarray(cv2.cvtColor(raw, cv2.COLOR_BGRA2RGB))
                    except Exception:
                        frame_img = None

            # Fallback: use a full-screen capture as the backdrop
            if frame_img is None:
                try:
                    with mss.mss() as sct:
                        shot = sct.grab(sct.monitors[0])
                        frame_img = Image.fromarray(cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2RGB))
                except Exception as e:
                    self.root.deiconify()
                    return messagebox.showerror("Error", f"Failed to capture a frame, can't select a region:\n{e}", parent=self.root)

            def on_region_selected(rect):
                self.root.deiconify()
                if rect and index < len(self.targets):
                    x1, y1, x2, y2 = rect
                    t = self.targets[index]
                    if (x2 - x1) < t['w'] or (y2 - y1) < t['h']:
                        messagebox.showwarning("Notice", "The selected region is smaller than the target image itself; setting rejected. Please select a larger region.", parent=self.root)
                        self.log_msg(f"[{t['name']}] Failed to set region: selection smaller than target size.", "warn")
                        return
                    t['region'] = (x1, y1, x2, y2)
                    self.log_msg(f"[{t['name']}] Scan region set: ({x1},{y1}) - ({x2},{y2}), CPU load reduced", "success")
                else:
                    self.log_msg("Region selection cancelled.")
                self.refresh_target_listbox()
                self.target_listbox.selection_set(index)

            RegionPickerTool(self.root, frame_img, on_region_selected)

        self.root.after(250, do_capture_and_pick)

    def clear_scan_region_for_selected(self):
        """Clear the selected target's dedicated scan region, reverting to full screen/window scanning."""
        selection = self.target_listbox.curselection()
        if not selection:
            return messagebox.showwarning("Notice", "Select a target in the list first.")
        index = selection[0]
        t = self.targets[index]
        if not t.get('region'):
            return self.log_msg(f"[{t['name']}] No dedicated region set, nothing to clear.")
        t['region'] = None
        self.log_msg(f"[{t['name']}] Scan region cleared, reverted to full screen/window scanning.")
        self.refresh_target_listbox()
        self.target_listbox.selection_set(index)

    def on_target_select(self, event):
        if not self.target_listbox.curselection(): return
        if self.is_preview_hidden: self.lbl_preview.config(image="", text="[ Preview hidden ]", fg="#666")
        else: self.lbl_preview.config(image=self.targets[self.target_listbox.curselection()[0]]['preview'], text="")

    def toggle_preview_visibility(self):
        if not self.targets: return
        self.is_preview_hidden = not self.is_preview_hidden
        self.btn_preview_text.set("\U0001F441 Show preview" if self.is_preview_hidden else "\U0001F441 Hide preview")
        self.on_target_select(None)

    def load_success_audio(self):
        if path := filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3;*.wav")]):
            self.success_audio_path = path
            self.lbl_audio_name.config(text=f"Match sound: {os.path.basename(path)}")

    def load_fail_audio(self):
        if path := filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3;*.wav")]):
            self.fail_audio_path = path
            self.lbl_fail_audio_name.config(text=f"No-match sound: {os.path.basename(path)}")

    def play_sound(self, is_success=True):
        try:
            target_path = self.success_audio_path if is_success else self.fail_audio_path
            if target_path:
                pygame.mixer.music.load(target_path)
                pygame.mixer.music.play()
            elif os.name == 'nt':
                import winsound
                winsound.Beep(1000 if is_success else 500, 200)
        except Exception: pass

    def perform_click(self, monitor, match_loc, h, w, count, interval, custom_offset=None):
        # If a previous click sequence is still running, skip this one
        # avoids two threads fighting over the mouse cursor
        if getattr(self, 'is_clicking', False):
            return None

        def click_task():
            self.is_clicking = True
            try:
                offset_x = custom_offset[0] if custom_offset else monitor['left']
                offset_y = custom_offset[1] if custom_offset else monitor['top']
                center_x, center_y = offset_x + match_loc[0] + w // 2, offset_y + match_loc[1] + h // 2

                for i in range(count):
                    # Stop immediately if the user clicked "Stop scan"
                    if not self.is_running:
                        break

                    pyautogui.moveTo(center_x, center_y)
                    pyautogui.mouseDown()
                    time.sleep(0.005)
                    pyautogui.mouseUp()

                    if i < count - 1:
                        time.sleep(interval)
            except Exception:
                pass
            finally:
                # Always release the lock, whether the click succeeded or errored
                self.is_clicking = False

        threading.Thread(target=click_task, daemon=True).start()
        return None

    def trigger_visual_alert(self):
        total_ms = max(90, int(self.scan_freq.get() * 1000 * 0.2))
        step = total_ms // 3
        def set_bg(c):
            try: self.root.configure(bg=c); self.main_frame.configure(bg=c)
            except: pass
        self.root.after(0, lambda: set_bg("#FF3333"))
        self.root.after(step, lambda: set_bg("#33FF33"))
        self.root.after(step*2, lambda: set_bg("#3333FF"))
        self.root.after(total_ms, lambda: set_bg(COLOR_BG))

    def set_status_persistent(self, text, bg_color, fg_color):
        self.root.after(0, lambda: self.status_bar.config(text=text, bg=bg_color, fg=fg_color))

    def toggle_detection(self):
        if self.is_running:
            self.is_running = False
            self.btn_control.config(text="Start scan", bg=COLOR_ACCENT, fg="black")
            self.status_bar.config(text="Scan stopped", bg="#333", fg="white")
            self.log_msg("Scan stopped.")
            self.radar.stop()
            pygame.mixer.music.stop()
            if self.enable_window_mode.get():
                self.btn_select_wins.config(state="normal")
                self.btn_clear_wins.config(state="normal")
                self.cb_strategy.config(state="readonly")
        else:
            if not self.targets: return messagebox.showwarning("Error", "The target library is empty. Add at least one target first.")
            if self.enable_window_mode.get() and not self.target_hwnds: return messagebox.showwarning("Error", "Background window mode is on, but no target window is selected.")

            self.is_running = True
            self.btn_control.config(text="\U0001F6D1 Stop (Ctrl+Q)", bg=COLOR_WARN, fg="white")
            self.log_msg(f"Scan started [{'Background window' if self.enable_window_mode.get() else 'Full screen'}] - threshold: {self.confidence_val.get()}")
            self.radar.start()
            if self.enable_window_mode.get():
                self.btn_select_wins.config(state="disabled")
                self.btn_clear_wins.config(state="disabled")
                self.cb_strategy.config(state="disabled")
            threading.Thread(target=self.loop_detection, daemon=True).start()

    def _apply_region(self, gray_frame, target):
# Region-scan core. If the target has a dedicated scan region, crop to just that region before template matching (this substantially reduces the cv2.matchTemplate workload, lowering CPU load and heat); otherwise return the full frame unchanged (i.e. full screen/window scanning, matching the original behavior). Returns (grayscale image to match against, top-left offset of the region relative to the full frame (ox, oy)) - the offset is used to convert match coordinates back into full-frame coordinates.
        region = target.get('region')
        if not region:
            return gray_frame, (0, 0)
        fh, fw = gray_frame.shape[:2]
        x1, y1, x2, y2 = region
        x1, y1 = max(0, min(int(x1), fw - 1)), max(0, min(int(y1), fh - 1))
        x2, y2 = max(x1 + 1, min(int(x2), fw)), max(y1 + 1, min(int(y2), fh))
        # If the region is smaller than the target itself (e.g. the window was resized), matching inside it is impossible - fall back safely to scanning the full frame.
        if (x2 - x1) < target['w'] or (y2 - y1) < target['h']:
            return gray_frame, (0, 0)
        return gray_frame[y1:y2, x1:x2], (x1, y1)

    def loop_detection(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            while self.is_running:
                start_ts, freq, current_targets = time.time(), self.scan_freq.get(), list(self.targets)
                if not current_targets:
                    time.sleep(1)
                    continue

                found_matches, frame_max_val = [], 0.0
                confidence_threshold = self.confidence_val.get()

                if not self.enable_window_mode.get():
                    screen_gray = cv2.cvtColor(np.array(sct.grab(monitor)), cv2.COLOR_BGRA2GRAY)
                    for t in current_targets:
                        try:
                            # Region scan: if the target has a dedicated region, only match within it to reduce CPU load
                            region_frame, (rox, roy) = self._apply_region(screen_gray, t)
                            res = cv2.matchTemplate(region_frame, t['gray'], cv2.TM_CCOEFF_NORMED)
                            if self.allow_multi_target.get():
                                _, g_max_val, _, _ = cv2.minMaxLoc(res)
                                if g_max_val > frame_max_val: frame_max_val = g_max_val
                                detected = []
                                for local_pt in list(zip(*np.where(res >= confidence_threshold)[::-1])):
                                    val = float(res[local_pt[1], local_pt[0]])
                                    pt = (local_pt[0] + rox, local_pt[1] + roy)
                                    c_x, c_y = pt[0] + t['w']//2, pt[1] + t['h']//2
                                    if not any(math.hypot(c_x - ox, c_y - oy) < t['w'] / 2 for ox, oy in detected):
                                        detected.append((c_x, c_y))
                                        found_matches.append({'name': t['name'], 'val': val, 'loc': pt, 'h': t['h'], 'w': t['w']})
                            else:
                                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                                if max_val > frame_max_val: frame_max_val = max_val
                                if max_val >= confidence_threshold:
                                    abs_loc = (max_loc[0] + rox, max_loc[1] + roy)
                                    found_matches.append({'name': t['name'], 'val': max_val, 'loc': abs_loc, 'h': t['h'], 'w': t['w']})
                        except Exception: pass
                else:
                    updated_hwnds = []
                    strategy = self.strategy_var.get()

                    for item in self.target_hwnds:
                        hwnd = item['hwnd']
                        if win32gui.IsWindow(hwnd):
                            item['status'], item['miss_count'] = 'alive', 0
                            updated_hwnds.append(item)
                        else:
                            if item['status'] != 'lost':
                                item['status'] = 'lost'
                                self.root.after(0, lambda t=item['title']: self.log_msg(f"Window lost: {t}, searching quietly...", "warn"))

                            new_hwnd = 0
                            while True:
                                new_hwnd = win32gui.FindWindowEx(0, new_hwnd, item['class_name'], item['title'])
                                if not new_hwnd or (win32gui.IsWindowVisible(new_hwnd) and not any(t['hwnd'] == new_hwnd for t in updated_hwnds)):
                                    break

                            if new_hwnd and new_hwnd != hwnd:
                                item['hwnd'], item['status'], item['miss_count'] = new_hwnd, 'alive', 0
                                self.root.after(0, lambda t=item['title']: self.log_msg(f"Reconnected: {t}", "success"))
                                updated_hwnds.append(item)
                                hwnd = new_hwnd
                            else:
                                item['miss_count'] += 1
                                if strategy == "Auto-drop" and item['miss_count'] >= 5:
                                    self.root.after(0, lambda t=item['title']: self.log_msg(f"[{t}] Failed to recover 5 times in a row, dropping it permanently.", "fail"))
                                    continue
                                updated_hwnds.append(item)
                                continue

                        self.wake_up_silently(hwnd)
                        img = self.capture_bg_window(self.get_render_child_hwnd(hwnd))
                        if img is None or np.mean(img) < 2.0: continue
                        win_offset_x, win_offset_y = win32gui.ClientToScreen(self.get_render_child_hwnd(hwnd), (0, 0))
                        screen_gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

                        for t in current_targets:
                            try:
                                region_frame, (rox, roy) = self._apply_region(screen_gray, t)
                                res = cv2.matchTemplate(region_frame, t['gray'], cv2.TM_CCOEFF_NORMED)
                                if self.allow_multi_target.get():
                                    _, g_max_val, _, _ = cv2.minMaxLoc(res)
                                    if g_max_val > frame_max_val: frame_max_val = g_max_val
                                    detected = []
                                    for local_pt in list(zip(*np.where(res >= confidence_threshold)[::-1])):
                                        val = float(res[local_pt[1], local_pt[0]])
                                        pt = (local_pt[0] + rox, local_pt[1] + roy)
                                        c_x, c_y = pt[0] + t['w']//2, pt[1] + t['h']//2
                                        if not any(math.hypot(c_x - ox, c_y - oy) < t['w'] / 2 for ox, oy in detected):
                                            detected.append((c_x, c_y))
                                            found_matches.append({'name': t['name'], 'val': val, 'loc': pt, 'h': t['h'], 'w': t['w'], 'offset_x': win_offset_x, 'offset_y': win_offset_y})
                                else:
                                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                                    if max_val > frame_max_val: frame_max_val = max_val
                                    if max_val >= confidence_threshold:
                                        abs_loc = (max_loc[0] + rox, max_loc[1] + roy)
                                        found_matches.append({'name': t['name'], 'val': max_val, 'loc': abs_loc, 'h': t['h'], 'w': t['w'], 'offset_x': win_offset_x, 'offset_y': win_offset_y})
                            except Exception: pass

                    self.target_hwnds = updated_hwnds
                    self.root.after(0, lambda: self.btn_select_wins.config(text=f"Select windows ({len(self.target_hwnds)})"))

                    if not self.target_hwnds:
                        self.root.after(0, lambda: self.log_msg("All target windows have closed. Stopping.", "fail"))
                        self.root.after(0, self.toggle_detection)
                        break

                if found_matches:
                    self.last_detect_time, self.last_detect_val = time.strftime("%H:%M:%S"), frame_max_val
                    self.trigger_visual_alert()
                    self.set_status_persistent(f"Found {len(found_matches)} match(es)! (best: {frame_max_val:.1%})", COLOR_STATUS_HIT, "black")
                    for fm in found_matches:
                        abs_x, abs_y = fm.get('offset_x', monitor['left']) + fm['loc'][0], fm.get('offset_y', monitor['top']) + fm['loc'][1]
                        if self.enable_overlay_circle.get() or self.enable_overlay_text.get():
                            self.root.after(0, lambda x=abs_x, y=abs_y, w=fm['w'], h=fm['h'], d=freq * 0.75, txt=f"{fm['val']:.1%}" if self.enable_overlay_text.get() else "", sc=self.enable_overlay_circle.get():
                                            LockOverlay(x, y, w, h, d, text_info=txt, stroke_width=self.stroke_width.get(), show_circle=sc))
                        self.root.after(0, lambda m=f"Match [{fm['name']}] ({fm['val']:.1%}) - (X:{abs_x}, Y:{abs_y})": self.log_msg(m, "success"))
                        if self.enable_click.get(): self.perform_click(monitor, fm['loc'], fm['h'], fm['w'], self.click_count.get(), self.click_interval.get(), custom_offset=(fm['offset_x'], fm['offset_y']) if 'offset_x' in fm else None)
                    if self.enable_sound.get() and not pygame.mixer.music.get_busy(): self.play_sound(is_success=True)
                else:
                    msg = f"Scanning... (current max: {frame_max_val:.1%})"
                    if self.last_detect_time: msg += f" | last match: {self.last_detect_time} ({self.last_detect_val:.1%})"
                    self.set_status_persistent(msg, "#333", "white")
                    if self.enable_fail_sound.get() and not pygame.mixer.music.get_busy(): self.play_sound(is_success=False)

                time.sleep(max(0.05, freq - (time.time() - start_ts)))


def start_application():
    """Create and run the main application window."""
    global app
    app = DetectorApp(root)


if __name__ == "__main__":
    root = tk.Tk()

    # Set the window icon if the file exists
    try:
        icon_path = resource_path('ico.png')
        icon_image = ImageTk.PhotoImage(file=icon_path)
        root.iconphoto(True, icon_image)
    except Exception:
        pass

    start_application()
    root.mainloop()
