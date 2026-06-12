"""

  FIREBALL   — raise BOTH arms above your head (Y shape)
   SHIELD     — extend BOTH arms straight out to sides (T shape)
    LIGHTNING  — raise your RIGHT KNEE high
    FREEZE     — raise your LEFT KNEE high
  COIN GRAB  — jump / rise on tiptoes (hips move up quickly)

Run:  
python spellcasterv4_final.py
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import time
import random
import threading
import subprocess
import platform

# ─────────────────────────────────────────────────────────
# COLOURS (BGR)
# ─────────────────────────────────────────────────────────
BLACK       = (0,   0,   0)
WHITE       = (255,255,255)
NEON_CYAN   = (255,230, 30)
NEON_GREEN  = ( 50,255, 80)
NEON_PINK   = ( 80, 50,255)
NEON_YELLOW = (  0,230,255)
NEON_ORANGE = (  0,140,255)
NEON_PURPLE = (200,  0,200)
DARK_BG     = ( 10,  8, 20)
GOLD        = ( 30,215,255)
RED         = ( 30, 30,220)
SPELL_COLORS = {
    "fireball":   (  0,  60, 255),   # BGR → vivid RED/ORANGE
    "shield":     ( 20, 220,  20),   # BGR → vivid GREEN
    "lightning":  (  0, 220, 220),   # BGR → vivid YELLOW
    "freeze":     (255,  80,  20),   # BGR → vivid BLUE
    "jump":       ( 30, 220, 255),   # BGR → GOLD
    "dark_bolt":  ( 60,   0, 120),   # BGR → deep PURPLE/BLACK
    "none":       ( 80,  80,  80),   # grey
}

# ─────────────────────────────────────────────────────────
# TTS (macOS say / pyttsx3 fallback)
# ─────────────────────────────────────────────────────────
_tts_lock   = threading.Lock()
_last_spoken: dict = {}
_SPEAK_COOL = 4.0

def speak(msg: str, key: str = "") -> None:
    now = time.time()
    k = key or msg
    with _tts_lock:
        if now - _last_spoken.get(k, 0) < _SPEAK_COOL:
            return
        _last_spoken[k] = now
    def _run():
        try:
            if platform.system() == "Darwin":
                subprocess.run(["say","-r","190", msg], timeout=6, capture_output=True)
            else:
                import pyttsx3
                e = pyttsx3.init(); e.setProperty("rate",170); e.say(msg); e.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

# ─────────────────────────────────────────────────────────
# GEOMETRY HELPERS
# ─────────────────────────────────────────────────────────
def angle_between(a, b, c) -> float:
    ba = np.array([a[0]-b[0], a[1]-b[1]], dtype=float)
    bc = np.array([c[0]-b[0], c[1]-b[1]], dtype=float)
    cos = np.dot(ba,bc)/(np.linalg.norm(ba)*np.linalg.norm(bc)+1e-6)
    return math.degrees(math.acos(np.clip(cos,-1,1)))

def lm_px(lm, w, h):
    return int(lm.x*w), int(lm.y*h)

def pt(lms, idx, w, h):
    l = lms[idx]
    return (int(l.x*w), int(l.y*h)), l.visibility

# ─────────────────────────────────────────────────────────
# PARTICLE SYSTEM
# ─────────────────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, color, size=8, life=30, vx=None, vy=None):
        self.x, self.y   = float(x), float(y)
        self.color       = color
        self.size        = size
        self.life        = life
        self.max_life    = life
        self.vx          = vx if vx is not None else random.uniform(-6, 6)
        self.vy          = vy if vy is not None else random.uniform(-10, -2)

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.4       # gravity
        self.life -= 1

    def draw(self, frame):
        alpha = self.life / self.max_life
        r = max(1, int(self.size * alpha))
        col = tuple(int(c * alpha) for c in self.color)
        cv2.circle(frame, (int(self.x), int(self.y)), r, col, -1, cv2.LINE_AA)

class ParticleSystem:
    def __init__(self):
        self.particles = []

    def burst(self, x, y, color, n=30, size=10):
        for _ in range(n):
            self.particles.append(Particle(x, y, color, size,
                                           random.randint(20,45)))

    def trail(self, x, y, color, n=5):
        for _ in range(n):
            self.particles.append(Particle(x, y, color,
                                           random.randint(4,8),
                                           random.randint(12,22),
                                           random.uniform(-3,3),
                                           random.uniform(-4,0)))

    def update_draw(self, frame):
        alive = []
        for p in self.particles:
            p.update()
            if p.life > 0:
                p.draw(frame)
                alive.append(p)
        self.particles = alive

# ─────────────────────────────────────────────────────────
# ENEMY CLASS
# ─────────────────────────────────────────────────────────
ENEMY_EMOJIS = ["👾","👹","🤖","💀","🐉","👻"]
ENEMY_TYPES  = ["slime","orc","robot","skull","dragon","ghost"]

class Enemy:
    def __init__(self, w, h, wave=1):
        self.w, self.h = w, h
        self.side      = random.choice(["left","right"])
        self.x         = 60     if self.side == "left" else w-60
        self.y         = random.randint(int(h*0.15), int(h*0.65))
        self.etype     = random.choice(ENEMY_TYPES)
        speed_base     = 1.5 + wave * 0.25
        self.speed     = random.uniform(speed_base, speed_base+1.5)
        self.hp        = 1 + (wave // 3)
        self.max_hp    = self.hp
        self.alive     = True
        self.hit_flash = 0
        self.size      = random.randint(38, 55)
        # Required spell to defeat
        self.weakness  = random.choice(["fireball","lightning","freeze","shield","dark_bolt"])
        self.color     = SPELL_COLORS[self.weakness]
        self.age       = 0

    def update(self, player_x, player_y):
        self.age += 1
        dx = player_x - self.x
        dy = player_y - self.y
        dist = math.hypot(dx, dy) + 1e-6
        self.x += self.speed * dx / dist
        self.y += self.speed * dy / dist
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def draw(self, frame):
        if not self.alive:
            return
        flash = self.hit_flash > 0
        col   = WHITE if flash else self.color
        # Body circle
        cv2.circle(frame, (int(self.x), int(self.y)), self.size, col, -1, cv2.LINE_AA)
        cv2.circle(frame, (int(self.x), int(self.y)), self.size, WHITE, 2, cv2.LINE_AA)
        # Eyes
        ex = int(self.x) - 10
        ey = int(self.y) - 8
        cv2.circle(frame, (ex, ey),      6, BLACK, -1)
        cv2.circle(frame, (ex+20, ey),   6, BLACK, -1)
        cv2.circle(frame, (ex+2, ey),    2, WHITE, -1)
        cv2.circle(frame, (ex+22, ey),   2, WHITE, -1)
        # Mouth
        cv2.ellipse(frame, (int(self.x), int(self.y)+10),
                    (12,7), 0, 0, 180, BLACK, -1)
        # Weakness label
        label = {"fireball":"","lightning":"","freeze":"","shield":"","dark_bolt":"🖤"}.get(self.weakness,"?")
        cv2.putText(frame, self.weakness[:3].upper(),
                    (int(self.x)-22, int(self.y)-self.size-8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.5, col, 1, cv2.LINE_AA)
        # HP bar
        bw = self.size*2
        bx = int(self.x) - self.size
        by = int(self.y) - self.size - 24
        cv2.rectangle(frame, (bx, by), (bx+bw, by+8), (40,40,40), -1)
        fill = int(bw * self.hp / self.max_hp)
        cv2.rectangle(frame, (bx, by), (bx+fill, by+8), NEON_GREEN, -1)

    def hit(self, spell):
        if spell == self.weakness:
            self.hp -= 1
            self.hit_flash = 8
            if self.hp <= 0:
                self.alive = False
                return "kill"
            return "hit"
        else:
            self.hit_flash = 5
            return "wrong"

    def dist_to(self, x, y):
        return math.hypot(self.x-x, self.y-y)

# ─────────────────────────────────────────────────────────
# COIN CLASS
# ─────────────────────────────────────────────────────────
class Coin:
    def __init__(self, w, h):
        self.x     = random.randint(int(w*0.15), int(w*0.85))
        self.y     = random.randint(int(h*0.10), int(h*0.75))
        self.r     = 18
        self.alive = True
        self.age   = 0
        self.bob   = random.uniform(0, math.pi*2)

    def update(self):
        self.age += 1

    def draw(self, frame):
        bob_y = int(self.y + 5*math.sin(self.age*0.08 + self.bob))
        glow_size = self.r + 6 + int(3*math.sin(self.age*0.12))
        cv2.circle(frame, (self.x, bob_y), glow_size, (0,160,220), -1, cv2.LINE_AA)
        cv2.circle(frame, (self.x, bob_y), self.r,    GOLD,        -1, cv2.LINE_AA)
        cv2.circle(frame, (self.x, bob_y), self.r,    WHITE,        2, cv2.LINE_AA)
        cv2.putText(frame, "$", (self.x-7, bob_y+6),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, BLACK, 2, cv2.LINE_AA)

    def dist_to(self, x, y):
        return math.hypot(self.x-x, self.y-y)

# ─────────────────────────────────────────────────────────
# POWERUP CLASS
# ─────────────────────────────────────────────────────────
class PowerUp:
    TYPES = ["star","nuke","heart"]
    COLORS = {"star":NEON_YELLOW,"nuke":NEON_PINK,"heart":RED}
    LABELS = {"star":"★ x2 SCORE!","nuke":"💥 NUKE!","heart":"♥ +HEALTH!"}

    def __init__(self, w, h):
        self.kind  = random.choice(self.TYPES)
        self.x     = random.randint(int(w*0.2), int(w*0.8))
        self.y     = random.randint(int(h*0.1), int(h*0.7))
        self.r     = 22
        self.alive = True
        self.age   = 0
        self.life  = 200   # frames before despawn

    def update(self):
        self.age  += 1
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    def draw(self, frame):
        if not self.alive:
            return
        alpha_fade = min(1.0, self.life/40)
        col = tuple(int(c*alpha_fade) for c in self.COLORS[self.kind])
        glow = self.r + 8 + int(4*math.sin(self.age*0.15))
        cv2.circle(frame, (self.x,self.y), glow, col, 2, cv2.LINE_AA)
        cv2.circle(frame, (self.x,self.y), self.r, col, -1, cv2.LINE_AA)
        cv2.circle(frame, (self.x,self.y), self.r, WHITE, 2, cv2.LINE_AA)
        symbol = {"star":"★","nuke":"☢","heart":"♥"}[self.kind]
        cv2.putText(frame, symbol, (self.x-12,self.y+8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, BLACK, 2, cv2.LINE_AA)
        


# bomb class
# ─────────────────────────────────────────────────────────
# BOMB CLASS
# ─────────────────────────────────────────────────────────
class Bomb:
    def __init__(self, w, h):
        self.x     = random.randint(int(w*0.15), int(w*0.85))
        self.y     = random.randint(int(h*0.10), int(h*0.75))
        self.r     = 20
        self.alive = True
        self.age   = 0
        self.life  = 250  # Bomb stays for about 8-10 seconds

    def update(self):
        self.age += 1
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    def draw(self, frame):
        # Pulsing red glow effect
        glow = self.r + 5 + int(5 * math.sin(self.age * 0.2))
        cv2.circle(frame, (self.x, self.y), glow, (0, 0, 180), -1, cv2.LINE_AA)
        # Bomb body
        cv2.circle(frame, (self.x, self.y), self.r, BLACK, -1, cv2.LINE_AA)
        cv2.circle(frame, (self.x, self.y), self.r, (50, 50, 50), 2, cv2.LINE_AA)
        # "Fuse" or Symbol
        cv2.putText(frame, "💣", (self.x-14, self.y+8), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, WHITE, 1, cv2.LINE_AA)

    def dist_to(self, x, y):
        return math.hypot(self.x-x, self.y-y)

# ─────────────────────────────────────────────────────────
# FLOATING TEXT
# ─────────────────────────────────────────────────────────
class FloatText:
    def __init__(self, x, y, text, color, size=0.8, life=55):
        self.x, self.y = x, y
        self.text      = text
        self.color     = color
        self.size      = size
        self.life      = life
        self.max_life  = life

    def update(self):
        self.y    -= 2
        self.life -= 1

    def draw(self, frame):
        alpha  = self.life / self.max_life
        col    = tuple(int(c*alpha) for c in self.color)
        thick  = max(1, int(2*alpha))
        cv2.putText(frame, self.text, (int(self.x), int(self.y)),
                    cv2.FONT_HERSHEY_DUPLEX, self.size, col, thick, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# POSE DETECTOR / SPELL RECOGNISER
# ─────────────────────────────────────────────────────────
class SpellDetector:
    LM = {
        "nose":0,
        "l_shoulder":11,"r_shoulder":12,
        "l_elbow":13,"r_elbow":14,
        "l_wrist":15,"r_wrist":16,
        "l_hip":23,"r_hip":24,
        "l_knee":25,"r_knee":26,
        "l_ankle":27,"r_ankle":28,
    }
    SPELL_HOLD    = 18   # frames to hold pose
    SPELL_COOLDOWN= 35

    def __init__(self):
        self._hold_spell  = "none"
        self._hold_frames = 0
        self._cooldown    = 0
        self._hip_hist    = []     # for jump detection
        self.last_cast    = "none"
        self.cast_ready   = False

    def _p(self, lms, name, w, h):
        lm = lms[self.LM[name]]
        return lm_px(lm, w, h), lm.visibility

    def detect(self, lms, w, h):
        """Returns detected spell string each frame (may be 'none')."""
        if self._cooldown > 0:
            self._cooldown -= 1

        lw, lvw = self._p(lms,"l_wrist",    w, h)
        rw, rvw = self._p(lms,"r_wrist",    w, h)
        ls, lsv = self._p(lms,"l_shoulder", w, h)
        rs, rsv = self._p(lms,"r_shoulder", w, h)
        lh, lhv = self._p(lms,"l_hip",      w, h)
        rh, rhv = self._p(lms,"r_hip",      w, h)
        lk, lkv = self._p(lms,"l_knee",     w, h)
        rk, rkv = self._p(lms,"r_knee",     w, h)
        nose,_  = self._p(lms,"nose",       w, h)

        if min(lvw,rvw,lsv,rsv) < 0.4:
            return "none", False

        mid_shoulder_y = (ls[1]+rs[1])//2
        mid_hip_y      = (lh[1]+rh[1])//2
        body_height    = max(1, mid_hip_y - mid_shoulder_y)

        # ── Jump detection (hip y moving upward quickly) ───────────
        self._hip_hist.append(mid_hip_y)
        if len(self._hip_hist) > 12:
            self._hip_hist.pop(0)
        jump = False
        if len(self._hip_hist) == 12:
            drop = self._hip_hist[0] - self._hip_hist[-1]  # y decreases upward
            jump = drop > body_height * 0.12

        # ─── FIREBALL: both wrists above nose (Y shape) ────────────
        fireball = (lw[1] < nose[1] - 20) and (rw[1] < nose[1] - 20)

        # ─── SHIELD: both wrists near shoulder height, arms spread ─
        lw_side = abs(lw[0] - ls[0]) > w*0.12
        rw_side = abs(rw[0] - rs[0]) > w*0.12
        lw_mid  = abs(lw[1] - mid_shoulder_y) < body_height*0.6
        rw_mid  = abs(rw[1] - mid_shoulder_y) < body_height*0.6
        shield  = lw_side and rw_side and lw_mid and rw_mid and not fireball

        # ─── LIGHTNING: Right knee raised (leg movement) ───────────
        lightning = (rk[1] < mid_hip_y - body_height * 0.15) and not fireball

        # ─── FREEZE: Left knee raised (leg movement) ───────────────
        freeze    = (lk[1] < mid_hip_y - body_height * 0.15) and not fireball

        # ─── DARK BOLT: Squat — hips drop low toward knees ─────────
        # Hip y drops significantly below shoulder baseline (hips near knee level)
        la, _  = self._p(lms, "l_ankle", w, h)
        ra, _  = self._p(lms, "r_ankle", w, h)
        mid_ankle_y = (la[1] + ra[1]) // 2
        mid_knee_y  = (lk[1] + rk[1]) // 2
        # In a squat: hips drop so mid_hip_y approaches mid_knee_y
        # body_height is shoulder→hip; we use ankle→shoulder as full leg reference
        full_height = max(1, mid_ankle_y - mid_shoulder_y)
        squat = (
            (mid_hip_y > mid_shoulder_y + full_height * 0.55) and   # hips very low
            not fireball and not shield
        )

        # Priority order
        if   fireball:   raw = "fireball"
        elif shield:     raw = "shield"
        elif lightning:  raw = "lightning"
        elif freeze:     raw = "freeze"
        elif squat:      raw = "dark_bolt"
        elif jump:       raw = "jump"
        else:            raw = "none"

        # Hold-to-cast logic
        if raw == self._hold_spell and raw != "none":
            self._hold_frames += 1
        else:
            self._hold_spell  = raw
            self._hold_frames = 1

        cast_fired = False
        if self._hold_frames >= self.SPELL_HOLD and self._cooldown == 0 and raw != "none":
            cast_fired         = True
            self.last_cast     = raw
            self._cooldown     = self.SPELL_COOLDOWN
            self._hold_frames  = 0

        return raw, cast_fired

    def hold_progress(self):
        return min(1.0, self._hold_frames / self.SPELL_HOLD)

    def on_cooldown(self):
        return self._cooldown > 0

# ─────────────────────────────────────────────────────────
# SKELETON DRAWING (coloured by spell)
# ─────────────────────────────────────────────────────────
CONNECTIONS = [
    (11,12),(11,13),(13,15),(12,14),(14,16),
    (11,23),(12,24),(23,24),(23,25),(24,26),(25,27),(26,28),
    (0,11),(0,12),
]

def draw_skeleton(frame, lms, w, h, spell_col):
    for ia, ib in CONNECTIONS:
        la, lb = lms[ia], lms[ib]
        if la.visibility < 0.35 or lb.visibility < 0.35:
            continue
        cv2.line(frame, lm_px(la,w,h), lm_px(lb,w,h), spell_col, 3, cv2.LINE_AA)
    for i in range(33):
        lm = lms[i]
        if lm.visibility < 0.35:
            continue
        cv2.circle(frame, lm_px(lm,w,h), 6, spell_col, -1, cv2.LINE_AA)
        cv2.circle(frame, lm_px(lm,w,h), 6, WHITE,     1, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# HEALTH BAR
# ─────────────────────────────────────────────────────────
def draw_health_bar(frame, x, y, w, h, current, maximum, label, col):
    cv2.rectangle(frame, (x,y), (x+w,y+h), (40,40,40), -1)
    fill = int(w * current / max(1, maximum))
    cv2.rectangle(frame, (x,y), (x+fill,y+h), col, -1)
    cv2.rectangle(frame, (x,y), (x+w,y+h), WHITE, 1)
    cv2.putText(frame, f"{label} {current}/{maximum}",
                (x, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# HUD DRAW
# ─────────────────────────────────────────────────────────
SPELL_ICONS = {
    "fireball":  "FIREBALL   — Both arms UP",
    "shield":    "SHIELD     — Arms spread sideways",
    "lightning": "LIGHTNING  — Raise RIGHT KNEE",
    "freeze":    "FREEZE     — Raise LEFT KNEE",
    "jump":      "GRAB COIN  — JUMP / rise up!",
    "dark_bolt": "DARK BOLT  — SQUAT down low!",
}

def draw_hud(frame, score, wave, player_hp, max_hp, spell, hold_prog, cooldown,
             score_mult, combo, w_frame, h_frame, remaining, best_score):
    # ── Top bar background ─────────────────────────────────────
    ov = frame.copy()
    cv2.rectangle(ov, (0,0), (w_frame,72), DARK_BG, -1)
    cv2.addWeighted(ov, 0.82, frame, 0.18, 0, frame)

    # Score
    cv2.putText(frame, f"SCORE: {score:06d}", (12, 32),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, GOLD, 2, cv2.LINE_AA)
    if score_mult > 1:
        cv2.putText(frame, f"x{score_mult}", (230,32),
                    cv2.FONT_HERSHEY_DUPLEX, 0.8, NEON_YELLOW, 2, cv2.LINE_AA)
    # Best
    cv2.putText(frame, f"BEST:{best_score:06d}", (12,60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160,160,160), 1, cv2.LINE_AA)

    # Wave + Countdown Timer
    secs_left = int(remaining) + 1
    timer_col = (50, 50, 220) if remaining <= 5 else \
                (0, 200, 220) if remaining <= 10 else \
                (150, 150, 150)
    cv2.putText(frame, f"WAVE {wave}", (w_frame//2-55, 32),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, NEON_CYAN, 2, cv2.LINE_AA)
    cv2.putText(frame, f"TIME: {secs_left}s", (w_frame//2-50, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, timer_col, 1, cv2.LINE_AA)

    # Combo
    if combo >= 3:
        combo_col = NEON_PINK if combo >= 7 else NEON_YELLOW
        cv2.putText(frame, f"COMBO x{combo}!", (w_frame//2+80, 38),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75, combo_col, 2, cv2.LINE_AA)

    # Player HP bar
    draw_health_bar(frame, w_frame-260, 10, 240, 22, player_hp, max_hp,
                    "❤ HP", NEON_GREEN if player_hp > max_hp//3 else RED)

    # ── Bottom spell panel ──────────────────────────────────────
    ph = 90
    ov2 = frame.copy()
    cv2.rectangle(ov2, (0, h_frame-ph), (w_frame, h_frame), DARK_BG, -1)
    cv2.addWeighted(ov2, 0.78, frame, 0.22, 0, frame)

    # Active spell display
    spell_col = SPELL_COLORS.get(spell, (100,100,100))
    if spell != "none":
        cv2.putText(frame, SPELL_ICONS.get(spell,""), (12, h_frame-58),
                    cv2.FONT_HERSHEY_DUPLEX, 0.62, spell_col, 1, cv2.LINE_AA)
        # Hold progress bar
        bar_w = int(300 * hold_prog)
        cv2.rectangle(frame, (12,h_frame-42), (312,h_frame-28), (50,50,50), -1)
        cv2.rectangle(frame, (12,h_frame-42), (12+bar_w,h_frame-28), spell_col, -1)
        cv2.putText(frame, "HOLD TO CAST...", (14,h_frame-31),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, WHITE, 1, cv2.LINE_AA)
    else:
        cv2.putText(frame, "STRIKE A SPELL POSE!", (12,h_frame-42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (120,120,120), 1, cv2.LINE_AA)

    # Cooldown indicator
    if cooldown:
        cv2.putText(frame, "RECHARGING...", (12, h_frame-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100,100,200), 1, cv2.LINE_AA)
    else:
        cv2.putText(frame, "READY TO CAST!", (12, h_frame-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, NEON_GREEN, 1, cv2.LINE_AA)

    # Legend (right side bottom)
    legend_x = w_frame - 380
    cv2.putText(frame, "SPELL GUIDE:", (legend_x, h_frame-70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180,180,180), 1, cv2.LINE_AA)
    lines = [
        ("FIREBALL",   "Both arms UP",        NEON_ORANGE),
        ("SHIELD",     "Arms spread OUT",      NEON_YELLOW),
        ("LIGHTNING",  "Raise RIGHT KNEE",     NEON_CYAN),
        ("FREEZE",     "Raise LEFT KNEE",      NEON_PURPLE),
        ("DARK BOLT",  "SQUAT low!",           SPELL_COLORS["dark_bolt"]),
    ]
    for i,(icon,desc,col) in enumerate(lines):
        cv2.putText(frame, f"{icon}: {desc}", (legend_x, h_frame-50+i*15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# SCREEN FLASH EFFECT
# ─────────────────────────────────────────────────────────
class ScreenFlash:
    def __init__(self):
        self.frames = 0
        self.color  = WHITE

    def trigger(self, color=WHITE, frames=8):
        self.frames = frames
        self.color  = color

    def apply(self, frame):
        if self.frames <= 0:
            return
        alpha = self.frames / 12
        ov = np.full_like(frame, self.color, dtype=np.uint8)
        cv2.addWeighted(ov, alpha*0.45, frame, 1-alpha*0.45, 0, frame)
        self.frames -= 1

# ─────────────────────────────────────────────────────────
# GAME STATE MACHINE
# ─────────────────────────────────────────────────────────
class Game:
    # (... same as before ...)
    MAX_HP        = 100
    WAVE_KILL_REQ = 5        # kills to advance wave
    COIN_SCORE    = 50
    KILL_SCORE    = 100
    WRONG_PENALTY = -5
    HP_DAMAGE     = 20 # 12
    COIN_SPAWN_INTERVAL = 120   # frames
    PU_SPAWN_INTERVAL   = 400
    GAME_DURATION       = 50    # seconds — game ends after this

    def __init__(self, w, h):
        self.w, self.h  = w, h
        self.reset()

    def reset(self):
        self.score       = 0
        self.best_score  = getattr(self, "best_score", 0)
        self.player_hp   = self.MAX_HP
        self.wave        = 1
        self.wave_kills  = 0
        self.enemies     : list[Enemy]   = []
        self.coins       : list[Coin]    = []
        self.powerups    : list[PowerUp] = []
        self.particles   = ParticleSystem()
        self.floats      : list[FloatText] = []
        self.flash       = ScreenFlash()
        self.score_mult  = 1
        self.mult_timer  = 0
        self.combo       = 0
        self.combo_timer = 0
        self.state       = "playing"   # playing | dead | countdown
        self.start_time  = time.time()
        self._frame      = 0
        self._enemy_timer= 0
        # Spawn first enemies
        for _ in range(2):
            self.enemies.append(Enemy(self.w, self.h, self.wave))
        self.coins.append(Coin(self.w, self.h))

    def _player_center(self, lms):
        """Use mid-hip as player avatar position."""
        try:
            lh = lms[23]; rh = lms[24]
            x = int((lh.x+rh.x)/2 * self.w)
            y = int((lh.y+rh.y)/2 * self.h)
            return x, y
        except Exception:
            return self.w//2, self.h//2

    def update(self, lms, spell_raw, cast_fired):
        if self.state != "playing":
            return

        self._frame += 1
        w, h = self.w, self.h

        # ── Time limit check ───────────────────────────────
        elapsed = time.time() - self.start_time
        if elapsed >= self.GAME_DURATION:
            self.state      = "timeup"
            self.best_score = max(self.score, self.best_score)
            speak("Time's up! Amazing run!", "timeup")
            return

        px, py = self._player_center(lms) if lms else (w//2, h//2)

        # ── Multiplier timer ───────────────────────────────
        if self.mult_timer > 0:
            self.mult_timer -= 1
        else:
            self.score_mult = 1

        # ── Combo timer ────────────────────────────────────
        if self.combo_timer > 0:
            self.combo_timer -= 1
        else:
            self.combo = 0

        # ── Coin spawn ─────────────────────────────────────
        if self._frame % self.COIN_SPAWN_INTERVAL == 0:
            self.coins.append(Coin(w, h))

        # ── Powerup spawn ──────────────────────────────────
        if self._frame % self.PU_SPAWN_INTERVAL == 0:
            self.powerups.append(PowerUp(w, h))

        # ── Enemy spawn ────────────────────────────────────
        self._enemy_timer += 1
        spawn_interval = max(60, 80 - self.wave*10) # 150 change spawn rate here!!!!------------------------------
        max_enemies    = min(3 + self.wave, 10)
        if self._enemy_timer >= spawn_interval and len(self.enemies) < max_enemies:
            self.enemies.append(Enemy(w, h, self.wave))
            self._enemy_timer = 0

        # ── Update enemies ─────────────────────────────────
        for e in self.enemies:
            e.update(px, py)
            if e.dist_to(px, py) < 50 + e.size:
                self.player_hp -= self.HP_DAMAGE
                self.particles.burst(px, py, RED, 20, 8)
                self.flash.trigger((0,0,255), 10)
                speak("Ouch!", "hit")
                e.alive = False   # enemy bounces back (simplification)
                if self.player_hp <= 0:
                    self.player_hp = 0
                    self.state     = "dead"
                    self.best_score= max(self.score, self.best_score)
                    speak("Game over! Great effort!", "dead")

        # ── Handle cast ────────────────────────────────────
        if cast_fired and lms:
            self._handle_cast(spell_raw, px, py)

        # ── Coin collection: jump or wrist near coin ───────
        if lms:
            lw,_ = pt(lms, 15, w, h)
            rw,_ = pt(lms, 16, w, h)
            for c in self.coins:
                if not c.alive:
                    continue
                for cx,cy in [lw, rw, (px,py)]:
                    if c.dist_to(cx, cy) < 55:
                        c.alive = False
                        pts = self.COIN_SCORE * self.score_mult
                        self.score += pts
                        self.particles.burst(c.x, c.y, GOLD, 18, 10)
                        self.floats.append(FloatText(c.x-20, c.y-20,
                                           f"+{pts} 💰", GOLD, 0.75))
                        speak("Coin!", "coin")
                        break

        # ── Powerup collection ─────────────────────────────
        if lms:
            for pu in self.powerups:
                if not pu.alive:
                    continue
                pu.update()
                if math.hypot(pu.x-px, pu.y-py) < 55:
                    self._collect_powerup(pu, px, py)

        # ── Wave advance ───────────────────────────────────
        if self.wave_kills >= self.WAVE_KILL_REQ * self.wave:
            self.wave       += 1
            self.wave_kills  = 0
            self.flash.trigger(NEON_CYAN, 14)
            self.floats.append(FloatText(w//2-100, h//2,
                               f"🌊 WAVE {self.wave}!", NEON_CYAN, 1.4, 90))
            speak(f"Wave {self.wave}! Get ready!", "wave")

        # ── Prune dead objects ─────────────────────────────
        self.enemies  = [e for e in self.enemies  if e.alive]
        self.coins    = [c for c in self.coins    if c.alive]
        self.powerups = [p for p in self.powerups if p.alive]

        # ── Update coins ───────────────────────────────────
        for c in self.coins:
            c.update()

        # ── Update floats ──────────────────────────────────
        for f in self.floats:
            f.update()
        self.floats = [f for f in self.floats if f.life > 0]

    def _handle_cast(self, spell, px, py):
        if not self.enemies:
            return
        nearest = min(self.enemies, key=lambda e: e.dist_to(px, py))
        result  = nearest.hit(spell)
        col     = SPELL_COLORS.get(spell, WHITE)

        if result == "kill":
            self.wave_kills += 1
            self.combo      += 1
            self.combo_timer = 90
            pts = self.KILL_SCORE * self.score_mult * max(1, self.combo//3)
            self.score += pts
            self.particles.burst(int(nearest.x), int(nearest.y), col, 40, 14)
            if spell == "dark_bolt":
                # Extra shadowy burst for dark spell
                self.particles.burst(int(nearest.x), int(nearest.y), (80, 0, 140), 30, 10)
                self.flash.trigger(SPELL_COLORS["dark_bolt"], 10)
                speak("Dark bolt! Obliterated!", "dark_kill")
            else:
                self.flash.trigger(col, 8)
                speak("Enemy defeated!", "kill")
            label = f"+{pts} {'COMBO!' if self.combo >= 3 else 'KILL!'}"
            self.floats.append(FloatText(int(nearest.x)-40, int(nearest.y)-30,
                               label, col, 0.9))
        elif result == "hit":
            self.particles.burst(int(nearest.x), int(nearest.y), col, 15, 8)
            self.floats.append(FloatText(int(nearest.x)-20,int(nearest.y)-20,
                               "HIT!", col, 0.65))
        else:
            self.floats.append(FloatText(int(nearest.x)-30,int(nearest.y)-20,
                               "WRONG SPELL!", NEON_PINK, 0.65))
            self.score += self.WRONG_PENALTY
            self.combo  = 0
            speak("Wrong spell!", "wrong")

    def _collect_powerup(self, pu, px, py):
        pu.alive = False
        self.particles.burst(pu.x, pu.y, PowerUp.COLORS[pu.kind], 35, 12)
        # self.particles.burst(pu.x, pu.y, self.PowerUp.COLORS[pu.kind], 35, 12)
        self.flash.trigger(PowerUp.COLORS[pu.kind], 10)
        if pu.kind == "star":
            self.score_mult = 2
            self.mult_timer = 300
            self.floats.append(FloatText(pu.x-50, pu.y-20, "⭐ DOUBLE SCORE! 30s",
                               NEON_YELLOW, 0.8, 80))
            speak("Double score power up!", "star")
        elif pu.kind == "nuke":
            for e in self.enemies:
                e.alive = False
                self.particles.burst(int(e.x),int(e.y), NEON_PINK, 30, 12)
                self.wave_kills += 1
                self.score      += self.KILL_SCORE
            self.enemies = []
            self.flash.trigger(WHITE, 18)
            self.floats.append(FloatText(px-60, py-40, "💥 NUKE! ALL DEFEATED!",
                               NEON_PINK, 0.85, 80))
            speak("Nuke! All enemies defeated!", "nuke")
        elif pu.kind == "heart":
            self.player_hp = min(self.MAX_HP, self.player_hp + 30)
            self.floats.append(FloatText(px-30, py-40, "+30 ❤ HEALTH!",
                               NEON_GREEN, 0.8, 70))
            speak("Health restored!", "heart")

    def draw(self, frame, spell_raw, hold_prog, cooldown):
        w, h = self.w, self.h

        for c in self.coins:
            c.draw(frame)
        for pu in self.powerups:
            pu.draw(frame)
        for e in self.enemies:
            e.draw(frame)

        self.particles.update_draw(frame)

        for f in self.floats:
            f.draw(frame)

        self.flash.apply(frame)

        elapsed   = time.time() - self.start_time
        remaining = max(0.0, self.GAME_DURATION - elapsed)
        draw_hud(frame, self.score, self.wave, self.player_hp, self.MAX_HP,
                 spell_raw, hold_prog, cooldown, self.score_mult, self.combo,
                 w, h, remaining, self.best_score)

        if 0 < remaining <= 10 and self.state == "playing":
            warn_col = RED if remaining <= 5 else NEON_YELLOW
            cv2.putText(frame, f"TIME LEFT: {int(remaining)+1}s",
                        (w//2 - 130, 68),
                        cv2.FONT_HERSHEY_DUPLEX, 1.1, warn_col, 3, cv2.LINE_AA)

        if self.state in ("dead", "timeup"):
            ov = frame.copy()
            cv2.rectangle(ov, (0,0), (w,h), BLACK, -1)
            cv2.addWeighted(ov, 0.62, frame, 0.38, 0, frame)
            cy = h//2
            if self.state == "timeup":
                cv2.putText(frame, "TIME'S UP!", (w//2-190, cy-60),
                            cv2.FONT_HERSHEY_DUPLEX, 2.2, NEON_YELLOW, 4, cv2.LINE_AA)
            else:
                cv2.putText(frame, "GAME OVER!", (w//2-180, cy-60),
                            cv2.FONT_HERSHEY_DUPLEX, 2.0, RED, 4, cv2.LINE_AA)
            cv2.putText(frame, f"FINAL SCORE: {self.score:,}", (w//2-190, cy),
                        cv2.FONT_HERSHEY_DUPLEX, 1.1, GOLD, 2, cv2.LINE_AA)
            cv2.putText(frame, f"BEST SCORE:  {self.best_score:,}", (w//2-190, cy+50),
                        cv2.FONT_HERSHEY_DUPLEX, 0.9, NEON_CYAN, 2, cv2.LINE_AA)
            cv2.putText(frame, f"WAVE REACHED: {self.wave}", (w//2-170, cy+100),
                        cv2.FONT_HERSHEY_DUPLEX, 0.85, WHITE, 1, cv2.LINE_AA)
            cv2.putText(frame, "Press [R] to Play Again   [Q] to Quit",
                        (w//2-260, cy+155),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180,180,180), 1, cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# COUNTDOWN SPLASH
# ─────────────────────────────────────────────────────────
def draw_splash(frame, count, w, h):
    ov = frame.copy()
    cv2.rectangle(ov,(0,0),(w,h),(10,5,25),-1)
    cv2.addWeighted(ov,0.7,frame,0.3,0,frame)
    cv2.putText(frame,"⚡ AI SPELLCASTER",(w//2-260,h//2-130),
                cv2.FONT_HERSHEY_DUPLEX,1.6,NEON_CYAN,3,cv2.LINE_AA)
    cv2.putText(frame,"MOVE TO SURVIVE",(w//2-195,h//2-75),
                cv2.FONT_HERSHEY_DUPLEX,1.1,NEON_YELLOW,2,cv2.LINE_AA)
    lines=[
        "FIREBALL  — Raise BOTH arms above head",
        "SHIELD    — Spread arms wide to sides",
        "LIGHTNING — Raise your RIGHT KNEE",
        "FREEZE    — Raise your LEFT KNEE",
        "DARK BOLT — SQUAT down low!",
        "GRAB COIN — Jump or reach coins with hands!",
    ]
    for i,l in enumerate(lines):
        cv2.putText(frame,l,(w//2-310,h//2-20+i*34),
                    cv2.FONT_HERSHEY_SIMPLEX,0.6,WHITE,1,cv2.LINE_AA)
    msg = f"GET READY... {count}" if count > 0 else "GO!"
    col = RED if count > 0 else NEON_GREEN
    cv2.putText(frame, msg, (w//2-100, h//2+200),
                cv2.FONT_HERSHEY_DUPLEX,2.0,col,4,cv2.LINE_AA)

# ─────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────
def main():
    mp_pose = mp.solutions.pose
    pose    = mp_pose.Pose(
        static_image_mode       = False,
        model_complexity        = 1,
        enable_segmentation     = False,
        min_detection_confidence= 0.5,
        min_tracking_confidence = 0.5,
    )

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        print("ERROR: Cannot open camera. Try VideoCapture(1).")
        return

    ret, frame = cap.read()
    if not ret:
        print("ERROR: Cannot read from camera.")
        return

    frame = cv2.flip(frame, 1)
    h, w  = frame.shape[:2]

    WIN = "⚡ AI SPELLCASTER: MOVE TO SURVIVE  |  Q=Quit  R=Restart"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, w, h)

    detector = SpellDetector()
    game     = Game(w, h)

    countdown_start = time.time()
    COUNTDOWN_SECS  = 4

    speak("AI Spellcaster! Move to Survive! Get ready!", "intro")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result= pose.process(rgb)

        elapsed_cd = time.time() - countdown_start
        if elapsed_cd < COUNTDOWN_SECS:
            count = COUNTDOWN_SECS - int(elapsed_cd)
            draw_splash(frame, count, w, h)
            cv2.imshow(WIN, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            continue

        lms        = result.pose_landmarks.landmark if result.pose_landmarks else None
        spell_raw  = "none"
        cast_fired = False

        if lms:
            spell_raw, cast_fired = detector.detect(lms, w, h)
            spell_col = SPELL_COLORS.get(spell_raw, (80,80,80))
            draw_skeleton(frame, lms, w, h, spell_col)
        else:
            cv2.putText(frame, "STEP BACK — full body needed!",
                        (w//2-250, h//2),
                        cv2.FONT_HERSHEY_DUPLEX, 0.9, NEON_YELLOW, 2, cv2.LINE_AA)

        game.update(lms, spell_raw, cast_fired)
        game.draw(frame, spell_raw, detector.hold_progress(), detector.on_cooldown())

        cv2.imshow(WIN, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), ord('Q'), 27):
            speak("Thanks for playing! Goodbye!", "bye")
            break
        elif key in (ord('r'), ord('R')):
            game.reset()
            detector = SpellDetector()
            countdown_start = time.time()
            speak("Restarting! Get ready!", "restart")

    cap.release()
    cv2.destroyAllWindows()
    pose.close()
    print(f"\n🏆 Final score: {game.score}   Best: {game.best_score}")
    print("Thanks for playing AI SpellCaster!")

if __name__ == "__main__":
    main()