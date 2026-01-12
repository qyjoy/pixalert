# 🎯 PixAlert – Treasure Hunter

<img width="1000" height="564" alt="computer-vision-banner" src="https://github.com/user-attachments/assets/951a3cb7-e5bb-4272-a30d-88c25ad70e28" />

![1cau7cb4ji6f1](https://github.com/user-attachments/assets/4b9a9f79-cb98-4bf1-bcd4-578f3a4820fe)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![GUI](https://img.shields.io/badge/GUI-Tkinter-success)
![OpenCV](https://img.shields.io/badge/OpenCV-Template%20Matching-red)
![Status](https://img.shields.io/badge/Status-Stable-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

**PixAlert – Treasure Hunter** is a lightweight **real-time screen detection and alert tool** based on **OpenCV template matching**.  
It continuously monitors your screen, detects a predefined visual target, and triggers **sound alerts**, **auto-clicks**, and **visual feedback** when the target appears.

<img width="522" height="951" alt="image" src="https://github.com/user-attachments/assets/57c15c28-ccd6-4b9c-bb9f-0540930b1c9b" />

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
