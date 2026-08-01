# 🎯 PixAlert — Real-Time Screen Detection & Automation Toolkit

<img width="1672" height="941" alt="intro" src="https://github.com/user-attachments/assets/4b0a92f2-e2f6-4377-91a2-2ae9f8778d87" />

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![GUI](https://img.shields.io/badge/GUI-Tkinter-success)
![OpenCV](https://img.shields.io/badge/OpenCV-Template%20Matching-red)
![Status](https://img.shields.io/badge/Status-Stable-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

**PixAlert** is a desktop application that watches the screen — or a specific
background window — in real time, detects a set of reference images using
**OpenCV template matching**, and reacts automatically with a sound alert,
an animated on-screen highlight, and/or a simulated mouse click.

It started as a personal project to learn computer vision, multithreaded
GUI programming, and low-level Windows APIs, and grew into a small but
complete automation toolkit with a config system, background-window
capture, and per-target region optimization.

![demo](https://github.com/user-attachments/assets/8a3935da-2810-4b2d-bf18-96ff527481c6)
<img width="496" height="839" alt="image" src="https://github.com/user-attachments/assets/321e61fd-6886-4ffd-9571-5bebea0e24e8" />

Typical use cases:
- Watching a dashboard, HMI/SCADA panel, or monitoring feed for a status
  icon or alert light and triggering a notification
- Waiting for a UI element to appear/disappear before continuing an
  automated test or RPA-style workflow
- Lightweight visual QA: confirming a rendered element matches a reference
  image
- General "detect this, then do that" screen automation

---

## ✨ Features

**Detection**
- 🖼 **Snip or import targets** — drag-select any on-screen region as a
  detection target, or import existing image files (`png`/`jpg`/`bmp`),
  including batch import.
- 🔍 **Real-time template matching** — OpenCV `TM_CCOEFF_NORMED` with an
  adjustable confidence threshold and scan interval.
- 🪟 **Background window capture** — monitor a specific application
  window's contents (via `PrintWindow`) even while it's covered by other
  windows, so the target doesn't need to stay in focus. Includes automatic
  reconnect if the window is minimized, moved, or briefly closed and
  reopened.
- 🎯 **Per-target scan regions** — restrict matching to a sub-region of
  the frame for each target individually, cutting `matchTemplate` cost and
  CPU/thermal load on high-resolution screens.
- 🧠 **Multi-match mode** — detect and act on every non-overlapping match
  in the frame in a single pass, not just the single best one.

**Response actions**
- 🔔 **Configurable audio alerts** — separate success/failure sounds
  (custom file or system beep fallback).
- 🖱 **Auto-click** — clicks the detected target's center, with
  configurable click count and interval; DPI-aware for accurate cursor
  placement on high-DPI displays.
- 🎨 **Animated overlay** — a "lock-on" highlight with an optional
  confidence readout, rendered without stealing window focus.
- 📜 **Live, timestamped event log** with color-coded success/warning/
  failure entries, copyable to clipboard.

**Workflow / usability**
- 💾 **One-click JSON config import/export** — saves the entire target
  library (images included), audio paths, and all scan parameters, so the
  tool doesn't need to be reconfigured every session.
- 🎛 **Fine-grained controls** — scan interval, match threshold, overlay
  stroke width, preview visibility toggle (to avoid self-detection loops).
- ⌨️ **Global hotkey** (`Ctrl+Q`) to stop an active scan from anywhere.

---

## 🧩 Tech Stack

| Area | Tools / Libraries |
|---|---|
| Language | Python 3.9+ |
| GUI | Tkinter / ttk (custom canvas-based widgets, live animations) |
| Computer vision | OpenCV (template matching), NumPy, Pillow |
| Screen & window capture | `mss`, `pywin32` (`win32gui`, `win32ui`, `PrintWindow`) |
| Input simulation | `pyautogui` |
| Audio | `pygame.mixer` |
| Concurrency | Python `threading` (dedicated scan loop, click, and hotkey threads) |
| Persistence | JSON-based config schema with versioning |

---

## 🛠 What This Project Demonstrates

- Designing a **responsive multithreaded GUI**: the detection loop, click
  execution, and global hotkey listener all run on background threads and
  communicate safely with the Tkinter main thread via `root.after(...)`.
- Working with **low-level Windows APIs** to capture window contents that
  are occluded or not in focus, and to reconnect to windows that were
  moved, minimized, or recreated.
- Applying **classic computer vision** (template matching) with practical
  performance optimizations (region-of-interest cropping) instead of
  reaching for a heavier model where it isn't needed.
- Building a small, versioned **serialization format** (JSON + companion
  image assets) for saving and restoring complex application state.
- General **desktop application engineering**: custom UI components,
  animation, state management, and defensive error handling around OS/
  hardware-facing code.

---

## 📦 Requirements

- Windows (background-window capture uses `pywin32`, so this build is
  Windows-only as written)
- Python 3.9+

```bash
pip install opencv-python numpy mss pygame pillow pyautogui pywin32
```

## 🚀 Usage

```bash
python pixalert.py
```

1. Click **Snip** to select a region of the screen as a target image, or
   **Import** to load existing image files.
2. (Optional) Enable **Background window mode** and select the window(s)
   to monitor — detection then continues even if that window is covered.
3. Configure trigger actions (sound / auto-click / overlay) and scan
   parameters (interval, match threshold).
4. Click **Start scan**. Press **Ctrl+Q** at any time to stop.
5. Use **Save config / Load config** to persist your target library and
   settings between sessions.

Place an optional `ico.png` next to the script to use it as the window
icon; it's not required.

---

## 📌 Notes

This is a portfolio build shared for demonstration purposes. As with any
screen-automation tool, please only point it at applications where doing
so complies with that application's terms of service.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
