import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import mss
import pygame
from PIL import Image, ImageTk, ImageEnhance
import threading
import time
import os
import ctypes

# 尝试开启 Windows 高DPI感知，防止截图坐标偏移
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

class SnippingTool(tk.Toplevel):
    """
    高仿 QQ/微信 截图工具
    """
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.withdraw() # 先隐藏
        
        # 1. 获取全屏截图
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            sct_img = sct.grab(monitor)
            self.src_img_np = np.array(sct_img)
            self.src_img_rgb = cv2.cvtColor(self.src_img_np, cv2.COLOR_BGRA2RGB)
            self.original_pil = Image.fromarray(self.src_img_rgb)

        # 2. 生成背景图（变暗）
        enhancer = ImageEnhance.Brightness(self.original_pil)
        self.dark_pil = enhancer.enhance(0.4) 
        self.tk_dark_img = ImageTk.PhotoImage(self.dark_pil)
        
        # 3. 初始化窗口
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
            # mss截取的原始数据用于保存，避免PIL压缩损失
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
        self.root.title("智能屏幕监控 V2.0")
        self.root.geometry("520x720")
        self.root.resizable(False, False)

        pygame.mixer.init()
        
        self.target_image = None
        self.audio_path = None
        self.is_running = False
        
        self.scan_freq = tk.IntVar(value=1)
        self.confidence_val = tk.DoubleVar(value=0.85)
        self.play_mode = tk.StringVar(value="times")
        self.play_value = tk.DoubleVar(value=1)
        
        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill="both", expand=True)

        # --- 1. 目标图像区域 ---
        group_img = ttk.LabelFrame(main_frame, text=" 1. 监控目标 ", padding=10)
        group_img.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(group_img)
        # 修正: 使用 pady=(上, 下) 代替 mb
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(btn_frame, text="✀ 屏幕截图 (QQ风格)", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(btn_frame, text="📂 导入本地图片", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # 预览容器
        self.preview_container = tk.Frame(group_img, width=460, height=180, bg="#f0f0f0", relief="sunken", borderwidth=1)
        self.preview_container.pack(fill="none", expand=False)
        self.preview_container.pack_propagate(False)

        self.lbl_preview = tk.Label(self.preview_container, text="请截取或导入目标图片", bg="#f0f0f0", fg="#888")
        self.lbl_preview.pack(fill="both", expand=True)

        # --- 2. 提示音配置 ---
        group_audio = ttk.LabelFrame(main_frame, text=" 2. 警报设置 ", padding=10)
        group_audio.pack(fill="x", pady=10)

        audio_row = ttk.Frame(group_audio)
        audio_row.pack(fill="x")
        
        self.lbl_audio_name = ttk.Label(audio_row, text="当前: 默认系统提示音", width=30, anchor="w")
        self.lbl_audio_name.pack(side="left")
        ttk.Button(audio_row, text="选择音频...", command=self.load_audio_file, width=12).pack(side="right")

        # 播放模式
        # 修正: 移除了错误的 mt 参数，改用 pack 的 pady
        mode_row = ttk.Frame(group_audio)
        mode_row.pack(fill="x", pady=(5, 0))
        
        ttk.Radiobutton(mode_row, text="播放次数:", variable=self.play_mode, value="times").pack(side="left")
        sp_times = ttk.Spinbox(mode_row, from_=1, to=10, width=5, textvariable=self.play_value)
        sp_times.pack(side="left", padx=5)
        
        ttk.Label(mode_row, text="   |   ").pack(side="left")
        
        ttk.Radiobutton(mode_row, text="持续时长(秒):", variable=self.play_mode, value="duration").pack(side="left")
        sp_dur = ttk.Spinbox(mode_row, from_=1, to=60, width=5, textvariable=self.play_value)
        sp_dur.pack(side="left", padx=5)

        # --- 3. 检测参数 ---
        group_settings = ttk.LabelFrame(main_frame, text=" 3. 运行参数 ", padding=10)
        group_settings.pack(fill="x", pady=5)

        f_row = ttk.Frame(group_settings)
        f_row.pack(fill="x", pady=5)
        ttk.Label(f_row, text="检测间隔 (秒):", width=12).pack(side="left")
        
        # 滑块
        scale_freq = ttk.Scale(f_row, from_=1, to=10, variable=self.scan_freq, orient="horizontal", length=200, command=lambda v: self.scan_freq.set(int(float(v))))
        scale_freq.pack(side="left", padx=10)
        
        self.lbl_freq_val = ttk.Label(f_row, text="1 秒", width=5)
        self.lbl_freq_val.pack(side="left")
        self.scan_freq.trace_add("write", lambda *args: self.lbl_freq_val.config(text=f"{self.scan_freq.get()} 秒"))

        c_row = ttk.Frame(group_settings)
        c_row.pack(fill="x", pady=5)
        ttk.Label(c_row, text="匹配灵敏度:", width=12).pack(side="left")
        ttk.Scale(c_row, from_=0.5, to=0.99, variable=self.confidence_val, orient="horizontal", length=200).pack(side="left", padx=10)
        
        self.lbl_conf_val = ttk.Label(c_row, text="0.85")
        self.lbl_conf_val.pack(side="left")
        self.confidence_val.trace_add("write", lambda *args: self.lbl_conf_val.config(text=f"{self.confidence_val.get():.2f}"))

        # --- 4. 底部控制 ---
        self.btn_control = tk.Button(main_frame, text="启动监控", command=self.toggle_detection,
                                     bg="#007bff", fg="white", font=("Microsoft YaHei UI", 14, "bold"),
                                     relief="flat", height=2)
        self.btn_control.pack(fill="x", pady=(20, 0))

        self.status_bar = tk.Label(self.root, text="就绪 - 请先设置目标", bd=1, relief="sunken", anchor="w", bg="#e9ecef", padx=5)
        self.status_bar.pack(side="bottom", fill="x")

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
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img_rgb)
        
        container_w, container_h = 460, 180
        im_pil.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
        
        self.tk_preview = ImageTk.PhotoImage(im_pil)
        self.lbl_preview.config(image=self.tk_preview, text="")
        self.status_bar.config(text=f"目标已设定: {img.shape[1]}x{img.shape[0]} 像素")

    def load_audio_file(self):
        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3;*.wav")])
        if path:
            self.audio_path = path
            name = os.path.basename(path)
            if len(name) > 20: name = name[:17] + "..."
            self.lbl_audio_name.config(text=f"当前: {name}")

    def toggle_detection(self):
        if self.is_running:
            self.is_running = False
            self.btn_control.config(text="启动监控", bg="#007bff")
            self.status_bar.config(text="已停止")
            pygame.mixer.music.stop()
        else:
            if self.target_image is None:
                messagebox.showwarning("错误", "请先截取或导入一张目标图片！")
                return
            
            self.is_running = True
            self.btn_control.config(text="🛑 停止运行", bg="#dc3545")
            
            t = threading.Thread(target=self.loop_detection)
            t.daemon = True
            t.start()

    def play_sound(self):
        try:
            if self.audio_path:
                pygame.mixer.music.load(self.audio_path)
            else:
                # 系统 Beep 提示
                if os.name == 'nt':
                    import winsound
                    winsound.Beep(1000, 500)
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
            print(f"音频错误: {e}")

    def loop_detection(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            
            target_gray = cv2.cvtColor(self.target_image, cv2.COLOR_BGR2GRAY)
            
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
                        if not pygame.mixer.music.get_busy():
                            self.root.after(0, lambda: self.status_bar.config(text=">>> 警报触发 <<<", bg="#ffc107"))
                            self.play_sound()
                    else:
                        msg = f"监控中... 最高相似度: {max_val:.2%}"
                        self.root.after(0, lambda: self.status_bar.config(text=msg, bg="#e9ecef"))
                        
                except Exception as e:
                    print(f"CV Error: {e}")
                
                process_time = time.time() - start_ts
                wait_time = max(0.1, self.scan_freq.get() - process_time)
                time.sleep(wait_time)

if __name__ == "__main__":
    root = tk.Tk()
    app = DetectorApp(root)
    root.mainloop()