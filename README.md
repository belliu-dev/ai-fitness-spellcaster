# AI Fitness Coach — Setup & Run Guide

## What It Does
- Opens your webcam in a live window
- Draws a colour-coded skeleton over your body:
  - **Green** = joints/limbs in correct position
  - **Red**   = joints/limbs with a form issue
- Detects and counts **reps** for squats and pushups
- Pops up a **warning window** describing the issue
- Speaks feedback aloud via **text-to-speech**
- Shows a **side HUD** with live angle data, rep count, and issues

### Modes
| Key | Mode | What it checks |
|-----|------|----------------|
| `S` | Squat | Knee angle, back lean, knee cave |
| `P` | Pushup | Elbow angle, body line (hips), neck |
| `O` | Posture | Head forward lean, shoulder tilt, spine |

Press `Q` to quit.

---

## Prerequisites
- **Python 3.9 – 3.11** (MediaPipe does not yet support 3.12+ on all platforms)
- A working **webcam**
- **VSCode** with the Python extension installed

---

## Step-by-Step Setup in VSCode

### 1 — Open the project folder
1. Put both `ai_fitness_coach.py` and `requirements.txt` in the same folder (e.g. `C:\Users\You\fitness_coach\`).
2. In VSCode: **File → Open Folder** → select that folder.

### 2 — Create a virtual environment (recommended)
Open the VSCode **Terminal** (`Ctrl + ~`) and run:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt.

### 3 — Install dependencies
```bash
pip install -r requirements.txt
```

This installs:
- `mediapipe` — Google's pose-estimation library
- `opencv-python` — camera capture & drawing
- `numpy` — angle calculations

> **macOS users**: if TTS doesn't work, run `pip install pyobjc` as well.

### 4 — Run the program
```bash
python spellcasterv4_final.py
```

A window titled **"AI Fitness Coach"** will open showing your webcam feed.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No module named mediapipe` | Make sure the venv is activated and you ran `pip install -r requirements.txt` |
| Camera doesn't open | Try changing `cv2.VideoCapture(0)` to `cv2.VideoCapture(1)` in the script |
| TTS crashes on Windows | Run `pip install pypiwin32` |
| `Could not find a version that satisfies mediapipe` (Python 3.12+) | Downgrade to Python 3.11 |
| Skeleton not visible | Make sure you're well-lit and your full upper/lower body is visible |

---

## Jetson Nano Notes
When you move to the Jetson Nano:
- Replace `cv2.VideoCapture(0)` with your CSI camera pipeline string, e.g.:
  ```python
  cap = cv2.VideoCapture(
      "nvarguscamerasrc ! video/x-raw(memory:NVMM),width=1280,height=720,"
      "format=NV12,framerate=30/1 ! nvvidconv ! video/x-raw,format=BGRx ! "
      "videoconvert ! video/x-raw,format=BGR ! appsink", cv2.CAP_GSTREAMER)
  ```
- Set `model_complexity=0` in the `mp_pose.Pose(...)` call for better performance on the nano.
- `pyttsx3` may need `espeak` installed: `sudo apt install espeak`
