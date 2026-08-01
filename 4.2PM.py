import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
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

# High DPI Fix
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

class SnippingTool(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.withdraw() 
        
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            sct_img = sct.grab(monitor)
            self.src_img_np = np.array(sct_img)
            self.src_img_rgb = cv2.cvtColor(self.src_img_np, cv2.COLOR_BGRA2RGB)
            self.original_pil = Image.fromarray(self.src_img_rgb)

        enhancer = ImageEnhance.Brightness(self.original_pil)
        self.dark_pil = enhancer.enhance(0.4) 
        self.tk_dark_img = ImageTk.PhotoImage(self.dark_pil)
        
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.95) # Slight transparency for better UX
        self.configure(cursor="cross")
        
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.create_image(0, 0, image=self.tk_dark_img, anchor="nw")

        # Instruction overlay
        self.canvas.create_text(
            self.winfo_screenwidth()//2, 50, 
            text="Click & Drag to Select Target Area (Right-click or ESC to Cancel)", 
            fill="white", font=("Segoe UI", 12, "bold")
        )

        self.start_x = None
        self.start_y = None
        self.selection_rect_id = None 
        self.highlight_img_id = None 
        self.tk_region_img = None 

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<ButtonPress-3>", self.exit_snip) 
        self.bind("<Escape>", self.exit_snip)        

        self.deiconify() 

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.selection_rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, 
            outline='#00FF00', width=2
        )

    def on_drag(self, event):
        if not self.start_x: return
        cur_x, cur_y = event.x, event.y
        x1 = min(self.start_x, cur_x)
        y1 = min(self.start_y, cur_y)
        x2 = max(self.start_x, cur_x)
        y2 = max(self.start_y, cur_y)
        
        self.canvas.coords(self.selection_rect_id, x1, y1, x2, y2)
        
        if x2 - x1 > 0 and y2 - y1 > 0:
            region = self.original_pil.crop((x1, y1, x2, y2))
            self.tk_region_img = ImageTk.PhotoImage(region)
            
            if self.highlight_img_id is None:
                self.highlight_img_id = self.canvas.create_image(x1, y1, image=self.tk_region_img, anchor="nw")
            else:
                self.canvas.coords(self.highlight_img_id, x1, y1)
                self.canvas.itemconfig(self.highlight_img_id, image=self.tk_region_img)
            self.canvas.tag_raise(self.selection_rect_id)

    def on_release(self, event):
        if self.start_x is None: return
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            img_crop = self.src_img_np[y1:y2, x1:x2]
            img_final = cv2.cvtColor(img_crop, cv2.COLOR_BGRA2BGR)
            self.destroy()
            self.callback(img_final)
        else:
            self.cancel_selection()

    def cancel_selection(self):
        self.canvas.delete(self.selection_rect_id)
        self.canvas.delete(self.highlight_img_id)
        self.start_x = None
        self.selection_rect_id = None
        self.highlight_img_id = None

    def exit_snip(self, event=None):
        self.destroy()

class DetectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Visual Automation Pro v5.0") 
        self.root.geometry("540x850") 
        self.root.resizable(False, False)
        
        pygame.mixer.init()
        
        # Core State
        self.target_image = None
        self.tk_preview = None 
        self.audio_path = None
        self.is_running = False
        self.is_preview_hidden = False 
        self.last_click_time = 0
        
        # Variables
        self.scan_freq = tk.DoubleVar(value=1.5)
        self.confidence_val = tk.DoubleVar(value=0.85)
        self.play_mode = tk.StringVar(value="times")
        self.play_value = tk.DoubleVar(value=1)
        
        self.enable_sound = tk.BooleanVar(value=True) 
        self.enable_click = tk.BooleanVar(value=False) 
        self.enable_cooldown = tk.BooleanVar(value=True) # New: Safety cooldown
        
        self.setup_ui()
        
        # Global Hotkey Bind (Safety Feature)
        self.root.bind('<F10>', self.toggle_detection_event)
        self.root.bind('<Escape>', self.force_stop)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TButton", padding=5, font=("Segoe UI", 9))
        style.configure("TLabelFrame", font=("Segoe UI", 10, "bold"))
        
        main_pad = 15
        self.main_frame = tk.Frame(self.root, padx=main_pad, pady=main_pad, bg="#f4f4f4")
        self.main_frame.pack(fill="both", expand=True)

        # --- Header ---
        header_frame = tk.Frame(self.main_frame, bg="#f4f4f4")
        header_frame.pack(fill="x", pady=(0, 10))
        tk.Label(header_frame, text="Visual Auto-Clicker", font=("Segoe UI", 16, "bold"), bg="#f4f4f4", fg="#333").pack(side="left")
        tk.Label(header_frame, text="Press F10 to Start/Stop", font=("Segoe UI", 9, "bold"), bg="#ffdddd", fg="#d63031", padx=5, pady=2).pack(side="right")

        # --- 1. Target ---
        group_img = ttk.LabelFrame(self.main_frame, text=" 1. Target Image ", padding=10)
        group_img.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(group_img)
        btn_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_frame, text="📷 Snip Screen", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="📂 Load File", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=2)
        self.btn_toggle = ttk.Button(btn_frame, text="👁 Hide", command=self.toggle_preview_visibility)
        self.btn_toggle.pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.preview_container = tk.Frame(group_img, height=120, bg="#e0e0e0", relief="sunken", borderwidth=1)
        self.preview_container.pack(fill="x", expand=False)
        self.preview_container.pack_propagate(False)
        self.lbl_preview = tk.Label(self.preview_container, text="No Target Selected", bg="#e0e0e0", fg="#888")
        self.lbl_preview.pack(fill="both", expand=True)

        # --- 2. Actions ---
        group_action = ttk.LabelFrame(self.main_frame, text=" 2. Actions & Feedback ", padding=10)
        group_action.pack(fill="x", pady=10)

        # Toggles
        check_frame = ttk.Frame(group_action)
        check_frame.pack(fill="x", pady=(0, 5))
        ttk.Checkbutton(check_frame, text="🔊 Play Sound", variable=self.enable_sound).pack(side="left", padx=(0, 15))
        ttk.Checkbutton(check_frame, text="🖱️ Auto Click", variable=self.enable_click).pack(side="left", padx=(0, 15))
        ttk.Checkbutton(check_frame, text="⏳ Click Cooldown (3s)", variable=self.enable_cooldown).pack(side="left")

        # Sound Config
        audio_frame = ttk.Frame(group_action)
        audio_frame.pack(fill="x", pady=5)
        self.lbl_audio = ttk.Label(audio_frame, text="Sound: System Beep", font=("Segoe UI", 9), foreground="#666")
        self.lbl_audio.pack(side="left")
        ttk.Button(audio_frame, text="Change...", width=8, command=self.load_audio_file).pack(side="right")

        # --- 3. Settings ---
        group_settings = ttk.LabelFrame(self.main_frame, text=" 3. Settings ", padding=10)
        group_settings.pack(fill="x", pady=5)

        # Grid layout for settings
        grid_frame = ttk.Frame(group_settings)
        grid_frame.pack(fill="x")

        # Scan Frequency
        ttk.Label(grid_frame, text="Scan Interval:").grid(row=0, column=0, sticky="w", pady=5)
        scale_freq = ttk.Scale(grid_frame, from_=0.2, to=5.0, variable=self.scan_freq, orient="horizontal")
        scale_freq.grid(row=0, column=1, sticky="ew", padx=10)
        self.lbl_freq_val = ttk.Label(grid_frame, text="1.5s", width=5)
        self.lbl_freq_val.grid(row=0, column=2, sticky="e")
        self.scan_freq.trace_add("write", lambda *args: self.lbl_freq_val.config(text=f"{self.scan_freq.get():.1f}s"))

        # Confidence
        ttk.Label(grid_frame, text="Strictness:").grid(row=1, column=0, sticky="w", pady=5)
        scale_conf = ttk.Scale(grid_frame, from_=0.6, to=0.99, variable=self.confidence_val, orient="horizontal")
        scale_conf.grid(row=1, column=1, sticky="ew", padx=10)
        self.lbl_conf_val = ttk.Label(grid_frame, text="85%", width=5)
        self.lbl_conf_val.grid(row=1, column=2, sticky="e")
        self.confidence_val.trace_add("write", lambda *args: self.lbl_conf_val.config(text=f"{int(self.confidence_val.get()*100)}%"))

        grid_frame.columnconfigure(1, weight=1)

        # --- 4. Logs (New) ---
        log_frame = ttk.LabelFrame(self.main_frame, text=" Event Log ", padding=5)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 8), state="disabled", bg="#fafafa")
        self.log_text.pack(fill="both", expand=True)

        # --- Control Button ---
        self.btn_control = tk.Button(self.main_frame, text="START MONITORING (F10)", command=self.toggle_detection,
                                     bg="#2ecc71", fg="white", font=("Segoe UI", 12, "bold"),
                                     relief="flat", activebackground="#27ae60", activeforeground="white", cursor="hand2")
        self.btn_control.pack(fill="x", pady=(15, 0), ipady=5)

        # Status Bar
        self.status_bar = tk.Label(self.root, text="Ready", bd=0, bg="#e0e0e0", fg="#555", font=("Segoe UI", 9), anchor="w", padx=10, pady=2)
        self.status_bar.pack(side="bottom", fill="x")

    def log_msg(self, msg, type="info"):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}\n"
        
        self.log_text.config(state="normal")
        self.log_text.insert("end", full_msg)
        
        # Color coding logs
        end_index = self.log_text.index("end-1c")
        start_index = f"{float(self.log_text.index('end-1c')) - 1.0}"
        
        if type == "success":
            self.log_text.tag_add("success", start_index, end_index)
            self.log_text.tag_config("success", foreground="#27ae60") # Green
        elif type == "error":
            self.log_text.tag_add("error", start_index, end_index)
            self.log_text.tag_config("error", foreground="#c0392b") # Red
            
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def start_snipping(self):
        self.root.iconify()
        self.root.after(200, lambda: SnippingTool(self.root, self.set_target_image))

    def load_image_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if file_path:
            img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            self.set_target_image(img)

    def set_target_image(self, img):
        self.root.deiconify()
        if img is None: return

        self.target_image = img
        self.log_msg(f"Target loaded: {img.shape[1]}x{img.shape[0]} px")

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img_rgb)
        
        # Preserve aspect ratio for preview
        container_w, container_h = 460, 120
        im_pil.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
        
        self.tk_preview = ImageTk.PhotoImage(im_pil)
        self.is_preview_hidden = False
        self.update_preview_visibility()

    def toggle_preview_visibility(self):
        if self.target_image is None: return
        self.is_preview_hidden = not self.is_preview_hidden
        self.update_preview_visibility()

    def update_preview_visibility(self):
        if self.target_image is None:
            self.btn_toggle.config(text="👁 Hide")
            return

        if self.is_preview_hidden:
            self.lbl_preview.config(image="", text="[ Preview Hidden ]", fg="#666")
            self.btn_toggle.config(text="👁 Show")
        else:
            self.lbl_preview.config(image=self.tk_preview, text="")
            self.btn_toggle.config(text="👁 Hide")

    def load_audio_file(self):
        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3;*.wav")])
        if path:
            self.audio_path = path
            self.lbl_audio.config(text=f"File: {os.path.basename(path)}")

    def toggle_detection_event(self, event):
        self.toggle_detection()

    def force_stop(self, event):
        if self.is_running:
            self.toggle_detection()

    def toggle_detection(self):
        if self.is_running:
            self.is_running = False
            self.btn_control.config(text="START MONITORING (F10)", bg="#2ecc71")
            self.status_bar.config(bg="#e0e0e0", fg="#555", text="Stopped")
            self.log_msg("Monitoring Stopped.")
            pygame.mixer.music.stop()
        else:
            if self.target_image is None:
                messagebox.showwarning("Missing Target", "Please Select a Target Image First!")
                return
            
            self.is_running = True
            self.btn_control.config(text="🛑 STOP (F10 / ESC)", bg="#e74c3c")
            self.status_bar.config(bg="#f1c40f", fg="#000", text="Running... Scanning Screen...")
            self.log_msg("Monitoring Started...", "info")
            
            t = threading.Thread(target=self.loop_detection)
            t.daemon = True
            t.start()

    def play_sound(self):
        try:
            if self.audio_path:
                pygame.mixer.music.load(self.audio_path)
            else:
                if os.name == 'nt':
                    import winsound
                    winsound.Beep(1000, 200) # Short beep
                return

            if self.play_mode.get() == "times":
                times = int(self.play_value.get())
                pygame.mixer.music.play(loops=max(0, times - 1))
            else:
                duration = self.play_value.get()
                pygame.mixer.music.play(loops=-1)
                threading.Timer(duration, pygame.mixer.music.stop).start()
        except Exception as e:
            self.log_msg(f"Audio Error: {str(e)}", "error")

    def perform_click(self, monitor, match_loc, target_shape):
        current_time = time.time()
        
        # Cooldown Check
        if self.enable_cooldown.get() and (current_time - self.last_click_time < 3):
            self.log_msg("Target found, but in cooldown.", "info")
            return

        try:
            h, w = target_shape
            center_x = match_loc[0] + w // 2
            center_y = match_loc[1] + h // 2
            
            screen_x = monitor['left'] + center_x
            screen_y = monitor['top'] + center_y
            
            pyautogui.click(screen_x, screen_y)
            self.last_click_time = current_time
            self.log_msg(f"🖱️ Clicked at ({screen_x}, {screen_y})", "success")
            
        except Exception as e:
            self.log_msg(f"Click Failed: {e}", "error")

    def visual_feedback(self):
        # Subtle flash on status bar instead of whole screen
        orig_bg = self.status_bar.cget("bg")
        self.status_bar.config(bg="#2ecc71", text="TARGET MATCHED!")
        self.root.after(500, lambda: self.status_bar.config(bg="#f1c40f", text="Running... Scanning Screen..."))

    def loop_detection(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            target_gray = cv2.cvtColor(self.target_image, cv2.COLOR_BGR2GRAY)
            target_h, target_w = target_gray.shape
            
            while self.is_running:
                start_ts = time.time()
                
                sct_img = sct.grab(monitor)
                screen_np = np.array(sct_img)
                screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGRA2GRAY)
                
                try:
                    res = cv2.matchTemplate(screen_gray, target_gray, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    threshold = self.confidence_val.get()
                    
                    if max_val >= threshold:
                        self.root.after(0, self.visual_feedback)
                        
                        if self.enable_sound.get():
                            if not pygame.mixer.music.get_busy():
                                self.play_sound()
                        
                        if self.enable_click.get():
                            self.perform_click(monitor, max_loc, (target_h, target_w))
                        else:
                            # Log detection if not clicking
                            self.root.after(0, lambda: self.log_msg(f"Target Detected (Conf: {max_val:.1%})", "success"))

                    else:
                        # Optional: Log keepalive or debug
                        pass
                        
                except Exception as e:
                    print(f"CV Error: {e}")
                
                process_time = time.time() - start_ts
                wait_time = max(0.2, self.scan_freq.get() - process_time)
                time.sleep(wait_time)

if __name__ == "__main__":
    root = tk.Tk()
    app = DetectorApp(root)
    root.mainloop()
