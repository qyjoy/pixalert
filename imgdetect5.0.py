import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog, Menu
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

pyautogui.PAUSE = 0.01

# 尝试设置DPI感知，防止高分屏模糊
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
        self.root.title("PixAlert - V5.0 pre-release By QyJoy") 
        self.root.geometry("500x775") # 宽度适当增加
        self.root.resizable(False, False)
        
        self.default_bg = self.root.cget("bg") 
        
        pygame.mixer.init()
        
        # --- 多目标数据 ---
        # 列表存储字典: [{'name': '...', 'image': np, 'gray': np, 'preview': tk, ...}]
        self.targets = [] 
        self.screenshot_counter = 0 

        # Audio
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
        self.enable_fail_sound = tk.BooleanVar(value=False)
        
        self.setup_ui()
        self.update_fail_audio_visibility()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        self.main_frame = tk.Frame(self.root, padx=15, pady=15, bg=self.default_bg)
        self.main_frame.pack(fill="both", expand=True)

        # --- 1. Target Management ---
        group_img = ttk.LabelFrame(self.main_frame, text=" 1. 目标库管理 ", padding=10)
        group_img.pack(fill="x", pady=5)

        # Buttons
        btn_frame = ttk.Frame(group_img)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(btn_frame, text="✀ 截图", command=self.start_snipping).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_frame, text="📂 导入", command=self.load_image_file).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="🗑 删除", command=self.delete_selected_target).pack(side="left", fill="x", expand=True, padx=2)
        
        self.btn_toggle = ttk.Button(btn_frame, textvariable=self.btn_preview_text, command=self.toggle_preview_visibility)
        self.btn_toggle.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Split View
        content_frame = tk.Frame(group_img)
        content_frame.pack(fill="x", expand=True)

        # Listbox (60% width roughly)
        list_frame = tk.Frame(content_frame)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # width=38 is approx 60% relative to the preview box
        self.target_listbox = tk.Listbox(list_frame, height=8, width=38, font=("Arial", 9), selectmode="SINGLE")
        self.target_listbox.pack(side="left", fill="both", expand=True)
        self.target_listbox.bind('<<ListboxSelect>>', self.on_target_select)
        
        # Right Click Menu
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="✎ 重命名", command=self.rename_selected_target)
        self.target_listbox.bind("<Button-3>", self.show_context_menu)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.config(command=self.target_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.target_listbox.config(yscrollcommand=scrollbar.set)

        # Preview Area (40% width roughly)
        self.preview_container = tk.Frame(content_frame, width=160, height=140, bg="#f0f0f0", relief="sunken", borderwidth=1)
        self.preview_container.pack(side="right", fill="none", expand=False)
        self.preview_container.pack_propagate(False)

        self.lbl_preview = tk.Label(self.preview_container, text="无预览", bg="#f0f0f0", fg="#888")
        self.lbl_preview.pack(fill="both", expand=True)

        # --- 2. Actions ---
        group_audio = ttk.LabelFrame(self.main_frame, text=" 2. 触发动作 ", padding=10)
        group_audio.pack(fill="x", pady=10)

        # Switches
        action_switch_row = ttk.Frame(group_audio)
        action_switch_row.pack(fill="x", pady=(0, 0))
        
        chk_sound = ttk.Checkbutton(action_switch_row, text="发现提示音", variable=self.enable_sound)
        chk_sound.pack(side="left", padx=(0, 5))
        
        chk_click = ttk.Checkbutton(action_switch_row, text="自动点击(多目标并发)", variable=self.enable_click)
        chk_click.pack(side="left", padx=(0, 5))

        chk_fail_sound = ttk.Checkbutton(
            action_switch_row,
            text="失败提示音",
            variable=self.enable_fail_sound,
            command=self.update_fail_audio_visibility
        )
        chk_fail_sound.pack(side="left")

        # Audio Files
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

        # Play Settings
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

        # --- Log Box ---
        group_log = ttk.LabelFrame(self.main_frame, text=" 事件日志 ", padding=1)
        group_log.pack(fill="both", expand=True, pady=5)
        
        # Log Controls (Clear Button)
        log_ctrl_frame = tk.Frame(group_log)
        log_ctrl_frame.pack(fill="x", side="bottom")
        
        ttk.Button(log_ctrl_frame, text="清除日志", command=self.clear_log, width=10).pack(side="right")
        
        self.log_text = scrolledtext.ScrolledText(group_log, height=6, state='disabled', font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True, side="top")
        self.log_text.tag_config("success", foreground="#009900", font=("Consolas", 8, "bold"))
        
        # --- Control ---
        self.btn_control = tk.Button(self.main_frame, text="开始扫描", command=self.toggle_detection,
                                     bg="#007bff", fg="white", font=("Microsoft YaHei UI", 14, "bold"),
                                     relief="flat", height=1)
        self.btn_control.pack(fill="x", pady=(1, 0))

        self.status_bar = tk.Label(self.root, text="就绪", bd=1, relief="sunken", anchor="w", bg="#e9ecef", padx=5, font=("Arial", 9))
        self.status_bar.pack(side="bottom", fill="x")
    
    def update_fail_audio_visibility(self):
        if self.enable_fail_sound.get():
            self.fail_audio_row.pack(fill="x", pady=(0, 0))
        else:
            self.fail_audio_row.pack_forget()

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

    # --- 目标管理 (新增/重命名/删除) ---

    def start_snipping(self):
        self.root.iconify()
        self.root.after(200, lambda: SnippingTool(self.root, lambda img: self.add_target(img, is_screenshot=True)))

    def load_image_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.bmp")])
        if file_path:
            img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            filename = os.path.basename(file_path)
            self.add_target(img, name=filename, is_screenshot=False)

    def add_target(self, img, name=None, is_screenshot=False):
        self.root.deiconify()
        if img is None: return

        # 智能命名逻辑
        if is_screenshot:
            self.screenshot_counter += 1
            final_name = f"截图 {self.screenshot_counter}"
        else:
            final_name = name if name else "导入图像"

        # 生成UI预览图
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img_rgb)
        container_w, container_h = 160, 140
        im_pil.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
        tk_preview = ImageTk.PhotoImage(im_pil)

        # 预计算灰度图 (性能优化)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 存入列表
        target_data = {
            'name': final_name,
            'image': img, 
            'gray': gray,
            'preview': tk_preview,
            'h': gray.shape[0],
            'w': gray.shape[1]
        }
        self.targets.append(target_data)
        
        self.refresh_target_listbox()
        
        # 自动选中最新添加的
        self.target_listbox.selection_clear(0, tk.END)
        self.target_listbox.selection_set(tk.END)
        self.on_target_select(None)
        
        self.log_msg(f"已添加: {final_name}")

    def refresh_target_listbox(self):
        """ 清空并重新根据列表顺序生成带编号的名称 """
        self.target_listbox.delete(0, tk.END)
        for i, t in enumerate(self.targets):
            # 格式: 1. 截图名称
            display_str = f"{i+1}. {t['name']} ({t['w']}x{t['h']})"
            self.target_listbox.insert(tk.END, display_str)
        
        self.status_bar.config(text=f"目标库数量: {len(self.targets)}", bg="#e9ecef")

    def delete_selected_target(self):
        selection = self.target_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选中一个目标。")
            return
        
        index = selection[0]
        removed_name = self.targets[index]['name']
        
        # 移除数据
        self.targets.pop(index)
        
        self.refresh_target_listbox()
        
        self.log_msg(f"已删除: {removed_name}")
        
        # UI清理
        if self.targets:
            new_index = min(index, len(self.targets) - 1)
            self.target_listbox.selection_set(new_index)
            self.on_target_select(None)
        else:
            self.lbl_preview.config(image="", text="无预览")

    def show_context_menu(self, event):
        try:
            # 自动选中右键点击的项
            index = self.target_listbox.nearest(event.y)
            self.target_listbox.selection_clear(0, tk.END)
            self.target_listbox.selection_set(index)
            self.on_target_select(None)
            
            # 弹出菜单
            self.context_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def rename_selected_target(self):
        selection = self.target_listbox.curselection()
        if not selection: return
        
        index = selection[0]
        current_name = self.targets[index]['name']
        
        new_name = simpledialog.askstring("重命名", "请输入新名称:", initialvalue=current_name, parent=self.root)
        
        if new_name and new_name.strip():
            self.targets[index]['name'] = new_name.strip()
            self.refresh_target_listbox()
            self.target_listbox.selection_set(index) # 保持选中
            self.log_msg(f"重命名 [{current_name}] -> [{new_name}]")

    def on_target_select(self, event):
        selection = self.target_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        target = self.targets[index]
        
        if self.is_preview_hidden:
            self.lbl_preview.config(image="", text="[ 预览已隐藏 ]", fg="#666")
        else:
            self.lbl_preview.config(image=target['preview'], text="")

    def toggle_preview_visibility(self):
        if not self.targets:
            return
        self.is_preview_hidden = not self.is_preview_hidden
        
        if self.is_preview_hidden:
            self.btn_preview_text.set("👁 显示预览")
        else:
            self.btn_preview_text.set("👁 隐藏预览")
            
        self.on_target_select(None)

    def load_success_audio(self):
        path = filedialog.askopenfilename(filetypes=[("音频文件", "*.mp3;*.wav")])
        if path:
            self.success_audio_path = path
            name = os.path.basename(path)
            if len(name) > 20: name = name[:17] + "..."
            self.lbl_audio_name.config(text=f"发现音频: {name}")

    def load_fail_audio(self):
        path = filedialog.askopenfilename(filetypes=[("音频文件", "*.mp3;*.wav")])
        if path:
            self.fail_audio_path = path
            name = os.path.basename(path)
            if len(name) > 20: name = name[:17] + "..."
            self.lbl_fail_audio_name.config(text=f"失败音频: {name}")

    def play_sound(self, is_success=True):
        try:
            target_path = self.success_audio_path if is_success else self.fail_audio_path
            
            if target_path:
                pygame.mixer.music.load(target_path)
            else:
                if os.name == 'nt':
                    import winsound
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

    def trigger_visual_alert(self):
        """ 触发五彩闪烁 (Red -> Blue -> Green) 不阻塞主线程 """
        def set_bg(c):
            try:
                self.root.configure(bg=c)
                self.main_frame.configure(bg=c)
            except: pass

        # 使用 root.after 确保UI更新在主线程且有间隔
        self.root.after(0, lambda: set_bg("#ff3333"))   # Red
        self.root.after(100, lambda: set_bg("#3333ff")) # Blue
        self.root.after(200, lambda: set_bg("#33ff33")) # Green
        self.root.after(300, lambda: set_bg(self.default_bg)) # Restore

    def perform_click(self, monitor, match_loc, h, w):
        try:
            center_x = monitor['left'] + match_loc[0] + w // 2
            center_y = monitor['top'] + match_loc[1] + h // 2
            
            pyautogui.moveTo(center_x, center_y)
            pyautogui.mouseDown()
            time.sleep(0.01) # 保持按下一小段时间
            pyautogui.mouseUp()

            return (center_x, center_y)
        except Exception as e:
            self.log_msg(f"点击失败: {e}")
            return None

    def toggle_detection(self):
        if self.is_running:
            self.is_running = False
            self.btn_control.config(text="开始扫描", bg="#007bff")
            self.status_bar.config(text="扫描已停止", bg="#e9ecef")
            self.log_msg("扫描已停止。")
            pygame.mixer.music.stop()
        else:
            if not self.targets:
                messagebox.showwarning("错误", "目标库为空，请先添加至少一个目标！")
                return
            
            self.is_running = True
            self.btn_control.config(text="🛑 停止运行", bg="#dc3545")
            self.log_msg(f"扫描已启动 - 多目标并行检测")
            
            t = threading.Thread(target=self.loop_detection)
            t.daemon = True
            t.start()

    def loop_detection(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            
            def set_status(text, color="#e9ecef"):
                self.root.after(0, lambda: self.status_bar.config(text=text, bg=color, fg="black"))

            while self.is_running:
                start_ts = time.time()
                
                current_targets = list(self.targets)
                
                if not current_targets:
                    set_status("警告: 目标库为空", "#ffcccc")
                    time.sleep(1)
                    continue

                sct_img = sct.grab(monitor)
                screen_np = np.array(sct_img)
                screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGRA2GRAY)
                
                threshold = self.confidence_val.get()
                
                found_matches = []
                frame_max_val = 0.0 # 用于记录当前画面最高相似度(无论是否匹配)
                
                for t in current_targets:
                    try:
                        res = cv2.matchTemplate(screen_gray, t['gray'], cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                        
                        if max_val > frame_max_val:
                            frame_max_val = max_val

                        if max_val >= threshold:
                            found_matches.append({
                                'name': t['name'],
                                'val': max_val,
                                'loc': max_loc,
                                'h': t['h'],
                                'w': t['w']
                            })
                    except: pass

                # 处理结果
                if found_matches:
                    self.last_detect_time = time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 1. 触发视觉 (非阻塞)
                    self.trigger_visual_alert()

                    # 2. 触发音频 (非阻塞)
                    if self.enable_sound.get():
                        if not pygame.mixer.music.get_busy():
                            self.play_sound(is_success=True)

                    # 3. 处理每个匹配 (日志 + 点击)
                    for fm in found_matches:
                        log_str = f"发现[{fm['name']}] ({fm['val']:.1%})"
                        self.root.after(0, lambda m=log_str: self.log_msg(m, "success"))
                        
                        # 自动点击 (顺序执行，互不干扰)
                        if self.enable_click.get():
                            self.perform_click(monitor, fm['loc'], fm['h'], fm['w'])
                    
                    # 更新状态栏
                    status_text = f"发现 {len(found_matches)} 个目标! (最高: {frame_max_val:.1%})"
                    set_status(status_text, "#ffc107")

                else:
                    # 未发现
                    msg = f"扫描中... (当前最大: {frame_max_val:.1%})"
                    if self.last_detect_time:
                        msg += f" | 上次命中: {self.last_detect_time}"
                    set_status(msg, "#e9ecef")
                    
                    if self.enable_fail_sound.get():
                        if not pygame.mixer.music.get_busy():
                            self.play_sound(is_success=False)
                
                process_time = time.time() - start_ts
                wait_time = max(0.1, self.scan_freq.get() - process_time)
                time.sleep(wait_time)

if __name__ == "__main__":
    root = tk.Tk()
    app = DetectorApp(root)
    root.mainloop()