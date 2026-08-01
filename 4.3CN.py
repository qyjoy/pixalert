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
        self.configure(cursor="cross")
        
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.create_image(0, 0, image=self.tk_dark_img, anchor="nw")

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
            outline='#00BFFF', width=2
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
        self.root.title("PixAlert - V4.3 增强版 By QyJoy") 
        self.root.geometry("520x920")  # Increased height for Log Box and new options
        self.root.resizable(False, False)
        
        self.default_bg = self.root.cget("bg") 
        
        pygame.mixer.init()
        
        self.target_image = None
        self.tk_preview = None 
        
        # Audio Paths
        self.success_audio_path = None
        self.fail_audio_path = None
        
        self.is_running = False
        self.is_preview_hidden = False 
        self.last_detect_time = None   
        
        self.scan_freq = tk.IntVar(value=3)
        self.confidence_val = tk.DoubleVar(value=0.75)
        self.play_mode = tk.StringVar(value="times")
        self.play_value = tk.DoubleVar(value=1)
        self.btn_preview_text = tk.StringVar(value="👁 隐藏预览") 
        
        self.enable_sound = tk.BooleanVar(value=True) 
        self.enable_click = tk.BooleanVar(value=False)
        self.enable_fail_sound = tk.BooleanVar(value=False) # New: Fail sound switch
        
        self.setup_ui()
        self.update_fail_audio_visibility()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        self.main_frame = tk.Frame(self.root, padx=15, pady=15, bg=self.default_bg)
        self.main_frame.pack(fill="both", expand=True)

        # --- 1. Target Monitor ---
        group_img = ttk.LabelFrame(self.main_frame, text=" 1. 目标监控 ", padding=10)
        group_img.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(group_img)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(btn_frame, text="✀ 截图", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="📂 导入", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=2)
        
        self.btn_toggle = ttk.Button(btn_frame, textvariable=self.btn_preview_text, command=self.toggle_preview_visibility)
        self.btn_toggle.pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.preview_container = tk.Frame(group_img, width=460, height=150, bg="#f0f0f0", relief="sunken", borderwidth=1)
        self.preview_container.pack(fill="none", expand=False)
        self.preview_container.pack_propagate(False)

        self.lbl_preview = tk.Label(self.preview_container, text="请截图或导入目标图像", bg="#f0f0f0", fg="#888")
        self.lbl_preview.pack(fill="both", expand=True)

        # --- 2. Actions ---
        group_audio = ttk.LabelFrame(self.main_frame, text=" 2. 触发动作 ", padding=10)
        group_audio.pack(fill="x", pady=10)

        # -- Switches --
        action_switch_row = ttk.Frame(group_audio)
        action_switch_row.pack(fill="x", pady=(0, 10))
        
        chk_sound = ttk.Checkbutton(action_switch_row, text="发现提示音", variable=self.enable_sound)
        chk_sound.pack(side="left", padx=(0, 10))
        
        chk_click = ttk.Checkbutton(action_switch_row, text="自动点击", variable=self.enable_click)
        chk_click.pack(side="left", padx=(0, 10))

        chk_fail_sound = ttk.Checkbutton(
            action_switch_row,
            text="失败提示音",
            variable=self.enable_fail_sound,
            command=self.update_fail_audio_visibility
        )
        chk_fail_sound.pack(side="left")


        # -- Success Audio File --
        audio_row = ttk.Frame(group_audio)
        audio_row.pack(fill="x", pady=(5,0))
        self.lbl_audio_name = ttk.Label(audio_row, text="发现音频: 默认", width=25, anchor="w")
        self.lbl_audio_name.pack(side="left")
        ttk.Button(audio_row, text="选择音频...", command=self.load_success_audio, width=15).pack(side="right")

        self.fail_audio_row = ttk.Frame(group_audio)
        self.fail_audio_row.pack(fill="x", pady=(5,0))
        self.lbl_fail_audio_name = ttk.Label(
            self.fail_audio_row, text="失败音频: 默认", width=25, anchor="w"
        )
        self.lbl_fail_audio_name.pack(side="left")
        ttk.Button(
            self.fail_audio_row, text="选择音频...", command=self.load_fail_audio, width=15
        ).pack(side="right")


        # -- Play Settings --
        mode_row = ttk.Frame(group_audio)
        mode_row.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(mode_row, text="次数:", variable=self.play_mode, value="times").pack(side="left")
        ttk.Spinbox(mode_row, from_=1, to=10, width=5, textvariable=self.play_value).pack(side="left", padx=5)
        ttk.Label(mode_row, text="|").pack(side="left", padx=5)
        ttk.Radiobutton(mode_row, text="时长(秒):", variable=self.play_mode, value="duration").pack(side="left")
        ttk.Spinbox(mode_row, from_=1, to=60, width=5, textvariable=self.play_value).pack(side="left", padx=5)

        # --- 3. Parameters ---
        group_settings = ttk.LabelFrame(self.main_frame, text=" 3. 参数设置 ", padding=10)
        group_settings.pack(fill="x", pady=5)

        f_row = ttk.Frame(group_settings)
        f_row.pack(fill="x", pady=5)
        ttk.Label(f_row, text="扫描间隔(秒):", width=12).pack(side="left")
        ttk.Scale(f_row, from_=0.1, to=10, variable=self.scan_freq, orient="horizontal", length=200).pack(side="left", padx=10)
        self.lbl_freq_val = ttk.Label(f_row,text=f"{self.scan_freq.get():.1f} s",width=5)
        self.lbl_freq_val.pack(side="left")
        self.scan_freq.trace_add("write", lambda *args: self.lbl_freq_val.config(text=f"{self.scan_freq.get():.1f} s"))

        c_row = ttk.Frame(group_settings)
        c_row.pack(fill="x", pady=5)
        ttk.Label(c_row, text="严格度:", width=12).pack(side="left")
        ttk.Scale(c_row, from_=0.5, to=0.99, variable=self.confidence_val, orient="horizontal", length=200).pack(side="left", padx=10)
        self.lbl_conf_val = ttk.Label(c_row,text=f"{self.confidence_val.get():.2f}")
        self.lbl_conf_val.pack(side="left")
        self.confidence_val.trace_add("write", lambda *args: self.lbl_conf_val.config(text=f"{self.confidence_val.get():.2f}"))

        # --- Log Box (New) ---
        group_log = ttk.LabelFrame(self.main_frame, text=" 事件日志 ", padding=10)
        group_log.pack(fill="both", expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(group_log, height=6, state='disabled', font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("success", foreground="#009900", font=("Consolas", 8, "bold"))

        # --- Control ---
        self.btn_control = tk.Button(self.main_frame, text="开始监控", command=self.toggle_detection,
                                     bg="#007bff", fg="white", font=("Microsoft YaHei UI", 14, "bold"),
                                     relief="flat", height=2)
        self.btn_control.pack(fill="x", pady=(10, 0))

        self.status_bar = tk.Label(self.root, text="就绪", bd=1, relief="sunken", anchor="w", bg="#e9ecef", padx=5, font=("Arial", 9))
        self.status_bar.pack(side="bottom", fill="x")
    
    def update_fail_audio_visibility(self):
        if self.enable_fail_sound.get():
            self.fail_audio_row.pack(fill="x", pady=(5, 0))
        else:
            self.fail_audio_row.pack_forget()

    def log_msg(self, msg, tag=None):
        """Adds a message to the scrolling log box"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def start_snipping(self):
        self.root.iconify()
        self.root.after(200, lambda: SnippingTool(self.root, self.set_target_image))

    def load_image_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.bmp")])
        if file_path:
            img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            self.set_target_image(img)

    def set_target_image(self, img):
        self.root.deiconify()
        if img is None: return

        self.target_image = img
        self.last_detect_time = None
        self.status_bar.config(text=f"目标已加载: {img.shape[1]}x{img.shape[0]} px", bg="#e9ecef")
        self.log_msg(f"目标已加载: {img.shape[1]}x{img.shape[0]} px")

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img_rgb)
        
        container_w, container_h = 460, 150
        im_pil.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
        
        self.tk_preview = ImageTk.PhotoImage(im_pil)
        
        self.is_preview_hidden = False
        self.update_preview_visibility()

    def toggle_preview_visibility(self):
        if self.target_image is None:
            return
        self.is_preview_hidden = not self.is_preview_hidden
        self.update_preview_visibility()

    def update_preview_visibility(self):
        if self.target_image is None:
            self.btn_preview_text.set("👁 隐藏预览")
            return

        if self.is_preview_hidden:
            self.lbl_preview.config(image="", text="[ 预览已隐藏 ]\n\n防止发生自检测错误", fg="#666")
            self.btn_preview_text.set("👁 显示预览")
        else:
            self.lbl_preview.config(image=self.tk_preview, text="")
            self.btn_preview_text.set("👁 隐藏预览")

    def load_success_audio(self):
        path = filedialog.askopenfilename(filetypes=[("音频文件", "*.mp3;*.wav")])
        if path:
            self.success_audio_path = path
            name = os.path.basename(path)
            if len(name) > 20: name = name[:17] + "..."
            self.lbl_audio_name.config(text=f"发现音频: {name}")
            self.log_msg(f"发现音频已设为: {name}")

    def load_fail_audio(self):
        path = filedialog.askopenfilename(filetypes=[("音频文件", "*.mp3;*.wav")])
        if path:
            self.fail_audio_path = path
            name = os.path.basename(path)
            if len(name) > 20: name = name[:17] + "..."
            self.lbl_fail_audio_name.config(text=f"失败音频: {name}")
            self.log_msg(f"失败音频已设为: {name}")

    def toggle_detection(self):
        if self.is_running:
            self.is_running = False
            self.btn_control.config(text="开始监控", bg="#007bff")
            self.status_bar.config(text="监控已停止", bg="#e9ecef")
            self.log_msg("监控已停止。")
            pygame.mixer.music.stop()
        else:
            if self.target_image is None:
                messagebox.showwarning("错误", "请先截图或导入目标图像！")
                return
            
            self.is_running = True
            self.btn_control.config(text="🛑 停止运行", bg="#dc3545")
            self.log_msg("监控已启动。")
            
            t = threading.Thread(target=self.loop_detection)
            t.daemon = True
            t.start()

    def play_sound(self, is_success=True):
        try:
            # Determine which file to play
            target_path = self.success_audio_path if is_success else self.fail_audio_path
            
            if target_path:
                pygame.mixer.music.load(target_path)
            else:
                # System beep fallback
                if os.name == 'nt':
                    import winsound
                    # Different frequency for success vs fail
                    freq = 1000 if is_success else 500
                    winsound.Beep(freq, 200)
                else:
                    print('\a')
                return

            if self.play_mode.get() == "times":
                times = int(self.play_value.get())
                pygame.mixer.music.play(loops=max(0, times - 1))
            else:
                duration = self.play_value.get()
                pygame.mixer.music.play(loops=-1)
                threading.Timer(duration, pygame.mixer.music.stop).start()
        except Exception as e:
            self.log_msg(f"音频错误: {e}")

    def perform_click(self, monitor, match_loc, target_shape):
        try:
            h, w = target_shape
            
            center_x_in_img = match_loc[0] + w // 2
            center_y_in_img = match_loc[1] + h // 2
            
            screen_x = monitor['left'] + center_x_in_img
            screen_y = monitor['top'] + center_y_in_img
            
            pyautogui.click(screen_x, screen_y)
            self.log_msg(f"已点击位置: {screen_x}, {screen_y}")
            print(f"Click executed at: {screen_x}, {screen_y}")
            
        except Exception as e:
            self.log_msg(f"点击失败: {e}")
            print(f"Click failed: {e}")

    def loop_detection(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            target_gray = cv2.cvtColor(self.target_image, cv2.COLOR_BGR2GRAY)
            target_h, target_w = target_gray.shape
            
            def set_window_color(color):
                self.root.configure(bg=color)
                self.main_frame.configure(bg=color)

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
                        self.last_detect_time = time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        msg = f"目标发现! 置信度:{max_val:.1%} @ 坐标({max_loc[0]}, {max_loc[1]})"
                        self.root.after(0, lambda m=msg: self.status_bar.config(text=m, bg="#ffc107", fg="black"))
                        self.root.after(0, lambda m=msg: self.log_msg(m, "success"))
                        
                        self.root.after(0, lambda: set_window_color("#ff3333")) 
                        time.sleep(0.1) 
                        self.root.after(0, lambda: set_window_color("#3333ff")) 
                        time.sleep(0.1)
                        self.root.after(0, lambda: set_window_color("#33ff33")) 
                        time.sleep(0.1)

                        if self.enable_sound.get():
                            if not pygame.mixer.music.get_busy():
                                self.play_sound(is_success=True)
                        
                        if self.enable_click.get():
                            self.perform_click(monitor, max_loc, (target_h, target_w))

                    else:
                        self.root.after(0, lambda: set_window_color(self.default_bg))
                        
                        msg = f"搜索中... (当前最大: {max_val:.1%})"
                        if self.last_detect_time:
                            msg += f" | 上次发现: {self.last_detect_time}"
                        
                        self.root.after(0, lambda m=msg: self.status_bar.config(text=m, bg="#e9ecef", fg="black"))
                        
                        # --- Logic for Fail Sound ---
                        if self.enable_fail_sound.get():
                            if not pygame.mixer.music.get_busy():
                                self.play_sound(is_success=False)
                        
                except Exception as e:
                    print(f"CV Error: {e}")
                
                process_time = time.time() - start_ts
                wait_time = max(0.1, self.scan_freq.get() - process_time)
                time.sleep(wait_time)

if __name__ == "__main__":
    root = tk.Tk()
    app = DetectorApp(root)
    root.mainloop()
