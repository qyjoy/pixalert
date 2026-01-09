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
    高仿 QQ/微信 截图工具 (无变化，保持 V2 的优秀体验)
    """
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.withdraw() 
        
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
        self.root.title("PixAlert - Treasure Hunter V3.0")
        self.root.geometry("520x760") #稍微加高一点以容纳更多信息
        self.root.resizable(False, False)

        pygame.mixer.init()
        
        # 核心状态变量
        self.target_image = None
        self.tk_preview = None # 保存图片引用
        self.audio_path = None
        self.is_running = False
        self.is_preview_hidden = False # V3新增：预览隐藏状态
        self.last_detect_time = None   # V3新增：上次检测时间
        
        # UI 绑定变量
        self.scan_freq = tk.IntVar(value=1)
        self.confidence_val = tk.DoubleVar(value=0.85)
        self.play_mode = tk.StringVar(value="times")
        self.play_value = tk.DoubleVar(value=1)
        self.btn_preview_text = tk.StringVar(value="👁 隐藏预览") # 按钮文字
        
        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill="both", expand=True)

        # --- 1. 目标图像区域 ---
        group_img = ttk.LabelFrame(main_frame, text=" 1. 监控目标 ", padding=10)
        group_img.pack(fill="x", pady=5)

        # 按钮行 (截图 / 导入 / 隐藏)
        btn_frame = ttk.Frame(group_img)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(btn_frame, text="✀ 截图", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="📂 导入", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=2)
        # V3 新增：隐藏预览按钮
        self.btn_toggle = ttk.Button(btn_frame, textvariable=self.btn_preview_text, command=self.toggle_preview_visibility)
        self.btn_toggle.pack(side="left", fill="x", expand=True, padx=(2, 0))

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

        mode_row = ttk.Frame(group_audio)
        mode_row.pack(fill="x", pady=(5, 0))
        ttk.Radiobutton(mode_row, text="播放次数:", variable=self.play_mode, value="times").pack(side="left")
        ttk.Spinbox(mode_row, from_=1, to=10, width=5, textvariable=self.play_value).pack(side="left", padx=5)
        ttk.Label(mode_row, text="   |   ").pack(side="left")
        ttk.Radiobutton(mode_row, text="持续时长(秒):", variable=self.play_mode, value="duration").pack(side="left")
        ttk.Spinbox(mode_row, from_=1, to=60, width=5, textvariable=self.play_value).pack(side="left", padx=5)

        # --- 3. 检测参数 ---
        group_settings = ttk.LabelFrame(main_frame, text=" 3. 运行参数 ", padding=10)
        group_settings.pack(fill="x", pady=5)

        f_row = ttk.Frame(group_settings)
        f_row.pack(fill="x", pady=5)
        ttk.Label(f_row, text="检测间隔 (秒):", width=12).pack(side="left")
        ttk.Scale(f_row, from_=1, to=10, variable=self.scan_freq, orient="horizontal", length=200, command=lambda v: self.scan_freq.set(int(float(v)))).pack(side="left", padx=10)
        self.lbl_freq_val = ttk.Label(f_row, text="1 秒", width=5)
        self.lbl_freq_val.pack(side="left")
        self.scan_freq.trace_add("write", lambda *args: self.lbl_freq_val.config(text=f"{self.scan_freq.get()} 秒"))

        c_row = ttk.Frame(group_settings)
        c_row.pack(fill="x", pady=5)
        ttk.Label(c_row, text="匹配严格度:", width=12).pack(side="left")
        ttk.Scale(c_row, from_=0.5, to=0.99, variable=self.confidence_val, orient="horizontal", length=200).pack(side="left", padx=10)
        self.lbl_conf_val = ttk.Label(c_row, text="0.85")
        self.lbl_conf_val.pack(side="left")
        self.confidence_val.trace_add("write", lambda *args: self.lbl_conf_val.config(text=f"{self.confidence_val.get():.2f}"))

        # --- 4. 底部控制 ---
        self.btn_control = tk.Button(main_frame, text="启动监控", command=self.toggle_detection,
                                     bg="#007bff", fg="white", font=("Microsoft YaHei UI", 14, "bold"),
                                     relief="flat", height=2)
        self.btn_control.pack(fill="x", pady=(20, 0))

        # 状态栏
        self.status_bar = tk.Label(self.root, text="就绪 - 等待指令", bd=1, relief="sunken", anchor="w", bg="#e9ecef", padx=5, font=("Arial", 9))
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
        self.last_detect_time = None # 重置检测时间
        self.status_bar.config(text=f"目标已加载: {img.shape[1]}x{img.shape[0]}像素", bg="#e9ecef")

        # 处理显示图片
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img_rgb)
        
        container_w, container_h = 460, 180
        im_pil.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
        
        self.tk_preview = ImageTk.PhotoImage(im_pil)
        
        # 默认重置为显示状态
        self.is_preview_hidden = False
        self.update_preview_visibility()

    def toggle_preview_visibility(self):
        """切换预览图的显示/隐藏，防止自识别"""
        if self.target_image is None:
            return
        self.is_preview_hidden = not self.is_preview_hidden
        self.update_preview_visibility()

    def update_preview_visibility(self):
        """根据 is_preview_hidden 刷新界面"""
        if self.target_image is None:
            self.btn_preview_text.set("👁 隐藏预览")
            return

        if self.is_preview_hidden:
            # 隐藏模式：移除图片，显示占位文字
            self.lbl_preview.config(image="", text="[ 预览已隐藏 ]\n\n防止程序扫描到自身界面造成误报", fg="#666")
            self.btn_preview_text.set("👁 显示预览")
        else:
            # 显示模式
            self.lbl_preview.config(image=self.tk_preview, text="")
            self.btn_preview_text.set("👁 隐藏预览")

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
            self.status_bar.config(text="监控已停止", bg="#e9ecef")
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
                
                # 截图 & 转换
                sct_img = sct.grab(monitor)
                screen_np = np.array(sct_img)
                screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGRA2GRAY)
                
                try:
                    # 模板匹配
                    res = cv2.matchTemplate(screen_gray, target_gray, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    threshold = self.confidence_val.get()
                    
                    if max_val >= threshold:
                        # 记录时间
                        self.last_detect_time = time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 构建警报信息 (带坐标)
                        msg = f"⚠ 目标发现! 相似度:{max_val:.1%} @ 坐标(X:{max_loc[0]}, Y:{max_loc[1]})"
                        
                        # UI更新
                        self.root.after(0, lambda m=msg: self.status_bar.config(text=m, bg="#ffc107", fg="black"))
                        
                        if not pygame.mixer.music.get_busy():
                            self.play_sound()
                    else:
                        # 未找到时的信息构建
                        msg = f"搜索中... (当前最高相似度: {max_val:.1%})"
                        
                        # 如果有历史记录，追加显示
                        if self.last_detect_time:
                            msg += f" | 上次发现于: {self.last_detect_time}"
                        
                        self.root.after(0, lambda m=msg: self.status_bar.config(text=m, bg="#e9ecef", fg="black"))
                        
                except Exception as e:
                    print(f"CV Error: {e}")
                
                # 频率控制
                process_time = time.time() - start_ts
                wait_time = max(0.1, self.scan_freq.get() - process_time)
                time.sleep(wait_time)

if __name__ == "__main__":
    root = tk.Tk()
    app = DetectorApp(root)
    root.mainloop()
