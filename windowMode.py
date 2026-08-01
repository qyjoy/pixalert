import time
import win32gui
import win32ui
import win32con
import win32process
import psutil
import cv2
import numpy as np
import ctypes


def get_pids_by_name(process_name):
    """获取所有同名进程的 PID"""
    pids = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                pids.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def get_main_hwnd(pids):
    """根据 PIDs 获取对应面积最大的主窗口句柄"""
    hwnds = []
    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in pids:
            hwnds.append(hwnd)
    
    win32gui.EnumWindows(callback, None)

    best_hwnd = None
    max_area = -1
    for h in hwnds:
        l, t, r, b = win32gui.GetWindowRect(h)
        # 如果是最小化状态，赋予一个极大的假面积使其成为候选
        area = (r - l) * (b - t) if not win32gui.IsIconic(h) else 9999999
        if area > max_area:
            max_area = area
            best_hwnd = h

    return best_hwnd


def get_render_child_hwnd(parent_hwnd):
    """
    【核心优化】自动往下钻取，寻找模拟器内部真正的渲染子窗口
    这样不仅后台抓取成功率更高，还能自动裁切掉模拟器的侧边栏和标题栏
    """
    child_hwnds = []
    def child_callback(hwnd, _):
        child_hwnds.append(hwnd)
        return True
    
    try:
        win32gui.EnumChildWindows(parent_hwnd, child_callback, None)
    except Exception:
        pass
    
    # 找到面积最大的子窗口，通常就是游戏画面本身 (RenderWindow / sub-canvas)
    best_child = parent_hwnd
    max_area = 0
    for ch in child_hwnds:
        l, t, r, b = win32gui.GetWindowRect(ch)
        area = (r - l) * (b - t)
        if area > max_area:
            max_area = area
            best_child = ch
            
    return best_child


def wake_up_silently(hwnd):
    """
    【核心优化】静默唤醒：如果窗口最小化，让它在后台悄悄展开，绝对不抢夺用户的当前焦点
    """
    if win32gui.IsIconic(hwnd):
        # SW_SHOWNOACTIVATE = 4 : 按最近的大小和位置显示窗口，但不激活（不抢焦点）
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        time.sleep(0.3) # 稍微等待 DWM 重新为其分配渲染缓冲区


def capture_bg_window(hwnd):
    """使用 DWM 缓冲区进行纯后台抓取，支持 GPU 加速窗口"""
    # 获取真正的客户区大小（去除系统阴影等干扰）
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    # 标志位 3 (PW_CLIENTONLY | PW_RENDERFULLCONTENT)
    # 作用：纯后台强制抓取 GPU 硬件加速的内部客户区画面
    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

    img = None
    if result == 1:
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8).copy()
        img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)
        # 转为 BGR 格式丢弃透明通道，防止 OpenCV 弹窗颜色异常
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    
    return img


def main():
    target = input("请输入要获取截图的进程名字 (例如 dnplayer.exe): ").strip()
    if not target:
        return

    print("查找进程窗口中...")
    pids = get_pids_by_name(target)
    if not pids:
        print("未找到该进程！")
        return

    main_hwnd = get_main_hwnd(pids)
    if not main_hwnd:
        print("未找到该进程对应的可见主窗口！")
        return

    # 1. 静默唤醒（哪怕它最小化了，也不会弹到你脸上）
    wake_up_silently(main_hwnd)

    # 2. 穿透寻找内部真实的渲染画布窗口
    render_hwnd = get_render_child_hwnd(main_hwnd)
    print(f"定位成功！底层渲染句柄: {hex(render_hwnd)}")

    # 3. 纯后台静默截取
    img = capture_bg_window(render_hwnd)

    if img is None or np.mean(img) < 2.0:
        print("后台截取失败或画面全黑，请检查程序是否被彻底挂起。")
        return

    print("截图成功！按下任意按键关闭显示。")
    # 为了防止 CV2 弹窗抢焦点，这里我们甚至可以把 CV2 的窗口也设为不抢焦点
    cv2.namedWindow("Background Capture", cv2.WINDOW_AUTOSIZE)
    # 注意：cv2.imshow 本身在某些系统下仍可能轻微闪烁前台，但目标游戏窗口绝对不会弹出来了
    cv2.imshow("Background Capture", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
