# 🎯 PixAlert – Treasure Hunter

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![GUI](https://img.shields.io/badge/GUI-Tkinter-success)
![OpenCV](https://img.shields.io/badge/OpenCV-Template%20Matching-red)
![Status](https://img.shields.io/badge/Status-Stable-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

**PixAlert – Treasure Hunter** is a lightweight **real-time screen detection and alert tool** based on **OpenCV template matching**.  
It continuously monitors your screen, detects a predefined visual target, and triggers **sound alerts**, **auto-clicks**, and **visual feedback** when the target appears.

Designed for:
- Game farming & loot monitoring
- UI element detection
- Automation assistance
- Visual event alerting

---

## ✨ Features

- 🖼 **Screen Snipping & Image Import**
  - Snip any on-screen region as the detection target
  - Import images (`png / jpg / bmp`) directly

- 🔍 **Real-Time Template Matching**
  - Uses OpenCV `TM_CCOEFF_NORMED`
  - Adjustable confidence threshold

- 🔔 **Smart Audio Alerts**
  - Custom success sound
  - Optional fail sound
  - Play by **count** or **duration**
  - System beep fallback

- 🖱 **Auto Click**
  - Automatically clicks the detected target center
  - DPI-aware for accurate positioning

- 📜 **Live Event Log**
  - Timestamped detection events
  - Success highlighting

- 🎛 **Fine-Grained Controls**
  - Adjustable scan interval
  - Detection confidence slider
  - Toggle preview to avoid self-detection

- 🧠 **Anti-Spam Logic**
  - Prevents duplicate triggers on the same target
  - Cooldown-based detection logic
