#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KURTOS LAB - Beta v0.1
Jeu d'horreur et de survie en 3D pixel art (Python + Pygame + NumPy + OpenGL).

Lancer : directement depuis Pyzo (Run file as script) ou  python3 kurtos_lab.py
Les parametres et les sauvegardes sont stockes dans  ~/.kurtos_lab/kurtos_lab.db
"""

import sys
import os
import math
import time
import json
import random
import sqlite3
import subprocess
import importlib.util
import site
from collections import deque, defaultdict

GAME_NAME = "KURTOS LAB"
GAME_VERSION = "Beta v0.1"
GAME_TITLE = "%s - %s" % (GAME_NAME, GAME_VERSION)


# ----------------------------------------------------------------------------
# INSTALLATION AUTOMATIQUE DES DEPENDANCES
# ----------------------------------------------------------------------------
def ensure_dependencies():
    needed = [("numpy", "numpy"), ("pygame", "pygame"), ("OpenGL", "PyOpenGL")]
    missing = [pip_name for mod, pip_name in needed
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print("[KURTOS LAB] Installation des dependances manquantes :", ", ".join(missing))
    for pkg in missing:
        ok = False
        for extra in ([], ["--user"], ["--user", "--break-system-packages"]):
            cmd = [sys.executable, "-m", "pip", "install"] + extra + [pkg]
            try:
                if subprocess.call(cmd) == 0:
                    ok = True
                    break
            except OSError:
                break
        if not ok:
            print("[KURTOS LAB] Echec de l'installation de", pkg)
    try:
        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.append(user_site)
    except Exception:
        pass
    importlib.invalidate_caches()
    still = [p for m, p in needed if importlib.util.find_spec(m) is None]
    if still:
        raise RuntimeError(
            "Dependances introuvables : %s\n"
            "Essaie dans un terminal :\n"
            "  sudo apt install -y python3-pip python3-numpy python3-pygame python3-opengl"
            % ", ".join(still))


ensure_dependencies()

import numpy as np
import pygame
from OpenGL.GL import *


# ----------------------------------------------------------------------------
# CONSTANTES
# ----------------------------------------------------------------------------
WIN_W, WIN_H = 1280, 720
UI_W, UI_H = 640, 360                      # resolution de l'interface (pixelisee x2)
CELL = 2.0                                 # taille d'une case en metres
WALL_H = 3.0
QUALITY_LEVELS = [(240, 135), (320, 180), (480, 270), (640, 360)]
FPS_CHOICES = [30, 60, 90, 120, 144]
DB_DIR = os.path.join(os.path.expanduser("~"), ".kurtos_lab")
DB_PATH = os.path.join(DB_DIR, "kurtos_lab.db")

ACTION_ORDER = ["forward", "back", "left", "right", "interact", "run", "crouch",
                "flashlight", "battery", "inventory", "action"]


def default_keys():
    return {"forward": pygame.K_z, "back": pygame.K_s, "left": pygame.K_q, "right": pygame.K_d,
            "interact": pygame.K_e, "run": pygame.K_LSHIFT, "crouch": pygame.K_LCTRL,
            "flashlight": pygame.K_f, "battery": pygame.K_r, "inventory": pygame.K_i,
            "action": pygame.K_SPACE}


def default_settings():
    return {"language": "fr", "sensitivity": 0.12, "invert_y": False, "headbob": True,
            "fov": 70, "master": 0.8, "music": 0.6, "sfx": 0.9,
            "quality": 1, "fps": 60, "keys": default_keys()}


# ----------------------------------------------------------------------------
# TRADUCTION  (les textes sont definis a la fin du fichier : STRINGS)
# ----------------------------------------------------------------------------
LANG = "fr"


def set_language(code):
    global LANG
    LANG = code if code in STRINGS else "fr"


def tr(key, *args):
    s = STRINGS.get(LANG, {}).get(key)
    if s is None:
        s = STRINGS["fr"].get(key, key)
    if args:
        try:
            s = s.format(*args)
        except Exception:
            pass
    return s


# ----------------------------------------------------------------------------
# BASE DE DONNEES SQLITE (parametres + sauvegardes)
# ----------------------------------------------------------------------------
class Database:
    def __init__(self, path=DB_PATH):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS saves (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "created REAL, updated REAL, level INTEGER DEFAULT 0, playtime REAL DEFAULT 0, data TEXT)")
        self.conn.commit()

    # --- parametres ---
    def load_settings(self):
        st = default_settings()
        row = self.conn.execute("SELECT value FROM settings WHERE key='main'").fetchone()
        if row:
            try:
                saved = json.loads(row[0])
                for k, v in saved.items():
                    if k == "keys" and isinstance(v, dict):
                        for a, code in v.items():
                            if a in st["keys"] and isinstance(code, int):
                                st["keys"][a] = code
                    elif k in st and k != "keys" and type(v) == type(st[k]):
                        st[k] = v
                    elif k in st and k != "keys" and isinstance(st[k], float) and isinstance(v, int):
                        st[k] = float(v)
            except Exception:
                pass
        return st

    def save_settings(self, st):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('main', ?)", (json.dumps(st),))
        self.conn.commit()

    # --- sauvegardes ---
    def list_saves(self):
        rows = self.conn.execute(
            "SELECT id, name, created, updated, level, playtime FROM saves ORDER BY updated DESC").fetchall()
        return [dict(id=r[0], name=r[1], created=r[2], updated=r[3], level=r[4], playtime=r[5]) for r in rows]

    def create_save(self, name):
        now = time.time()
        cur = self.conn.execute("INSERT INTO saves (name, created, updated, level, playtime, data) "
                                "VALUES (?, ?, ?, 0, 0, NULL)", (name, now, now))
        self.conn.commit()
        return cur.lastrowid

    def rename_save(self, sid, name):
        self.conn.execute("UPDATE saves SET name=? WHERE id=?", (name, sid))
        self.conn.commit()

    def delete_save(self, sid):
        self.conn.execute("DELETE FROM saves WHERE id=?", (sid,))
        self.conn.commit()

    def write_save(self, sid, level, playtime, data):
        self.conn.execute("UPDATE saves SET updated=?, level=?, playtime=?, data=? WHERE id=?",
                          (time.time(), level, playtime, json.dumps(data), sid))
        self.conn.commit()

    def read_save(self, sid):
        row = self.conn.execute("SELECT data FROM saves WHERE id=?", (sid,)).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None


# ----------------------------------------------------------------------------
# TEXTURES PROCEDURALES (NumPy) - 64x64 RGBA pixel art
# alpha = 255 : opaque | 200 : opaque ET emissif (brille dans le noir) | 0 : transparent
# ----------------------------------------------------------------------------
TEX_N = 64
_YY, _XX = np.indices((TEX_N, TEX_N))


def _base(color, seed, amp=8):
    rng = np.random.default_rng(seed)
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    img[..., :3] = color
    img[..., 3] = 255
    img[..., :3] += rng.integers(-amp, amp + 1, (TEX_N, TEX_N, 1), dtype=np.int16)
    return img, rng


def _fin(img):
    return np.ascontiguousarray(np.clip(img, 0, 255).astype(np.uint8))


def _panel_lines(img, pct=55):
    img[::32, :, :3] = img[::32, :, :3] * pct // 100
    img[:, ::32, :3] = img[:, ::32, :3] * pct // 100


def _t_wall_metal():
    img, rng = _base((66, 74, 88), 1, 9)
    _panel_lines(img)
    for by in (0, 32):
        for bx in (0, 32):
            for (py, px) in ((4, 4), (4, 27), (27, 4), (27, 27)):
                img[by + py, bx + px, :3] += 45
    low = _YY < 8
    stripe = (((_XX + _YY) // 4) % 2 == 0) & low
    img[stripe, :3] = (150, 170, 30)
    img[low & ~stripe, :3] = (25, 25, 30)
    return _fin(img)


def _t_wall_tile():
    img, rng = _base((92, 112, 108), 11, 5)
    img[::16, :, :3] = img[::16, :, :3] * 60 // 100
    img[:, ::16, :3] = img[:, ::16, :3] * 60 // 100
    for _ in range(5):
        x = int(rng.integers(0, TEX_N - 6))
        y = int(rng.integers(12, TEX_N - 12))
        for k in range(12):
            img[y + k, x + k // 3, :3] = (30, 36, 34)
    dirt = _YY < 12
    img[dirt, :3] = img[dirt, :3] * 70 // 100
    return _fin(img)


def _t_wall_rust():
    img, rng = _base((88, 62, 52), 12, 7)
    for col in rng.integers(0, TEX_N, 10):
        img[:, int(col), :3] = img[:, int(col), :3] * 70 // 100
    for _ in range(7):
        x = int(rng.integers(0, 52))
        y = int(rng.integers(0, 52))
        img[y:y + 8, x:x + 10, :3] = (122 + int(rng.integers(-8, 8)), 72, 32)
    _panel_lines(img, 60)
    return _fin(img)


def _t_floor_metal():
    img, rng = _base((40, 38, 50), 2, 6)
    mask = (((_XX // 16) + (_YY // 16)) % 2 == 0)
    img[mask, :3] += 8
    _panel_lines(img, 50)
    img[..., 2] += 4
    return _fin(img)


def _t_floor_tile():
    img, rng = _base((60, 72, 70), 21, 5)
    mask = (((_XX // 16) + (_YY // 16)) % 2 == 0)
    img[mask, :3] = img[mask, :3] * 85 // 100
    img[::16, :, :3] = img[::16, :, :3] * 55 // 100
    img[:, ::16, :3] = img[:, ::16, :3] * 55 // 100
    return _fin(img)


def _t_floor_concrete():
    img, rng = _base((62, 60, 64), 22, 8)
    for _ in range(4):
        x = int(rng.integers(4, 56))
        y = int(rng.integers(0, 40))
        for k in range(20):
            img[y + k, min(TEX_N - 1, x + int(3 * math.sin(k * 0.6))), :3] = (26, 26, 30)
    for _ in range(4):
        x = int(rng.integers(0, 48))
        y = int(rng.integers(0, 48))
        img[y:y + 12, x:x + 14, :3] = img[y:y + 12, x:x + 14, :3] * 80 // 100
    return _fin(img)


def _t_ceiling():
    img, rng = _base((30, 32, 42), 4, 6)
    _panel_lines(img, 55)
    return _fin(img)


def _t_lamp():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    img[..., :3] = (36, 36, 42)
    img[..., 3] = 255
    img[8:56, 8:56, :3] = (225, 235, 255)
    img[8:56, 8:56, 3] = 200
    return _fin(img)


def _t_solid(color):
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    img[..., :3] = color
    img[..., 3] = 255
    return _fin(img)


def _t_door(stripe=None, style="plain"):
    base = (98, 68, 48) if style == "jammed" else (74, 80, 92)
    img, rng = _base(base, 31, 5)
    if style == "exit":
        d = (((_XX + _YY) // 6) % 2 == 0)
        img[d, :3] = (40, 210, 95)
        img[d, 3] = 200
        img[~d, :3] = (18, 28, 22)
    if style == "jammed":
        for k in range(48):
            img[8 + k, 10 + k * 7 // 8, :3] = (20, 14, 10)
            img[9 + k, 10 + k * 7 // 8, :3] = (20, 14, 10)
        for _ in range(5):
            x = int(rng.integers(6, 50))
            y = int(rng.integers(6, 50))
            img[y:y + 6, x:x + 8, :3] = img[y:y + 6, x:x + 8, :3] * 70 // 100
    if style == "auto":
        img[6:58, 24:40, :3] = (80, 200, 255)
        img[6:58, 24:40, 3] = 200
    img[:3, :, :3] = 36
    img[-3:, :, :3] = 36
    img[:, :3, :3] = 36
    img[:, -3:, :3] = 36
    img[:, 31:33, :3] = img[:, 31:33, :3] * 60 // 100
    if stripe is not None:
        img[28:36, 6:58, :3] = stripe
        img[28:36, 6:58, 3] = 200
    img[30:34, 50:54, :3] = (190, 190, 200)
    return _fin(img)


def _t_planks():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    rng = np.random.default_rng(33)
    for y0 in (5, 25, 45):
        img[y0:y0 + 13, :, :3] = (112, 80, 48) + rng.integers(-12, 12, (13, TEX_N, 1))
        img[y0:y0 + 13, :, 3] = 255
        img[y0 + 5, 6, :3] = (50, 40, 30)
        img[y0 + 5, 57, :3] = (50, 40, 30)
        img[y0:y0 + 13:4, :, :3] = img[y0:y0 + 13:4, :, :3] * 80 // 100
    return _fin(img)


def _t_chain():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    for t in range(TEX_N):
        for (x, y) in ((t, t), (t, TEX_N - 1 - t)):
            for d in range(-1, 2):
                if 0 <= x + d < TEX_N:
                    img[y, x + d, :3] = (150, 150, 160) if (t // 3) % 2 == 0 else (80, 80, 90)
                    img[y, x + d, 3] = 255
    img[26:40, 27:37, :3] = (210, 170, 40)
    img[26:40, 27:37, 3] = 255
    return _fin(img)


def _t_crate():
    n = TEX_N
    img, rng = _base((44, 96, 54), 3, 9)
    img[::16, :, :3] = img[::16, :, :3] * 60 // 100
    d = np.arange(n)
    img[d, d, :3] = (30, 60, 34)
    img[d, n - 1 - d, :3] = (30, 60, 34)
    border = (_XX < 3) | (_XX >= n - 3) | (_YY < 3) | (_YY >= n - 3)
    img[border, :3] = (24, 52, 30)
    return _fin(img)


def _t_table():
    img, rng = _base((110, 78, 50), 5, 7)
    img[::8, :, :3] = img[::8, :, :3] * 85 // 100
    img[:3, :, :3] = (70, 48, 30)
    img[-3:, :, :3] = (70, 48, 30)
    return _fin(img)


def _t_machine(screen=(40, 230, 90)):
    img, rng = _base((40, 44, 52), 6, 5)
    img[10:34, 8:56, :3] = screen
    img[10:34, 8:56, 3] = 200
    for y in range(13, 32, 4):
        img[y:y + 1, 11:int(rng.integers(30, 53)), :3] = (10, 60, 25)
    img[40:56:4, 8:56, :3] = (22, 24, 30)
    for i, col in enumerate(((220, 40, 40), (230, 200, 40), (60, 200, 80))):
        img[38:41, 10 + i * 8:14 + i * 8, :3] = col
        img[38:41, 10 + i * 8:14 + i * 8, 3] = 200
    return _fin(img)


def _t_server():
    img, rng = _base((30, 34, 44), 7, 4)
    for y in range(6, 58, 6):
        img[y:y + 4, 6:58, :3] = (20, 22, 28)
        for x in range(10, 54, 6):
            c = [(60, 230, 90), (60, 140, 255), (230, 60, 60)][int(rng.integers(0, 3))]
            img[y + 1:y + 3, x:x + 2, :3] = c
            img[y + 1:y + 3, x:x + 2, 3] = 200
    return _fin(img)


def _t_chest():
    img, rng = _base((96, 64, 40), 8, 8)
    img[::10, :, :3] = img[::10, :, :3] * 85 // 100
    img[:, 8:12, :3] = (62, 62, 68)
    img[:, 52:56, :3] = (62, 62, 68)
    img[28:33, :, :3] = (62, 62, 68)
    img[27:37, 29:35, :3] = (200, 160, 40)
    return _fin(img)


def _t_locker():
    img, rng = _base((70, 90, 110), 9, 5)
    img[:, 31:33, :3] = (30, 38, 48)
    for y in (8, 12, 16):
        img[y:y + 2, 8:26, :3] = (20, 26, 34)
        img[y:y + 2, 38:56, :3] = (20, 26, 34)
    img[34:42, 26:28, :3] = (190, 190, 200)
    img[:3, :, :3] = 40
    img[-3:, :, :3] = 40
    return _fin(img)


def _t_cabinet():
    img, rng = _base((128, 142, 136), 10, 5)
    img[:, 31:33, :3] = (60, 70, 66)
    img[12:30, 28:36, :3] = (200, 40, 40)
    img[12:30, 28:36, 3] = 200
    img[18:24, 22:42, :3] = (200, 40, 40)
    img[18:24, 22:42, 3] = 200
    img[:3, :, :3] = 70
    img[-3:, :, :3] = 70
    return _fin(img)


def _t_bed():
    img, rng = _base((150, 160, 172), 13, 5)
    img[:14, :, :3] = (205, 210, 220)
    img[28:34, :, :3] = (70, 100, 150)
    img[:3, :, :3] = 60
    img[-3:, :, :3] = 60
    return _fin(img)


def _t_generator():
    img, rng = _base((82, 88, 60), 14, 5)
    stripe = (((_XX + _YY) // 5) % 2 == 0) & (_YY > 50)
    img[stripe, :3] = (210, 180, 30)
    img[8:28, 8:40, :3] = (40, 230, 90)
    img[8:28, 8:40, 3] = 200
    img[10:26:5, 10:36, :3] = (10, 70, 30)
    img[34:48, 40:56, :3] = (30, 30, 36)
    img[38:44, 44:52, :3] = (230, 60, 50)
    img[38:44, 44:52, 3] = 200
    return _fin(img)


def _t_cables():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    rng = np.random.default_rng(41)
    cols = ((26, 26, 30), (130, 24, 24), (24, 24, 28), (170, 140, 30), (26, 26, 30), (24, 60, 130))
    for col in cols:
        a = int(rng.integers(6, 58))
        b = float(rng.uniform(4, 11))
        f = float(rng.uniform(0.08, 0.2))
        ph = float(rng.uniform(0, 6.28))
        for x in range(TEX_N):
            y0 = int(a + b * math.sin(x * f + ph))
            for dy in range(-2, 3):
                y = y0 + dy
                if 0 <= y < TEX_N:
                    img[y, x, :3] = col
                    img[y, x, 3] = 255
    for _ in range(5):
        a = int(rng.integers(4, 60))
        f = float(rng.uniform(0.08, 0.2))
        for y in range(TEX_N):
            x0 = int(a + 5 * math.sin(y * f))
            for dx in range(-1, 2):
                x = x0 + dx
                if 0 <= x < TEX_N:
                    img[y, x, :3] = (28, 28, 34)
                    img[y, x, 3] = 255
    return _fin(img)


def _t_exit():
    img, rng = _base((30, 40, 36), 15, 4)
    ring = (_XX < 4) | (_XX >= TEX_N - 4) | (_YY < 4) | (_YY >= TEX_N - 4)
    chev = ((_XX + _YY) % 16 < 4) & (_XX > 12) & (_XX < 52) & (_YY > 12) & (_YY < 52)
    m = ring | chev
    img[m, :3] = (40, 220, 100)
    img[m, 3] = 200
    return _fin(img)


def _t_blood():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    rng = np.random.default_rng(51)
    for _ in range(7):
        cx, cy = [int(v) for v in rng.integers(12, 52, 2)]
        r = int(rng.integers(4, 12))
        m = ((_XX - cx) ** 2 + (_YY - cy) ** 2) <= r * r
        img[m, :3] = (int(rng.integers(80, 125)), 8, 12)
        img[m, 3] = 255
    return _fin(img)


def _t_scratch():
    img = np.zeros((TEX_N, TEX_N, 4), np.int16)
    for k in range(4):
        x0 = 10 + k * 12
        for t in range(50):
            x = x0 + t // 3
            y = 6 + t
            img[y, x:x + 2, :3] = (92, 24, 24)
            img[y, x:x + 2, 3] = 255
    return _fin(img)


def build_texture_arrays():
    return {
        "wall_metal": _t_wall_metal(), "wall_tile": _t_wall_tile(), "wall_rust": _t_wall_rust(),
        "floor_metal": _t_floor_metal(), "floor_tile": _t_floor_tile(), "floor_concrete": _t_floor_concrete(),
        "ceiling": _t_ceiling(), "lamp": _t_lamp(),
        "door_normal": _t_door(), "door_red": _t_door((200, 40, 40)), "door_blue": _t_door((50, 100, 220)),
        "door_yellow": _t_door((220, 190, 40)), "door_green": _t_door((50, 190, 80)),
        "door_jammed": _t_door(None, "jammed"), "door_exit": _t_door(None, "exit"),
        "door_auto": _t_door(None, "auto"),
        "planks": _t_planks(), "chain": _t_chain(), "padlock": _t_solid((210, 170, 40)),
        "crate": _t_crate(), "table": _t_table(), "machine": _t_machine(), "server": _t_server(),
        "chest": _t_chest(), "locker": _t_locker(), "cabinet": _t_cabinet(), "bed": _t_bed(),
        "generator": _t_generator(), "cables": _t_cables(), "exit": _t_exit(),
        "blood": _t_blood(), "scratch": _t_scratch(),
    }


# ----------------------------------------------------------------------------
# SPRITES (pygame.draw) : zombies et icones d'objets
# ----------------------------------------------------------------------------
def make_zombie_surface(kind, frame):
    skin, cloth, dark = {"slow": ((108, 132, 98), (62, 58, 84), (28, 30, 38)),
                         "fast": ((150, 118, 142), (104, 38, 50), (34, 24, 34)),
                         "crawler": ((124, 112, 88), (54, 56, 66), (30, 28, 30))}[kind]
    eye = (255, 60, 30, 200)
    blood = (120, 14, 18, 255)
    o = 1 if frame else -1
    if kind == "crawler":
        s = pygame.Surface((48, 28), pygame.SRCALPHA)
        pygame.draw.rect(s, dark, (4, 16 + o, 9, 4))
        pygame.draw.rect(s, dark, (9, 20 - o, 9, 4))
        pygame.draw.rect(s, cloth, (10, 11, 24, 10))
        pygame.draw.rect(s, skin, (30, 15 + o, 12, 3))
        pygame.draw.rect(s, skin, (28, 19 - o, 12, 3))
        pygame.draw.circle(s, skin, (38, 10), 7)
        pygame.draw.rect(s, eye, (35, 7, 2, 2))
        pygame.draw.rect(s, eye, (40, 7, 2, 2))
        pygame.draw.rect(s, dark, (37, 13, 4, 2))
        pygame.draw.rect(s, blood, (16, 12, 4, 3))
        pygame.draw.rect(s, blood, (37, 15, 3, 2))
        return s
    s = pygame.Surface((32, 48), pygame.SRCALPHA)
    fat = kind == "slow"
    tx0, tw = (7, 18) if fat else (10, 12)
    pygame.draw.rect(s, dark, (11 + o, 33, 4, 14))
    pygame.draw.rect(s, dark, (17 - o, 33, 4, 14))
    pygame.draw.rect(s, (14, 14, 18), (10 + o, 45, 6, 3))
    pygame.draw.rect(s, (14, 14, 18), (16 - o, 45, 6, 3))
    pygame.draw.rect(s, cloth, (tx0, 17, tw, 18))
    ay = 3 if frame else 0
    al = 14 if fat else 17
    pygame.draw.rect(s, skin, (tx0 - 4, 18 + ay, 4, al))
    pygame.draw.rect(s, skin, (tx0 + tw, 21 - ay, 4, al))
    hr = 7 if fat else 5
    pygame.draw.circle(s, skin, (16, 10), hr)
    pygame.draw.rect(s, eye, (12, 8, 2, 2))
    pygame.draw.rect(s, eye, (18, 8, 2, 2))
    pygame.draw.rect(s, dark, (14, 13, 4, 2))
    for (x, y) in ((tx0 + 2, 34), (tx0 + tw - 3, 33), (tx0 + 6, 34)):
        s.set_at((x, y), (0, 0, 0, 0))
    pygame.draw.rect(s, blood, (tx0 + 3, 22, 4, 5))
    pygame.draw.rect(s, blood, (tx0 + tw - 6, 28, 3, 4))
    pygame.draw.rect(s, blood, (13, 14, 2, 3))
    return s


def make_item_surface(iid):
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    D = pygame.draw
    if iid.startswith("key_"):
        col = {"red": (210, 50, 50), "blue": (60, 110, 230), "yellow": (230, 200, 50),
               "green": (60, 200, 90)}[iid[4:]]
        D.circle(s, col, (4, 8), 3)
        D.circle(s, (0, 0, 0, 0), (4, 8), 1)
        D.rect(s, col, (6, 7, 8, 2))
        D.rect(s, col, (11, 9, 2, 3))
        D.rect(s, col, (13, 9, 2, 2))
    elif iid == "crowbar":
        D.line(s, (170, 50, 40), (3, 13), (12, 4), 2)
        D.line(s, (150, 150, 160), (12, 4), (14, 6), 2)
        D.line(s, (150, 150, 160), (3, 13), (2, 14), 2)
    elif iid == "bolt_cutters":
        D.line(s, (190, 50, 40), (2, 14), (8, 8), 2)
        D.line(s, (190, 50, 40), (5, 14), (9, 10), 2)
        D.line(s, (160, 160, 170), (8, 8), (13, 3), 2)
        D.line(s, (160, 160, 170), (9, 10), (14, 6), 2)
    elif iid == "bandage":
        D.circle(s, (225, 225, 230), (8, 8), 6)
        D.circle(s, (0, 0, 0, 0), (8, 8), 2)
        D.rect(s, (200, 50, 50), (7, 2, 3, 3))
    elif iid == "medkit":
        D.rect(s, (230, 230, 235), (2, 4, 12, 9))
        D.rect(s, (200, 40, 40), (7, 5, 2, 7))
        D.rect(s, (200, 40, 40), (4, 7, 8, 3))
        D.rect(s, (150, 150, 155), (6, 2, 4, 2))
    elif iid == "pills":
        D.rect(s, (230, 140, 40), (5, 5, 6, 9))
        D.rect(s, (235, 235, 235), (5, 3, 6, 3))
        D.rect(s, (255, 255, 255), (6, 8, 4, 3))
    elif iid == "battery":
        D.rect(s, (40, 44, 50), (2, 5, 11, 7))
        D.rect(s, (60, 210, 90), (2, 5, 4, 7))
        D.rect(s, (200, 200, 200), (13, 7, 2, 3))
    elif iid == "fuse":
        D.rect(s, (200, 220, 230), (5, 3, 6, 10))
        D.rect(s, (220, 180, 40), (5, 2, 6, 2))
        D.rect(s, (220, 180, 40), (5, 12, 6, 2))
        D.line(s, (240, 120, 40), (8, 4), (8, 11), 1)
    else:  # notes / documents
        D.rect(s, (225, 220, 200), (3, 2, 10, 12))
        for y in (4, 6, 8, 10):
            D.line(s, (110, 110, 110), (5, y), (11, y), 1)
    return s


def surface_rgba(surf, emissive=False):
    w, h = surf.get_size()
    data = pygame.image.tostring(surf, "RGBA", True)
    arr = np.frombuffer(data, np.uint8).reshape(h, w, 4).copy()
    if emissive:
        arr[..., 3][arr[..., 3] > 0] = 200
    return arr


# ----------------------------------------------------------------------------
# AUDIO PROCEDURAL (NumPy) - aucun fichier externe necessaire
# ----------------------------------------------------------------------------
class Audio:
    def __init__(self, settings):
        self.ok = False
        self.sounds = {}
        self.sr = 22050
        self.channels = 2
        self.master = settings["master"]
        self.music = settings["music"]
        self.sfx = settings["sfx"]
        self._v = [0.0, 0.0, 0.0]
        self.loops = []
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(20)
            pygame.mixer.set_reserved(3)
            info = pygame.mixer.get_init()
            self.sr, self.channels = info[0], info[2]
            self._generate()
            self.loops = [pygame.mixer.Channel(i) for i in range(3)]
            for ch, name in zip(self.loops, ("drone", "chase", "hum")):
                ch.set_volume(0.0)
                ch.play(self.sounds[name], loops=-1)
            self.ok = True
        except Exception as e:
            print("[KURTOS LAB] Audio desactive :", e)
            self.ok = False

    def apply_settings(self, settings):
        self.master = settings["master"]
        self.music = settings["music"]
        self.sfx = settings["sfx"]

    # --- generation ---
    def _t(self, d):
        return np.arange(int(self.sr * d), dtype=np.float64) / self.sr

    def _lp(self, x, k):
        return np.convolve(x, np.ones(k) / k, mode="same")

    def _mk(self, mono, vol=0.8):
        mono = np.clip(mono, -1.0, 1.0)
        a = (mono * 32767 * vol).astype(np.int16)
        if self.channels == 1:
            arr = np.ascontiguousarray(a)
        else:
            arr = np.ascontiguousarray(np.column_stack([a] * self.channels))
        return pygame.sndarray.make_sound(arr)

    def _groan(self, f0, f1, dur, rasp, vib, vol):
        rng = np.random.default_rng(int(f0))
        t = self._t(dur)
        f = np.linspace(f0, f1, len(t)) * (1.0 + 0.05 * np.sin(2 * np.pi * vib * t))
        ph = 2 * np.pi * np.cumsum(f) / self.sr
        x = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.33 * np.sin(3 * ph)
        x = x / 1.8 + rasp * self._lp(rng.standard_normal(len(t)), 4)
        x *= np.sin(np.pi * t / dur) ** 0.7
        return self._mk(x * 0.7, vol)

    def _generate(self):
        sr = self.sr
        rng = np.random.default_rng(7)
        S = self.sounds
        # ventilation (boucle 4 s)
        t = self._t(4.0)
        hum = 0.30 * np.sin(2 * np.pi * 50 * t) + 0.18 * np.sin(2 * np.pi * 100 * t) + 0.1 * np.sin(2 * np.pi * 75 * t)
        hum += 1.4 * self._lp(rng.standard_normal(len(t)), 40)
        S["hum"] = self._mk(hum * 0.6, 0.6)
        # drone d'ambiance (boucle 16 s)
        t = self._t(16.0)
        dr = np.zeros(len(t))
        for i, f in enumerate((55.0, 82.5, 110.25, 164.5)):
            f = round(f * 16) / 16.0
            lfo = 0.55 + 0.45 * np.sin(2 * np.pi * (i + 1) / 16.0 * t + i)
            dr += np.sin(2 * np.pi * f * t) * lfo * (0.35 / (i + 1) ** 0.5)
        S["drone"] = self._mk(dr, 0.7)
        # musique de poursuite (boucle 8 s)
        t = self._t(8.0)
        pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t) ** 2
        ch = np.sin(2 * np.pi * 55 * t) * pulse * 0.6 + np.sin(2 * np.pi * 58 * t) * 0.3
        ch += np.sin(2 * np.pi * 440 * t) * (np.sin(2 * np.pi * 4 * t) > 0.6) * 0.12
        S["chase"] = self._mk(ch, 0.7)
        # pas
        for i in range(2):
            n = int(sr * 0.14)
            tt = np.arange(n) / sr
            x = self._lp(rng.standard_normal(n), 12) * np.exp(-tt * 38) * 3.5
            x += 0.5 * np.sin(2 * np.pi * (70 + 10 * i) * tt) * np.exp(-tt * 40)
            S["step%d" % i] = self._mk(x, 0.7)
        # pied de biche (choc metallique)
        t = self._t(0.5)
        x = (0.5 * np.sin(2 * np.pi * 880 * t) + 0.4 * np.sin(2 * np.pi * 1480 * t)
             + 0.3 * np.sin(2 * np.pi * 2330 * t)) * np.exp(-t * 9)
        x += rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.8
        S["clank"] = self._mk(x, 0.8)
        # planches qui craquent
        t = self._t(0.4)
        x = np.zeros(len(t))
        for off in (0.0, 0.07, 0.15):
            i0 = int(off * sr)
            seg = self._lp(rng.standard_normal(len(t) - i0), 6) * np.exp(-np.arange(len(t) - i0) / sr * 40)
            x[i0:] += seg * 3.0
        S["crack"] = self._mk(x, 0.8)
        # porte qui grince
        t = self._t(0.7)
        f = 140 + 90 * t / 0.7
        ph = 2 * np.pi * np.cumsum(f) / sr
        x = (np.sin(ph) + 0.5 * np.sin(2 * ph)) * (1 + 0.4 * np.sin(2 * np.pi * 18 * t)) * np.sin(np.pi * t / 0.7) * 0.4
        x += self._lp(rng.standard_normal(len(t)), 8) * 0.3 * np.sin(np.pi * t / 0.7)
        S["door"] = self._mk(x, 0.7)
        # pince coupante
        t = self._t(0.15)
        x = np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 60) + rng.standard_normal(len(t)) * np.exp(-t * 120)
        S["snip"] = self._mk(x * 0.8, 0.7)
        # ramassage
        t1, t2 = self._t(0.06), self._t(0.09)
        x = np.concatenate([np.sin(2 * np.pi * 660 * t1) * np.exp(-t1 * 20),
                            np.sin(2 * np.pi * 990 * t2) * np.exp(-t2 * 18)])
        S["pickup"] = self._mk(x * 0.7, 0.6)
        # blessure
        t = self._t(0.4)
        x = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 9) + self._lp(rng.standard_normal(len(t)), 8) * np.exp(-t * 14) * 3
        S["hurt"] = self._mk(x * 0.8, 0.9)
        # coup (whoosh)
        t = self._t(0.25)
        S["swing"] = self._mk(self._lp(rng.standard_normal(len(t)), 10) * np.sin(np.pi * t / 0.25) * 3.0, 0.5)
        # menu
        t = self._t(0.05)
        S["ui"] = self._mk(np.sin(2 * np.pi * 900 * t) * np.exp(-t * 50) * 0.6, 0.5)
        # soin
        t = self._t(0.35)
        S["heal"] = self._mk(np.sin(2 * np.pi * (440 + 300 * t) * t) * np.sin(np.pi * t / 0.35) * 0.5, 0.6)
        # generateur
        t = self._t(1.6)
        x = np.sign(np.sin(2 * np.pi * 45 * t)) * 0.4 + self._lp(rng.standard_normal(len(t)), 6) * 1.2
        S["motor"] = self._mk(x * np.minimum(1, t * 4) * np.exp(-t * 0.8), 0.8)
        # battement de coeur
        t = self._t(0.9)
        x = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 14)
        i0 = int(0.28 * sr)
        x[i0:] += 0.7 * np.sin(2 * np.pi * 50 * t[:len(t) - i0]) * np.exp(-t[:len(t) - i0] * 14)
        S["heart"] = self._mk(x, 0.9)
        # gemissements des zombies
        S["groan_slow"] = self._groan(85, 55, 1.4, 0.4, 5, 0.8)
        S["groan_fast"] = self._groan(150, 95, 0.8, 0.6, 9, 0.8)
        S["groan_crawler"] = self._groan(210, 110, 1.0, 0.8, 12, 0.7)

    # --- lecture ---
    def play(self, name, vol=1.0, pan=0.0):
        if not self.ok:
            return
        if name == "step":
            name = "step%d" % random.randint(0, 1)
        s = self.sounds.get(name)
        if s is None:
            return
        v = vol * self.sfx * self.master
        if v <= 0.01:
            return
        ch = s.play()
        if ch is not None:
            ch.set_volume(v * (1.0 - max(0.0, pan)), v * (1.0 - max(0.0, -pan)))

    def update(self, dt, chase, in_game):
        if not self.ok:
            return
        m = self.master * self.music
        target = [m * (0.55 if in_game else 0.7) * (1.0 - 0.8 * chase),
                  m * 0.6 * chase,
                  self.master * self.sfx * (0.35 if in_game else 0.2)]
        k = min(1.0, dt * 1.5)
        for i in range(3):
            self._v[i] += (target[i] - self._v[i]) * k
            self.loops[i].set_volume(max(0.0, min(1.0, self._v[i])))

    def shutdown(self):
        try:
            pygame.mixer.stop()
        except Exception:
            pass
# ============================================================================
# NIVEAUX (generes)
# ============================================================================
LEVELS = [
    {
        "name": 'lvl1_name',
        "yaw": -90.0,
        "exit_need": None,
        "map": [
            '####################################',
            '#.N..N..k#.#########################',
            '#........#.##.M.M...M..#......k#####',
            '#M.......8.##..........#..t....#####',
            '#...P....#.##.....t....#.......#####',
            '#......t.#Z##........M.#....Z..#####',
            '#.N..N...#.##.B....C...#.B.....#####',
            '##########.##.........B#.......#####',
            '#........#.######7#########8#####..#',
            '#...t....#......................1.X#',
            '#.....i..8.###############5######..#',
            '#........#.#############......######',
            '#BB..k..B#.#############.k...B######',
            '##########.#############......######',
            '#........#i#############......######',
            '#.N...N..#.#############....B.######',
            '#........6.#############......######',
            '#.N.Z.N..#.#########################',
            '#.......k#.#########################',
            '####################################',
        ],
        "items": ['note3', 'key_red', 'note1', 'crowbar', 'bandage', 'bandage'],
        "containers": [
            {'kind': 'locker', 'lock': None, 'loot': [('battery', 1), ('bandage', 1)]},
            {'kind': 'cabinet', 'lock': None, 'loot': [('bandage', 1)]},
            {'kind': 'chest', 'lock': None, 'loot': [('pills', 1), ('battery', 1)]},
            {'kind': 'chest', 'lock': None, 'loot': [('battery', 2), ('medkit', 1)]},
            {'kind': 'chest', 'lock': 'planks', 'loot': [('bolt_cutters', 1), ('note2', 1)]},
        ],
        "default": {'rect': None, 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.06, 0.05, 0.1), 'lamp': (0.55, 0.6, 0.9), 'flicker': False, 'alarm': False, 'fog': 0.1},
        "zones": [
            {'rect': (1, 1, 8, 6), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.07, 0.09, 0.09), 'lamp': (0.55, 0.85, 0.8), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (1, 14, 8, 18), 'wall': 'wall_rust', 'floor': 'floor_concrete', 'amb': (0.08, 0.05, 0.06), 'lamp': (0.9, 0.55, 0.35), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (13, 2, 22, 7), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.04, 0.1, 0.06), 'lamp': (0.3, 1.0, 0.4), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (33, 8, 34, 10), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.1, 0.03, 0.03), 'lamp': (1.0, 0.15, 0.1), 'flicker': False, 'alarm': True, 'fog': 0.1},
        ],
    },
    {
        "name": 'lvl2_name',
        "yaw": -90.0,
        "exit_need": None,
        "map": [
            '########################################',
            '#########...M....t.#####################',
            '#########.k.....M..#####################',
            '#########..........#####################',
            '#############w##########################',
            '#######..............###################',
            '#######...Z........S.#.........#########',
            '#######..B.......B.S.#.S.S.S.S.#########',
            '#######..B...........#.........#########',
            '#t....#....M...M.....#.........#......##',
            '#.P...9......t.......2..C..t...3.....X##',
            '#.....#..............#.........#......##',
            '#.....#i...M..FM.....#.......M.#########',
            '#######..............#.S.S....k#########',
            '#######.....B....BC..#.........#########',
            '#######.k............###################',
            '#######..............###################',
            '#############5##########################',
            '########.............###################',
            '########.k..F......k.###################',
            '########......B.i....###################',
            '########.............###################',
            '########################################',
        ],
        "items": ['note5', 'note4', 'bandage', 'note6', 'battery', 'medkit'],
        "containers": [
            {'kind': 'chest', 'lock': 'planks', 'loot': [('key_blue', 1), ('battery', 1)]},
            {'kind': 'locker', 'lock': None, 'loot': [('key_yellow', 1)]},
            {'kind': 'locker', 'lock': None, 'loot': [('pills', 1), ('bandage', 1)]},
            {'kind': 'chest', 'lock': None, 'loot': [('battery', 2)]},
            {'kind': 'cabinet', 'lock': None, 'loot': [('medkit', 1), ('bandage', 1)]},
        ],
        "default": {'rect': None, 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.06, 0.05, 0.1), 'lamp': (0.55, 0.6, 0.9), 'flicker': False, 'alarm': False, 'fog': 0.1},
        "zones": [
            {'rect': (1, 9, 5, 12), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.07, 0.08, 0.09), 'lamp': (0.6, 0.85, 0.85), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (7, 5, 20, 16), 'wall': 'wall_rust', 'floor': 'floor_concrete', 'amb': (0.05, 0.1, 0.06), 'lamp': (0.3, 1.0, 0.35), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (9, 1, 18, 3), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.04, 0.1, 0.07), 'lamp': (0.3, 1.0, 0.5), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (8, 18, 20, 21), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.05, 0.07, 0.12), 'lamp': (0.4, 0.6, 1.0), 'flicker': False, 'alarm': False, 'fog': 0.1},
            {'rect': (22, 6, 30, 14), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.04, 0.06, 0.13), 'lamp': (0.3, 0.5, 1.0), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (32, 9, 37, 11), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.1, 0.03, 0.03), 'lamp': (1.0, 0.15, 0.1), 'flicker': False, 'alarm': True, 'fog': 0.1},
        ],
    },
    {
        "name": 'lvl3_name',
        "yaw": -90.0,
        "exit_need": 'power',
        "map": [
            '##########################################',
            '###############...........################',
            '###############..M..k..M..################',
            '###############.F....t..C.################',
            '########k...M##...........################',
            '########.....#######4#####################',
            '########B....#.............###############',
            '########...t.#....M...M..i.###############',
            '#N....##.Z...#..B...F...B..###############',
            '#...t.####8###.............#######.....###',
            '#.P...8.......8............0..........X###',
            '#.....####9###...Z..B......#######.....###',
            '#N...k##.....#.........C...###############',
            '########B...k#..B.......B..###############',
            '########.....#.k..M...M....###############',
            '########...i.#.............###############',
            '########.....#######5#####################',
            '########..G..##...........################',
            '########.....##.k.....C.k.################',
            '###############...i.B.....################',
            '###############...........################',
            '##########################################',
            '##########################################',
        ],
        "items": ['note8', 'bandage', 'pills', 'note7', 'battery', 'bandage'],
        "containers": [
            {'kind': 'chest', 'lock': 'planks', 'loot': [('fuse', 1)]},
            {'kind': 'chest', 'lock': 'padlock', 'loot': [('key_green', 1)]},
            {'kind': 'locker', 'lock': None, 'loot': [('battery', 1), ('bandage', 1)]},
            {'kind': 'cabinet', 'lock': None, 'loot': [('medkit', 1)]},
            {'kind': 'locker', 'lock': None, 'loot': [('battery', 1), ('pills', 1)]},
            {'kind': 'cabinet', 'lock': None, 'loot': [('medkit', 1), ('bandage', 1)]},
            {'kind': 'chest', 'lock': None, 'loot': [('battery', 2)]},
        ],
        "default": {'rect': None, 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.06, 0.05, 0.1), 'lamp': (0.55, 0.6, 0.9), 'flicker': False, 'alarm': False, 'fog': 0.1},
        "zones": [
            {'rect': (1, 8, 5, 12), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.07, 0.08, 0.09), 'lamp': (0.6, 0.85, 0.85), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (8, 4, 12, 8), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.06, 0.05, 0.1), 'lamp': (0.6, 0.6, 0.9), 'flicker': False, 'alarm': False, 'fog': 0.1},
            {'rect': (8, 12, 12, 18), 'wall': 'wall_rust', 'floor': 'floor_concrete', 'amb': (0.08, 0.06, 0.04), 'lamp': (1.0, 0.7, 0.3), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (14, 6, 26, 15), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.05, 0.05, 0.1), 'lamp': (0.5, 0.55, 0.9), 'flicker': True, 'alarm': False, 'fog': 0.1},
            {'rect': (15, 1, 25, 4), 'wall': 'wall_rust', 'floor': 'floor_concrete', 'amb': (0.1, 0.03, 0.03), 'lamp': (1.0, 0.15, 0.1), 'flicker': True, 'alarm': True, 'fog': 0.1},
            {'rect': (15, 17, 25, 20), 'wall': 'wall_tile', 'floor': 'floor_tile', 'amb': (0.05, 0.09, 0.08), 'lamp': (0.4, 1.0, 0.7), 'flicker': False, 'alarm': False, 'fog': 0.1},
            {'rect': (34, 9, 38, 11), 'wall': 'wall_metal', 'floor': 'floor_metal', 'amb': (0.1, 0.03, 0.03), 'lamp': (1.0, 0.15, 0.1), 'flicker': False, 'alarm': True, 'fog': 0.1},
        ],
    },
]


# =============================================================================
# DONNEES DU MONDE
# =============================================================================
KEY_OF = {"red": "key_red", "blue": "key_blue", "yellow": "key_yellow", "green": "key_green"}
DOOR_CHARS = {"1": "red", "2": "blue", "3": "yellow", "4": "green", "5": "jammed",
              "6": "boarded", "7": "chained", "8": "normal", "9": "auto", "0": "exit"}
DOOR_TEX = {"red": "door_red", "blue": "door_blue", "yellow": "door_yellow", "green": "door_green",
            "jammed": "door_jammed", "exit": "door_exit", "auto": "door_auto"}
# kind: (texture, demi-largeur x, demi-largeur z, hauteur)
PROP_DEF = {"B": ("crate", 0.6, 0.6, 1.2), "T": ("table", 0.7, 0.45, 0.82),
            "M": ("machine", 0.5, 0.4, 1.4), "S": ("server", 0.45, 0.45, 2.2),
            "N": ("bed", 0.55, 0.9, 0.55), "G": ("generator", 0.8, 0.55, 1.3)}
CONT_DEF = {"chest": ("chest", 0.5, 0.35, 0.6), "locker": ("locker", 0.4, 0.4, 1.9),
            "cabinet": ("cabinet", 0.5, 0.35, 1.5)}
ITEM_KIND = {"crowbar": "tool", "bolt_cutters": "tool", "fuse": "tool",
             "key_red": "key", "key_blue": "key", "key_yellow": "key", "key_green": "key",
             "bandage": "use", "medkit": "use", "pills": "use", "battery": "use"}
for _i in range(1, 9):
    ITEM_KIND["note%d" % _i] = "doc"
ITEM_IDS = list(ITEM_KIND.keys())

ZTYPES = {
    "slow": dict(name="zombie_slow", hp=6, patrol=0.8, chase=1.7, vision=9.0, hear=1.0, dmg=22, reach=1.0,
                 w=0.95, h=1.85, radius=0.35, windup=0.7, cool=1.6, alert=0.55),
    "fast": dict(name="zombie_fast", hp=3, patrol=1.3, chase=3.9, vision=12.0, hear=1.1, dmg=12, reach=0.9,
                 w=0.8, h=1.75, radius=0.3, windup=0.35, cool=1.0, alert=1.1),
    "crawler": dict(name="zombie_crawler", hp=4, patrol=0.9, chase=2.7, vision=7.0, hear=1.5, dmg=15, reach=0.9,
                    w=1.3, h=0.75, radius=0.3, windup=0.5, cool=1.2, alert=0.9),
}


class Door:
    def __init__(self, cx, cz, kind):
        self.cx, self.cz, self.kind = cx, cz, kind
        self.lock = kind if (kind in KEY_OF or kind in ("jammed", "exit")) else None
        self.planks = kind == "boarded"
        self.chain = kind == "chained"
        self.open = 0.0
        self.target = False
        self.axis_x = True
        self.x = (cx + 0.5) * CELL
        self.z = (cz + 0.5) * CELL

    @property
    def tex(self):
        return DOOR_TEX.get(self.kind, "door_normal")

    def locked(self):
        return bool(self.lock or self.planks or self.chain)

    def zombie_ok(self):
        return not self.locked()

    def box(self):
        c0, z0 = self.cx * CELL, self.cz * CELL
        if self.axis_x:
            return (c0, self.z - 0.15, c0 + CELL, self.z + 0.15)
        return (self.x - 0.15, z0, self.x + 0.15, z0 + CELL)


class Container:
    def __init__(self, spec, cx, cz):
        self.kind = spec["kind"]
        self.lock = spec.get("lock")
        self.loot = [list(l) for l in spec["loot"]]
        self.opened = False
        self.cx, self.cz = cx, cz
        self.x, self.z = (cx + 0.5) * CELL, (cz + 0.5) * CELL

    def box(self):
        tex, hx, hz, h = CONT_DEF[self.kind]
        return (self.x - hx, self.z - hz, self.x + hx, self.z + hz)


class Item:
    def __init__(self, iid, x, z, y):
        self.id, self.x, self.z, self.y = iid, x, z, y
        self.taken = False
        self.phase = random.uniform(0, 6.28)


def _circle_box(x, z, r, b):
    dx = x - min(max(x, b[0]), b[2])
    dz = z - min(max(z, b[1]), b[3])
    return dx * dx + dz * dz < r * r


# =============================================================================
# ZOMBIES (IA : patrouille, vue, ouie, poursuite, recherche, attaque)
# =============================================================================
class Zombie:
    def __init__(self, uid, kind, x, z):
        self.uid, self.kind, self.T = uid, kind, ZTYPES[kind]
        self.x, self.z = x, z
        self.yaw = random.uniform(0, 2 * math.pi)
        self.hp = float(self.T["hp"])
        self.radius = self.T["radius"]
        self.state = "patrol"
        self.path = []
        self.idle = random.uniform(0.5, 3.0)
        self.alert = 0.0
        self.lose = 0.0
        self.last_seen = None
        self.search_t = 0.0
        self.windup = 0.0
        self.cool = 0.0
        self.stun = 0.0
        self.groan_t = random.uniform(2.0, 8.0)
        self.anim = 0.0
        self.moving = False
        self.dead = False
        self.repath = 0.0
        self.stared = False

    def cell(self):
        return (int(self.x // CELL), int(self.z // CELL))

    # ---------------------------------------------------------------- reactions
    def hear(self, w, nx, nz, radius):
        if self.dead or self.state in ("chase", "attack"):
            return
        d = math.hypot(nx - self.x, nz - self.z)
        eff = radius * self.T["hear"]
        if not w.los(self.x, self.z, nx, nz):
            eff *= 0.6
        if d <= eff:
            path = w.find_path(self.cell(), (int(nx // CELL), int(nz // CELL)))
            if path is not None:
                self.state = "investigate"
                self.path = path
                self.search_t = 3.5
                self.alert = max(self.alert, 0.4)

    def damage(self, amount, stun, w, p, kx, kz):
        self.hp -= amount
        self.stun = max(self.stun, stun)
        self.x, self.z = w.move(self.x, self.z, kx * 0.7, kz * 0.7, self.radius)
        if self.hp <= 0:
            self.dead = True
            self.moving = False
            w.sound("groan_" + self.kind, self.x, self.z, 0.7)
        else:
            self.state = "chase"
            self.alert = 1.5
            self.lose = 0.0
            self.last_seen = (p.x, p.z)

    # ---------------------------------------------------------------- deplacement
    def step_to(self, w, tx, tz, speed, dt):
        dx, dz = tx - self.x, tz - self.z
        d = math.hypot(dx, dz)
        if d < 1e-3:
            return
        ux, uz = dx / d, dz / d
        step = min(speed * dt, d)
        self.x, self.z = w.move(self.x, self.z, ux * step, uz * step, self.radius)
        self.turn_to(math.atan2(-ux, -uz), 5.0, dt)
        self.moving = True
        self.anim += dt * speed * 0.9

    def turn_to(self, desired, rate, dt):
        diff = (desired - self.yaw + math.pi) % (2 * math.pi) - math.pi
        self.yaw += max(-rate * dt, min(rate * dt, diff))

    def follow(self, w, speed, dt):
        if not self.path:
            self.moving = False
            return False
        tx = tz = None
        k = 0
        for i in range(min(len(self.path), 5) - 1, -1, -1):
            c = self.path[i]
            wx, wz = (c[0] + 0.5) * CELL, (c[1] + 0.5) * CELL
            if i == 0 or w.clear_line(self.x, self.z, wx, wz, self.radius):
                tx, tz, k = wx, wz, i
                break
        del self.path[:k]
        d = w.doors.get(self.path[0])
        if d is not None and d.open < 0.85:
            if d.zombie_ok():
                if not d.target:
                    d.target = True
                    w.sound("door", d.x, d.z, 0.7)
                self.moving = False
                return True
            self.path = []
            self.moving = False
            return False
        self.step_to(w, tx, tz, speed, dt)
        while self.path:
            c = self.path[0]
            if math.hypot(self.x - (c[0] + 0.5) * CELL, self.z - (c[1] + 0.5) * CELL) < 0.45:
                self.path.pop(0)
            else:
                break
        return True

    # ---------------------------------------------------------------- mise a jour
    def update(self, dt, w, p):
        if self.dead:
            return
        T = self.T
        self.moving = False
        self.cool = max(0.0, self.cool - dt)
        self.groan_t -= dt
        dx, dz = p.x - self.x, p.z - self.z
        dist = math.hypot(dx, dz)
        if self.groan_t <= 0:
            calm = self.state in ("patrol", "search")
            self.groan_t = random.uniform(6, 12) if calm else random.uniform(2.5, 5)
            w.sound("groan_" + self.kind, self.x, self.z, 1.0)
        if self.stun > 0:
            self.stun -= dt
            return

        # --- vue ---
        vr = T["vision"] * (1.25 if p.flash_on else 1.0) * (0.65 if p.crouching else 1.0)
        sees = False
        if dist < vr:
            fx, fz = -math.sin(self.yaw), -math.cos(self.yaw)
            dot = (dx * fx + dz * fz) / max(dist, 1e-6)
            if (dot > 0.3 or dist < 2.2) and w.los(self.x, self.z, p.x, p.z):
                sees = True
        if sees:
            self.last_seen = (p.x, p.z)
            gain = T["alert"] * (1.0 + (vr - dist) / vr * 1.5)
            if self.state == "chase":
                self.alert = 1.5
            else:
                self.alert = min(1.5, self.alert + gain * dt)
        elif self.state != "chase":
            self.alert = max(0.0, self.alert - 0.35 * dt)
            self.stared = False

        # --- transitions ---
        if self.state == "chase":
            if sees:
                self.lose = 0.0
            else:
                self.lose += dt
                if self.lose > 4.5:
                    self.state, self.search_t, self.path = "search", 4.0, []
        elif self.state != "attack" and self.alert >= 1.0:
            self.state, self.lose, self.path = "chase", 0.0, []
            w.sound("groan_" + self.kind, self.x, self.z, 1.2)

        # --- comportements ---
        st = self.state
        if st == "patrol":
            if self.alert > 0.3 and sees:           # il vous fixe : tension
                self.turn_to(math.atan2(-dx, -dz), 3.0, dt)
                if not self.stared:
                    self.stared = True
                    w.sound("groan_" + self.kind, self.x, self.z, 0.9)
                return
            if self.idle > 0:
                self.idle -= dt
                return
            if not self.path:
                self.path = w.random_path(self.cell(), 9) or []
                if not self.path:
                    self.idle = random.uniform(1, 3)
                    return
            self.follow(w, T["patrol"], dt)
            if not self.path:
                self.idle = random.uniform(1.0, 4.0)
        elif st == "investigate":
            if self.follow(w, T["patrol"] * 1.5, dt) and self.path:
                return
            self.state, self.search_t = "search", 3.5
        elif st == "search":
            self.search_t -= dt
            self.yaw += 1.4 * dt
            if self.search_t <= 0:
                self.state, self.path, self.idle = "patrol", [], 1.0
        elif st == "chase":
            speed = T["chase"]
            if dist < T["reach"] + 0.3 and self.cool <= 0:
                self.state, self.windup = "attack", T["windup"]
                return
            if sees and w.clear_line(self.x, self.z, p.x, p.z, self.radius):
                if dist > 0.55:
                    self.step_to(w, p.x, p.z, speed, dt)
                else:
                    self.turn_to(math.atan2(-dx, -dz), 8.0, dt)
            else:
                self.repath -= dt
                if self.repath <= 0 or not self.path:
                    self.repath = 0.4
                    tgt = self.last_seen or (p.x, p.z)
                    self.path = w.find_path(self.cell(), (int(tgt[0] // CELL), int(tgt[1] // CELL))) or []
                if self.path:
                    self.follow(w, speed, dt)
                elif not sees:
                    self.lose += dt * 3
        elif st == "attack":
            self.turn_to(math.atan2(-dx, -dz), 8.0, dt)
            self.windup -= dt
            if self.windup <= 0:
                if dist < T["reach"] + 0.6:
                    p.hurt(T["dmg"], dx / max(dist, 1e-6), dz / max(dist, 1e-6))
                    w.sound("hurt", p.x, p.z, 1.0)
                self.cool = T["cool"]
                self.state, self.lose = "chase", 0.0


# =============================================================================
# MONDE : grille, collisions, portes, navigation
# =============================================================================
class World:
    def __init__(self, idx):
        self.idx = idx
        L = LEVELS[idx]
        self.L = L
        rows = L["map"]
        self.H = len(rows)
        self.W = max(len(r) for r in rows)
        rows = [r.ljust(self.W, "#") for r in rows]
        self.rows = rows
        self.grid = np.array([list(r) for r in rows])
        self.walk = ~np.isin(self.grid, ["#", " "])
        self.walk_l = self.walk.tolist()
        self.boxes, self.doors = {}, {}
        self.props, self.containers, self.items, self.zombies, self.cables = [], [], [], [], []
        self.events = []
        self.zones = L["zones"]
        self.default_zone = L["default"]
        self.start = (1.5 * CELL, 1.5 * CELL)
        self.exit_cell = None
        self.gen = None
        self.power = False
        self.exit_need = L.get("exit_need")
        self.noise_pulse = 0.0
        it_items = iter(L["items"])
        it_cont = iter(L["containers"])
        zid = 0
        for cz, row in enumerate(rows):
            for cx, ch in enumerate(row):
                x, z = (cx + 0.5) * CELL, (cz + 0.5) * CELL
                if ch == "P":
                    self.start = (x, z)
                elif ch == "X":
                    self.exit_cell = (cx, cz)
                elif ch in "ZFC":
                    kind = {"Z": "slow", "F": "fast", "C": "crawler"}[ch]
                    self.zombies.append(Zombie(zid, kind, x, z))
                    zid += 1
                elif ch in DOOR_CHARS:
                    self.doors[(cx, cz)] = Door(cx, cz, DOOR_CHARS[ch])
                elif ch in PROP_DEF:
                    self._add_prop(ch, cx, cz)
                elif ch == "t":
                    self._add_prop("T", cx, cz)
                    self.items.append(Item(next(it_items), x, z, 0.88))
                elif ch == "i":
                    self.items.append(Item(next(it_items), x, z, 0.2))
                elif ch == "k":
                    c = Container(next(it_cont), cx, cz)
                    self.containers.append(c)
                    self.boxes[(cx, cz)] = c.box()
                elif ch == "w":
                    self.cables.append({"cx": cx, "cz": cz, "cut": False, "axis_x": True,
                                        "x": x, "z": z})
        # orientation des portes et des cables
        for d in self.doors.values():
            d.axis_x = (not self._walk(d.cx - 1, d.cz)) and (not self._walk(d.cx + 1, d.cz))
        for cb in self.cables:
            cb["axis_x"] = (not self._walk(cb["cx"] - 1, cb["cz"])) and (not self._walk(cb["cx"] + 1, cb["cz"]))
            self.boxes[(cb["cx"], cb["cz"])] = self._slab(cb)
        for (kind, cx, cz) in self.props:
            if kind == "G":
                self.gen = {"x": (cx + 0.5) * CELL, "z": (cz + 0.5) * CELL}
        # lampes
        self.lamps = []
        for cz in range(self.H):
            for cx in range(self.W):
                if not self.walk_l[cz][cx] or (cx, cz) in self.boxes or (cx, cz) in self.doors:
                    continue
                zn = self.zone_at(cx, cz)
                if zn["lamp"] is not None and (cx + 3 * cz) % 5 == 0:
                    self.lamps.append({"x": (cx + 0.5) * CELL, "y": WALL_H - 0.12, "z": (cz + 0.5) * CELL,
                                       "col": zn["lamp"], "flicker": zn["flicker"], "alarm": zn["alarm"]})

    def _walk(self, cx, cz):
        return 0 <= cx < self.W and 0 <= cz < self.H and self.walk_l[cz][cx]

    def _slab(self, cb):
        c0, z0 = cb["cx"] * CELL, cb["cz"] * CELL
        if cb["axis_x"]:
            return (c0, cb["z"] - 0.15, c0 + CELL, cb["z"] + 0.15)
        return (cb["x"] - 0.15, z0, cb["x"] + 0.15, z0 + CELL)

    def _add_prop(self, kind, cx, cz):
        tex, hx, hz, h = PROP_DEF[kind]
        x, z = (cx + 0.5) * CELL, (cz + 0.5) * CELL
        self.props.append((kind, cx, cz))
        self.boxes[(cx, cz)] = (x - hx, z - hz, x + hx, z + hz)

    def zone_at(self, cx, cz):
        for zn in self.zones:
            c0, r0, c1, r1 = zn["rect"]
            if c0 <= cx <= c1 and r0 <= cz <= r1:
                return zn
        return self.default_zone

    # ---------------------------------------------------------------- evenements
    def sound(self, name, x, z, vol=1.0):
        self.events.append((name, x, z, vol))

    def noise(self, x, z, radius):
        self.noise_pulse = max(self.noise_pulse, radius)
        for zb in self.zombies:
            zb.hear(self, x, z, radius)

    # ---------------------------------------------------------------- collisions
    def box_at(self, cx, cz):
        if cx < 0 or cz < 0 or cx >= self.W or cz >= self.H:
            return (cx * CELL, cz * CELL, (cx + 1) * CELL, (cz + 1) * CELL)
        d = self.doors.get((cx, cz))
        if d is not None:
            return None if d.open >= 0.85 else d.box()
        if not self.walk_l[cz][cx]:
            return (cx * CELL, cz * CELL, (cx + 1) * CELL, (cz + 1) * CELL)
        return self.boxes.get((cx, cz))

    def collides(self, x, z, r):
        for cz in range(int(math.floor((z - r) / CELL)), int(math.floor((z + r) / CELL)) + 1):
            for cx in range(int(math.floor((x - r) / CELL)), int(math.floor((x + r) / CELL)) + 1):
                b = self.box_at(cx, cz)
                if b is not None and _circle_box(x, z, r, b):
                    return True
        return False

    def move(self, x, z, dx, dz, r):
        if not self.collides(x + dx, z, r):
            x += dx
        if not self.collides(x, z + dz, r):
            z += dz
        return x, z

    def clear_line(self, x0, z0, x1, z1, r):
        d = math.hypot(x1 - x0, z1 - z0)
        n = int(d / 0.35) + 1
        for i in range(1, n + 1):
            t = min(1.0, i * 0.35 / max(d, 1e-6))
            if self.collides(x0 + (x1 - x0) * t, z0 + (z1 - z0) * t, r):
                return False
        return True

    def los(self, x0, z0, x1, z1):
        d = math.hypot(x1 - x0, z1 - z0)
        n = int(d / 0.4) + 1
        for i in range(1, n):
            t = i / n
            cx, cz = int((x0 + (x1 - x0) * t) // CELL), int((z0 + (z1 - z0) * t) // CELL)
            if not self._walk(cx, cz):
                return False
            dr = self.doors.get((cx, cz))
            if dr is not None and dr.open < 0.5:
                return False
        return True

    # ---------------------------------------------------------------- navigation
    def zpass(self, cx, cz):
        if not self._walk(cx, cz) or (cx, cz) in self.boxes:
            return False
        d = self.doors.get((cx, cz))
        if d is not None and d.open < 0.85 and not d.zombie_ok():
            return False
        return True

    def _bfs(self, start, goal=None, max_depth=None, max_nodes=3000):
        parent = {start: None}
        dq = deque([(start, 0)])
        while dq:
            cur, dep = dq.popleft()
            if goal is not None and cur == goal:
                break
            if max_depth is not None and dep >= max_depth:
                continue
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cur[0] + dx, cur[1] + dz)
                if n in parent:
                    continue
                if n != goal and not self.zpass(n[0], n[1]):
                    continue
                parent[n] = cur
                dq.append((n, dep + 1))
            if len(parent) > max_nodes:
                break
        return parent

    @staticmethod
    def _build(parent, start, goal):
        path, c = [], goal
        while c != start:
            path.append(c)
            c = parent[c]
        path.reverse()
        return path

    def find_path(self, start, goal):
        if start == goal:
            return []
        par = self._bfs(start, goal)
        return self._build(par, start, goal) if goal in par else None

    def random_path(self, start, depth=9):
        par = self._bfs(start, None, max_depth=depth)
        cands = [c for c in par if abs(c[0] - start[0]) + abs(c[1] - start[1]) >= 3]
        if not cands:
            return None
        return self._build(par, start, random.choice(cands))

    # ---------------------------------------------------------------- mise a jour
    def update_doors(self, dt, p):
        for d in self.doors.values():
            if d.kind == "auto" and not d.locked():
                near = math.hypot(p.x - d.x, p.z - d.z) < 2.6
                if not near:
                    for zb in self.zombies:
                        if not zb.dead and math.hypot(zb.x - d.x, zb.z - d.z) < 2.2:
                            near = True
                            break
                if near != d.target:
                    d.target = near
                    self.sound("door", d.x, d.z, 0.6)
            goal = 1.0 if d.target else 0.0
            if d.open < goal:
                d.open = min(goal, d.open + 2.2 * dt)
            elif d.open > goal:
                d.open = max(goal, d.open - 2.2 * dt)

    def update(self, dt, p):
        self.noise_pulse = max(0.0, self.noise_pulse - dt * 14.0)
        self.update_doors(dt, p)
        for zb in self.zombies:
            zb.update(dt, self, p)
        zs = [z for z in self.zombies if not z.dead]
        for i in range(len(zs)):
            a = zs[i]
            for j in range(i + 1, len(zs)):
                b = zs[j]
                dx, dz = b.x - a.x, b.z - a.z
                d = math.hypot(dx, dz)
                if 1e-4 < d < 0.7:
                    push = (0.7 - d) * 0.5
                    ux, uz = dx / d, dz / d
                    a.x, a.z = self.move(a.x, a.z, -ux * push, -uz * push, a.radius)
                    b.x, b.z = self.move(b.x, b.z, ux * push, uz * push, b.radius)

    # ---------------------------------------------------------------- sauvegarde
    def get_state(self):
        return {
            "doors": {"%d,%d" % k: {"lock": d.lock, "planks": d.planks, "chain": d.chain, "open": bool(d.target)}
                      for k, d in self.doors.items()},
            "containers": [{"lock": c.lock, "opened": c.opened, "loot": c.loot} for c in self.containers],
            "items": [it.taken for it in self.items],
            "cables": [cb["cut"] for cb in self.cables],
            "zombies": [{"x": z.x, "z": z.z, "hp": z.hp, "dead": z.dead, "yaw": z.yaw} for z in self.zombies],
            "power": self.power,
        }

    def load_state(self, s):
        try:
            for k, v in s.get("doors", {}).items():
                cx, cz = [int(a) for a in k.split(",")]
                d = self.doors.get((cx, cz))
                if d:
                    d.lock, d.planks, d.chain = v["lock"], v["planks"], v["chain"]
                    d.target = bool(v["open"])
                    d.open = 1.0 if d.target else 0.0
            for c, v in zip(self.containers, s.get("containers", [])):
                c.lock, c.opened, c.loot = v["lock"], v["opened"], [list(l) for l in v["loot"]]
            for it, v in zip(self.items, s.get("items", [])):
                it.taken = bool(v)
            for cb, v in zip(self.cables, s.get("cables", [])):
                cb["cut"] = bool(v)
                if v:
                    self.boxes.pop((cb["cx"], cb["cz"]), None)
            for z, v in zip(self.zombies, s.get("zombies", [])):
                z.x, z.z, z.hp, z.dead, z.yaw = v["x"], v["z"], v["hp"], v["dead"], v["yaw"]
            self.power = bool(s.get("power", False))
        except Exception as e:
            print("[KURTOS LAB] Etat du monde partiellement charge :", e)


# =============================================================================
# JOUEUR + INVENTAIRE
# =============================================================================
class Inventory:
    CAP = 16

    def __init__(self):
        self.slots = []

    def count(self, iid):
        return sum(n for i, n in self.slots if i == iid)

    def has(self, iid):
        return self.count(iid) > 0

    def add(self, iid, n=1):
        for s in self.slots:
            if s[0] == iid:
                s[1] += n
                return 0
        if len(self.slots) < self.CAP:
            self.slots.append([iid, n])
            return 0
        return n

    def remove(self, iid, n=1):
        for s in self.slots:
            if s[0] == iid:
                s[1] -= n
                if s[1] <= 0:
                    self.slots.remove(s)
                return True
        return False

    def to_list(self):
        return [list(s) for s in self.slots]

    def from_list(self, lst):
        self.slots = [[str(i), int(n)] for i, n in lst]


class Player:
    def __init__(self, x, z, yaw=0.0):
        self.x, self.z, self.yaw, self.pitch = x, z, yaw, 0.0
        self.hp, self.max_hp = 100.0, 100.0
        self.stamina, self.exhausted = 100.0, False
        self.battery, self.flash_on = 100.0, True
        self.crouching, self.crouch_amt = False, 0.0
        self.vx = self.vz = 0.0
        self.bleeding, self.bleed_t = False, 0.0
        self.hurt_t, self.shake = 0.0, 0.0
        self.bob, self.step_acc = 0.0, 0.0
        self.running = False
        self.noise_r = 0.0
        self.attack_cd = 0.0
        self.inv = Inventory()

    def hurt(self, dmg, kx=0.0, kz=0.0):
        self.hp -= dmg
        self.hurt_t = 1.0
        self.shake = 1.0
        if dmg >= 15 and random.random() < 0.6:
            self.bleeding = True


# =============================================================================
# PARTIE EN COURS (logique de jeu)
# =============================================================================
class Game:
    def __init__(self, app, level_idx, carry=None):
        self.app = app
        self.idx = level_idx
        self.world = World(level_idx)
        sx, sz = self.world.start
        self.player = Player(sx, sz, math.radians(self.world.L.get("yaw", 0.0)))
        if carry:
            p = self.player
            p.hp = min(p.max_hp, carry["hp"] + 25)
            p.battery = carry["battery"]
            p.bleeding = False
            p.inv.from_list(carry["inv"])
        self.msgs = []
        self.t = 0.0
        self.playtime = 0.0
        self.hold, self.hold_obj, self.pulse = 0.0, None, 0.0
        self.target = None
        self.need_autosave = False
        self.autosave_t = 0.0
        self.dead = False
        self.exit_reached = False
        self.noise_disp = 0.0
        self.toast = tr("level_n", level_idx + 1, tr(self.world.L["name"]))
        self.toast_t = 5.0
        self.fear = 0.0
        self.heart_t = 0.0
        self.flick_t = 0.0
        self.low_batt_warned = False
        self.amb = np.array(self.world.default_zone["amb"], dtype=np.float64)
        self.amb_now = tuple(self.amb)
        self.fog = (0.03, 0.02, 0.05, 0.1)
        self.ambient_t = random.uniform(15, 35)

    # ---------------------------------------------------------------- utilitaires
    def say(self, text, ttl=4.5):
        self.msgs.append([text, ttl])
        self.msgs = self.msgs[-5:]

    def sfx(self, name, vol=1.0):
        self.app.audio.play(name, vol, 0.0)

    def pr(self, text):
        return "[%s] %s" % (self.app.key_name("interact"), text)

    def any_chasing(self):
        return any((not z.dead) and z.state in ("chase", "attack") for z in self.world.zombies)

    def save_carry(self):
        p = self.player
        inv = [s for s in p.inv.to_list() if ITEM_KIND.get(s[0]) != "key" and s[0] != "fuse"]
        return {"hp": p.hp, "battery": p.battery, "inv": inv}

    # ---------------------------------------------------------------- camera
    def camera(self):
        p = self.player
        hb = self.app.settings.get("headbob", True)
        spd = math.hypot(p.vx, p.vz)
        sc = min(1.3, spd / 4.3)
        bob_y = abs(math.sin(p.bob)) * 0.05 * sc if hb else 0.0
        roll = math.sin(p.bob) * 0.012 * sc if hb else 0.0
        tired = p.stamina < 35
        breath = math.sin(self.t * (4.2 if tired else 1.7)) * (0.025 if tired else 0.008)
        y = 1.68 - 0.62 * p.crouch_amt - bob_y + breath
        sh = p.shake
        return dict(x=p.x, y=y, z=p.z,
                    yaw=p.yaw + (random.random() - 0.5) * 0.05 * sh,
                    pitch=p.pitch + (random.random() - 0.5) * 0.05 * sh + (breath * 0.5),
                    roll=roll + (random.random() - 0.5) * 0.04 * sh)

    def render_params(self):
        p = self.player
        c = self.camera()
        flash = 0.0
        if p.flash_on and p.battery > 0:
            flash = 1.0 if p.battery > 15 else 0.45 + 0.55 * random.random()
            if self.flick_t > 0:
                flash *= 0.25
        c.update(fov=self.app.settings["fov"], flash=flash, amb=self.amb_now, fogcol=self.fog[:3],
                 fogden=self.fog[3], hurt=max(0.0, p.hurt_t) * 0.9, fear=self.fear,
                 fade=1.0 if self.dead is False else 0.35)
        c["fade"] = min(1.0, self.t / 1.5) * (0.35 if self.dead else 1.0)
        return c

    # ---------------------------------------------------------------- interaction : description
    def find_target(self):
        p, w = self.player, self.world
        fx, fz = -math.sin(p.yaw), -math.cos(p.yaw)
        best, best_s = None, 1e9

        def consider(obj, kind, x, z, reach, shorten):
            nonlocal best, best_s
            dx, dz = x - p.x, z - p.z
            d = math.hypot(dx, dz)
            if d > reach:
                return
            dot = 1.0 if d < 0.7 else (dx * fx + dz * fz) / d
            if dot < 0.72:
                return
            if d > 1.3 and not w.los(p.x, p.z, x - dx / d * shorten, z - dz / d * shorten):
                return
            s = d * (2.2 - dot)
            if s < best_s:
                best_s, best = s, (kind, obj)

        for d in w.doors.values():
            consider(d, "door", d.x, d.z, 2.7, 1.2)
        for c in w.containers:
            if not c.opened:
                consider(c, "container", c.x, c.z, 2.4, 0.6)
        for it in w.items:
            if not it.taken:
                consider(it, "item", it.x, it.z, 2.2, 0.4)
        for cb in w.cables:
            if not cb["cut"]:
                consider(cb, "cable", cb["x"], cb["z"], 2.6, 1.2)
        if w.gen is not None:
            consider(w.gen, "gen", w.gen["x"], w.gen["z"], 2.6, 0.9)
        if best is None:
            return None
        return getattr(self, "_desc_" + best[0])(best[1])

    def _T(self, kind, obj):
        return dict(kind=kind, obj=obj, prompt="", hold=0.0, noise=0.0, snd=None, ok=True, msg="", act=None)

    def _desc_item(self, it):
        T = self._T("item", it)
        T["prompt"] = self.pr(tr("p_take", tr("item_" + it.id)))
        T["act"] = lambda: self._pickup(it)
        return T

    def _desc_door(self, d):
        inv = self.player.inv
        T = self._T("door", d)
        if d.kind == "auto" and not d.locked():
            return None
        if d.target or d.open > 0.5:
            T["prompt"] = self.pr(tr("p_close"))
            T["act"] = lambda: self._close_door(d)
            return T
        if d.planks:
            if inv.has("crowbar"):
                T.update(prompt=self.pr(tr("p_planks")), hold=1.4, noise=13.0, snd="crack",
                         act=lambda: self._planks_door(d))
            else:
                T.update(prompt=tr("p_planks_no"), ok=False, msg=tr("m_need_crowbar"))
        elif d.chain:
            if inv.has("bolt_cutters"):
                T.update(prompt=self.pr(tr("p_chain")), hold=0.8, noise=2.0, snd="snip",
                         act=lambda: self._chain_door(d))
            else:
                T.update(prompt=tr("p_chain_no"), ok=False, msg=tr("m_need_cutters"))
        elif d.lock in KEY_OF:
            col = tr("color_" + d.lock)
            if inv.has(KEY_OF[d.lock]):
                T.update(prompt=self.pr(tr("p_unlock", col)), act=lambda: self._unlock_door(d))
            else:
                T.update(prompt=tr("p_locked", col), ok=False, msg=tr("m_need_key", col))
        elif d.lock == "jammed":
            if inv.has("crowbar"):
                T.update(prompt=self.pr(tr("p_force")), hold=1.6, noise=15.0, snd="clank",
                         act=lambda: self._force_door(d))
            else:
                T.update(prompt=tr("p_jammed"), ok=False, msg=tr("m_need_crowbar"))
        elif d.lock == "exit":
            need = self.world.exit_need
            if need == "power":
                T.update(prompt=tr("p_nopower"), ok=False, msg=tr("m_nopower"))
            elif need and inv.has(need):
                T.update(prompt=self.pr(tr("p_open")), act=lambda: self._unlock_door(d))
            else:
                T.update(prompt=tr("m_exit_locked"), ok=False, msg=tr("m_exit_locked"))
        else:
            T.update(prompt=self.pr(tr("p_open")), act=lambda: self._open_door(d))
        return T

    def _desc_container(self, c):
        inv = self.player.inv
        T = self._T("container", c)
        name = tr("cont_" + c.kind)
        if c.lock == "planks":
            if inv.has("crowbar"):
                T.update(prompt=self.pr(tr("p_planks")), hold=1.4, noise=12.0, snd="crack",
                         act=lambda: self._unlock_container(c))
            else:
                T.update(prompt=tr("p_cont_planks", name), ok=False, msg=tr("m_need_crowbar"))
        elif c.lock == "padlock":
            if inv.has("bolt_cutters"):
                T.update(prompt=self.pr(tr("p_padlock")), hold=0.8, noise=2.0, snd="snip",
                         act=lambda: self._unlock_container(c))
            else:
                T.update(prompt=tr("p_cont_padlock", name), ok=False, msg=tr("m_need_cutters"))
        elif c.lock in KEY_OF:
            col = tr("color_" + c.lock)
            if inv.has(KEY_OF[c.lock]):
                T.update(prompt=self.pr(tr("p_unlock", col)), act=lambda: self._unlock_container(c))
            else:
                T.update(prompt=tr("p_locked", col), ok=False, msg=tr("m_need_key", col))
        else:
            T.update(prompt=self.pr(tr("p_search", name)), hold=0.5, noise=1.5, act=lambda: self._loot(c))
        return T

    def _desc_cable(self, cb):
        T = self._T("cable", cb)
        if self.player.inv.has("bolt_cutters"):
            T.update(prompt=self.pr(tr("p_cable")), hold=1.0, noise=2.0, snd="snip", act=lambda: self._cut_cable(cb))
        else:
            T.update(prompt=tr("p_cable_no"), ok=False, msg=tr("m_need_cutters"))
        return T

    def _desc_gen(self, g):
        T = self._T("gen", g)
        if self.world.power:
            T.update(prompt=tr("p_gen_on"), ok=False, msg=tr("p_gen_on"))
        elif self.player.inv.has("fuse"):
            T.update(prompt=self.pr(tr("p_gen_fuse")), hold=1.2, noise=6.0, snd="clank", act=self._start_generator)
        else:
            T.update(prompt=tr("p_gen_no"), ok=False, msg=tr("m_gen_no"))
        return T

    # ---------------------------------------------------------------- interaction : actions
    def _open_door(self, d):
        d.target = True
        self.world.sound("door", d.x, d.z, 0.8)
        self.world.noise(d.x, d.z, 3.0)

    def _close_door(self, d):
        p, w = self.player, self.world
        blockers = [(p.x, p.z)] + [(z.x, z.z) for z in w.zombies if not z.dead]
        if any(math.hypot(x - d.x, z - d.z) < 1.0 for x, z in blockers):
            self.say(tr("m_blocked"))
            return
        d.target = False
        w.sound("door", d.x, d.z, 0.7)
        w.noise(d.x, d.z, 1.5)

    def _unlock_door(self, d):
        d.lock = None
        self.say(tr("m_unlocked"))
        self._open_door(d)
        self.need_autosave = True

    def _force_door(self, d):
        d.lock = None
        self.world.noise(d.x, d.z, 18.0)
        self.world.sound("clank", d.x, d.z, 1.0)
        self.say(tr("m_forced"))
        self._open_door(d)
        self.need_autosave = True

    def _planks_door(self, d):
        d.planks = False
        self.world.noise(self.player.x, self.player.z, 16.0)
        self.world.sound("crack", d.x, d.z, 1.0)
        self.say(tr("m_planks_off"))

    def _chain_door(self, d):
        d.chain = False
        self.say(tr("m_chain_cut"))

    def _cut_cable(self, cb):
        cb["cut"] = True
        self.world.boxes.pop((cb["cx"], cb["cz"]), None)
        self.say(tr("m_cable_cut"))
        self.need_autosave = True

    def _unlock_container(self, c):
        c.lock = None
        if c.lock is None:
            self.world.noise(self.player.x, self.player.z, 8.0)
        self._loot(c)

    def _loot(self, c):
        got, rest = [], []
        for iid, n in c.loot:
            left = self.player.inv.add(iid, n)
            if left < n:
                got.append("%s x%d" % (tr("item_" + iid), n - left) if n - left > 1 else tr("item_" + iid))
            if left:
                rest.append([iid, left])
        if rest:
            c.loot = rest
            self.say(tr("inv_full"))
        else:
            c.loot = []
            c.opened = True
        if got:
            self.say(tr("found", ", ".join(got)))
            self.sfx("pickup")
            self.need_autosave = True
        elif not rest:
            self.say(tr("empty"))

    def _pickup(self, it):
        if self.player.inv.add(it.id, 1):
            self.say(tr("inv_full"))
            return
        it.taken = True
        self.sfx("pickup")
        self.say(tr("picked", tr("item_" + it.id)))
        if ITEM_KIND.get(it.id) in ("key", "tool"):
            self.need_autosave = True

    def _start_generator(self):
        w, p = self.world, self.player
        p.inv.remove("fuse", 1)
        w.power = True
        w.noise(w.gen["x"], w.gen["z"], 24.0)
        w.sound("motor", w.gen["x"], w.gen["z"], 1.0)
        self.say(tr("m_gen_started"), 6.0)
        for d in w.doors.values():
            if d.lock == "exit":
                d.lock = None
                d.target = True
                w.sound("door", d.x, d.z, 1.0)
        self.need_autosave = True

    # ---------------------------------------------------------------- actions du joueur
    def on_interact_down(self):
        t = self.target
        if not t:
            return
        if not t["ok"]:
            self.say(t["msg"])
        elif t["hold"] <= 0:
            t["act"]()

    def toggle_flashlight(self):
        p = self.player
        if p.battery <= 0:
            self.say(tr("m_no_battery"))
            return
        p.flash_on = not p.flash_on
        self.sfx("ui", 0.8)

    def reload_battery(self):
        p = self.player
        if not p.inv.has("battery"):
            self.say(tr("m_no_spare"))
            return
        if p.battery > 85:
            self.say(tr("m_batt_full"))
            return
        p.inv.remove("battery", 1)
        p.battery = min(100.0, p.battery + 50.0)
        self.low_batt_warned = False
        self.sfx("heal")
        self.say(tr("m_batt_ok"))

    def attack(self):
        p, w = self.player, self.world
        if p.attack_cd > 0 or p.stamina < 6:
            return
        has = p.inv.has("crowbar")
        p.attack_cd = 0.75
        p.stamina -= 8
        self.sfx("swing", 0.7)
        fx, fz = -math.sin(p.yaw), -math.cos(p.yaw)
        hit = False
        for z in w.zombies:
            if z.dead:
                continue
            dx, dz = z.x - p.x, z.z - p.z
            d = math.hypot(dx, dz)
            if d < 1.8 and (d < 0.6 or (dx * fx + dz * fz) / d > 0.5):
                z.damage(2.0 if has else 0.0, 0.9 if has else 0.6, w, p, fx, fz)
                hit = True
        w.noise(p.x, p.z, 11.0 if (has and hit) else 5.0)
        if has and hit:
            self.sfx("clank", 0.8)

    def use_item(self, i):
        p = self.player
        if i < 0 or i >= len(p.inv.slots):
            return
        iid = p.inv.slots[i][0]
        if iid == "bandage":
            if p.bleeding or p.hp < p.max_hp:
                p.bleeding = False
                p.hp = min(p.max_hp, p.hp + 15)
                p.inv.remove(iid)
                self.sfx("heal")
                self.say(tr("m_bandage"))
            else:
                self.say(tr("m_not_needed"))
        elif iid == "medkit":
            if p.bleeding or p.hp < p.max_hp - 5:
                p.bleeding = False
                p.hp = min(p.max_hp, p.hp + 60)
                p.inv.remove(iid)
                self.sfx("heal")
                self.say(tr("m_medkit"))
            else:
                self.say(tr("m_not_needed"))
        elif iid == "pills":
            p.stamina = 100.0
            p.exhausted = False
            p.hp = min(p.max_hp, p.hp + 10)
            p.inv.remove(iid)
            self.sfx("heal")
            self.say(tr("m_pills"))
        elif iid == "battery":
            self.reload_battery()
        elif ITEM_KIND.get(iid) == "doc":
            pass
        else:
            self.say(tr("m_auto_use"))

    # ---------------------------------------------------------------- mise a jour
    def update(self, dt, inp):
        self.t += dt
        self.playtime += dt
        self._update_player(dt, inp)
        self._update_interaction(dt, inp)
        self.world.update(dt, self.player)
        self._process_events()
        self._update_status(dt)

    def _update_player(self, dt, inp):
        p, w, s = self.player, self.world, self.app.settings
        dx, dy = inp["mouse"]
        sens = s["sensitivity"]
        p.yaw -= math.radians(dx * sens)
        p.pitch = max(-1.4, min(1.4, p.pitch - math.radians(dy * sens) * (-1 if s.get("invert_y") else 1)))
        fwd, side = inp["fwd"], inp["side"]
        moving = fwd != 0 or side != 0
        p.crouching = bool(inp["crouch"])
        p.crouch_amt += ((1.0 if p.crouching else 0.0) - p.crouch_amt) * min(1.0, dt * 9)
        want_run = bool(inp["run"]) and moving and (not p.crouching) and (not p.exhausted) and p.stamina > 0
        speed = 1.3 if p.crouching else 2.5
        if want_run:
            speed = 4.3
        if p.hp < 30:
            speed *= 0.85
        tvx = tvz = 0.0
        if moving:
            sy, cy = math.sin(p.yaw), math.cos(p.yaw)
            mx = -sy * fwd + cy * side
            mz = -cy * fwd - sy * side
            l = math.hypot(mx, mz)
            tvx, tvz = mx / l * speed, mz / l * speed
        k = min(1.0, dt * 10)
        p.vx += (tvx - p.vx) * k
        p.vz += (tvz - p.vz) * k
        ox, oz = p.x, p.z
        p.x, p.z = w.move(p.x, p.z, p.vx * dt, p.vz * dt, 0.3)
        moved = math.hypot(p.x - ox, p.z - oz)
        p.running = want_run and moved > 0.001
        if p.running:
            p.stamina -= 20 * dt
            if p.stamina <= 0:
                p.stamina, p.exhausted = 0.0, True
        else:
            p.stamina = min(100.0, p.stamina + (10 if moving else 18) * dt)
            if p.exhausted and p.stamina > 30:
                p.exhausted = False
        sl = 1.0 if p.crouching else (1.9 if p.running else 1.4)
        p.step_acc += moved
        p.bob += moved / sl * math.pi
        if p.step_acc >= sl:
            p.step_acc -= sl
            r = 1.6 if p.crouching else (9.0 if p.running else 4.5)
            self.sfx("step", 0.3 if p.crouching else (0.75 if p.running else 0.5))
            w.noise(p.x, p.z, r)
            p.noise_r = r
        p.noise_r = max(0.0, p.noise_r - dt * 6)
        p.attack_cd = max(0.0, p.attack_cd - dt)
        if p.flash_on:
            p.battery -= 0.7 * dt
            if p.battery <= 0:
                p.battery, p.flash_on = 0.0, False
                self.say(tr("m_batt_dead"))
            elif p.battery < 15 and not self.low_batt_warned:
                self.low_batt_warned = True
                self.say(tr("m_batt_low"))
        if p.bleeding:
            p.bleed_t += dt
            if p.bleed_t >= 2.0:
                p.bleed_t = 0.0
                if p.hp > 5:
                    p.hp -= 1.0
        p.hurt_t = max(0.0, p.hurt_t - dt * 1.2)
        p.shake = max(0.0, p.shake - dt * 2.0)

    def _update_interaction(self, dt, inp):
        p, w = self.player, self.world
        self.target = self.find_target()
        t = self.target
        if inp["interact"] and t and t["ok"] and t["hold"] > 0:
            if self.hold_obj is not t["obj"]:
                self.hold_obj, self.hold, self.pulse = t["obj"], 0.0, 0.0
            self.hold += dt
            self.pulse -= dt
            if self.pulse <= 0:
                self.pulse = 0.45
                if t["noise"] > 0:
                    w.noise(p.x, p.z, t["noise"])
                if t["snd"]:
                    self.sfx(t["snd"], 0.9)
            if self.hold >= t["hold"]:
                self.hold, self.hold_obj = 0.0, None
                t["act"]()
        else:
            self.hold, self.hold_obj = 0.0, None
        ex = w.exit_cell
        if ex and math.hypot(p.x - (ex[0] + 0.5) * CELL, p.z - (ex[1] + 0.5) * CELL) < 1.3:
            self.exit_reached = True

    def _process_events(self):
        w, p = self.world, self.player
        ev, w.events = w.events, []
        rx, rz = math.cos(p.yaw), -math.sin(p.yaw)
        for name, x, z, vol in ev:
            dx, dz = x - p.x, z - p.z
            d = math.hypot(dx, dz)
            v = vol * max(0.0, 1.0 - d / 26.0)
            if v <= 0.02:
                continue
            pan = (dx * rx + dz * rz) / d if d > 0.5 else 0.0
            self.app.audio.play(name, v, max(-1.0, min(1.0, pan)))

    def _update_status(self, dt):
        p, w = self.player, self.world
        self.msgs = [[t, ttl - dt] for t, ttl in self.msgs if ttl - dt > 0]
        self.toast_t = max(0.0, self.toast_t - dt)
        self.flick_t = max(0.0, self.flick_t - dt)
        if random.random() < 0.004:
            self.flick_t = 0.18
        self.noise_disp += (max(p.noise_r, w.noise_pulse * 0.0) - self.noise_disp) * min(1.0, dt * 8)
        # peur : zombie en poursuite proche
        f = 0.0
        for z in w.zombies:
            if z.dead:
                continue
            d = math.hypot(z.x - p.x, z.z - p.z)
            if z.state in ("chase", "attack"):
                f = max(f, 1.0 - d / 14.0)
            elif z.alert > 0.3:
                f = max(f, 0.3 * (1.0 - d / 10.0))
        self.fear += (max(0.0, min(1.0, f)) - self.fear) * min(1.0, dt * 3)
        self.heart_t -= dt
        if self.fear > 0.25 and self.heart_t <= 0:
            self.sfx("heart", 0.5 + self.fear * 0.5)
            self.heart_t = 1.2 - 0.7 * self.fear
        # ambiance : bruits lointains
        self.ambient_t -= dt
        if self.ambient_t <= 0:
            self.ambient_t = random.uniform(20, 45)
            self.app.audio.play(random.choice(("groan_slow", "groan_fast", "groan_crawler")), 0.22,
                                random.uniform(-1, 1))
        # lumiere ambiante de la zone (transition douce + pulsation d'alarme)
        zn = w.zone_at(int(p.x // CELL), int(p.z // CELL))
        self.amb += (np.array(zn["amb"]) - self.amb) * min(1.0, dt * 1.5)
        a = self.amb.copy()
        if zn["alarm"]:
            a[0] += 0.07 * (0.5 + 0.5 * math.sin(self.t * 3.0))
        self.amb_now = tuple(float(v) for v in a)
        fc = tuple(float(v) * 0.5 for v in a)
        self.fog = (fc[0], fc[1], fc[2], zn.get("fog", 0.1))
        # sauvegarde automatique
        self.autosave_t += dt
        if (self.need_autosave or self.autosave_t > 120.0) and not self.any_chasing():
            self.need_autosave = False
            self.autosave_t = 0.0
            self.app.save_game(auto=True)
        if p.hp <= 0 and not self.dead:
            self.dead = True
            self.sfx("hurt", 1.0)

    # ---------------------------------------------------------------- sauvegarde
    def get_state(self):
        p = self.player
        return {"level": self.idx, "playtime": self.playtime,
                "player": {"x": p.x, "z": p.z, "yaw": p.yaw, "pitch": p.pitch, "hp": p.hp,
                           "stamina": p.stamina, "battery": p.battery, "flash": p.flash_on,
                           "bleeding": p.bleeding, "inv": p.inv.to_list()},
                "world": self.world.get_state()}

    def load_state(self, d):
        try:
            self.playtime = float(d.get("playtime", 0.0))
            pl = d["player"]
            p = self.player
            p.x, p.z, p.yaw, p.pitch = pl["x"], pl["z"], pl["yaw"], pl["pitch"]
            p.hp, p.stamina, p.battery = pl["hp"], pl["stamina"], pl["battery"]
            p.flash_on, p.bleeding = bool(pl["flash"]), bool(pl["bleeding"])
            p.inv.from_list(pl["inv"])
            self.world.load_state(d.get("world", {}))
        except Exception as e:
            print("[KURTOS LAB] Sauvegarde partiellement chargee :", e)


# =============================================================================
# SHADERS GLSL (version 120 : compatible avec les PC modestes)
# =============================================================================
SCENE_VS = """
#version 120
varying vec2 vUV;
varying vec3 vPos;
varying vec3 vNormal;
void main() {
    vUV = gl_MultiTexCoord0.xy;
    vPos = (gl_ModelViewMatrix * gl_Vertex).xyz;
    vNormal = gl_NormalMatrix * gl_Normal;
    gl_Position = gl_ProjectionMatrix * gl_ModelViewMatrix * gl_Vertex;
}
"""

SCENE_FS = """
#version 120
uniform sampler2D uTex;
uniform float uFlash;
uniform vec3 uAmb;
uniform vec3 uFogCol;
uniform float uFogDen;
uniform vec3 uLP[4];
uniform vec3 uLC[4];
varying vec2 vUV;
varying vec3 vPos;
varying vec3 vNormal;
void main() {
    vec4 t = texture2D(uTex, vUV);
    if (t.a < 0.5) discard;
    float em = (t.a < 0.95) ? 1.0 : 0.0;
    vec3 albedo = t.rgb;
    float d = length(vPos);
    vec3 N = normalize(vNormal);
    vec3 V = normalize(-vPos);
    float ndl = max(dot(N, V), 0.0);
    // lampe torche : cone devant la camera (espace vue)
    float cosang = dot(normalize(vPos), vec3(0.0, 0.0, -1.0));
    float spot = smoothstep(0.82, 0.95, cosang);
    float att = 1.0 / (1.0 + 0.09 * d * d);
    vec3 flash = vec3(0.9, 0.95, 1.0) * uFlash * spot * att * (0.35 + 0.65 * ndl) * 2.6;
    // lampes proches (4 max)
    vec3 lights = vec3(0.0);
    for (int i = 0; i < 4; i++) {
        vec3 L = uLP[i] - vPos;
        float dl = length(L);
        L = L / max(dl, 0.001);
        float a = 1.0 / (1.0 + 0.30 * dl * dl);
        lights += uLC[i] * a * (0.35 + 0.65 * max(dot(N, L), 0.0));
    }
    vec3 col = albedo * (uAmb + flash + lights) + albedo * em * 0.75;
    float fog = clamp(1.0 - exp(-d * uFogDen), 0.0, 1.0);
    col = mix(col, uFogCol, fog * 0.9);
    gl_FragColor = vec4(col, 1.0);
}
"""

POST_VS = """
#version 120
varying vec2 vUV;
void main() {
    vUV = gl_MultiTexCoord0.xy;
    gl_Position = gl_Vertex;
}
"""

POST_FS = """
#version 120
uniform sampler2D uScene;
uniform float uTime;
uniform vec2 uRes;
uniform float uHurt;
uniform float uFear;
uniform float uFade;
varying vec2 vUV;
void main() {
    vec2 uv = vUV;
    uv.x += sin(uv.y * 40.0 + uTime * 8.0) * 0.002 * uFear;
    vec3 c = texture2D(uScene, uv).rgb;
    c.r = mix(c.r, texture2D(uScene, uv + vec2(0.006, 0.0)).r, clamp(uHurt + uFear * 0.5, 0.0, 1.0));
    float g = fract(sin(dot(uv * uRes + uTime, vec2(12.9898, 78.233))) * 43758.5453);
    c += (g - 0.5) * 0.035;
    c = floor(c * 18.0 + 0.5) / 18.0;
    c = mix(c, c * vec3(1.5, 0.35, 0.35), uHurt * 0.7);
    float v = length(vUV - 0.5);
    c *= 1.0 - smoothstep(0.25 - 0.1 * uFear, 0.85, v);
    c *= uFade;
    gl_FragColor = vec4(c, 1.0);
}
"""


def _log_to_str(log):
    return log.decode("utf-8", "replace") if isinstance(log, bytes) else str(log)


def build_program(vs_src, fs_src):
    prog = glCreateProgram()
    shaders = []
    for typ, src in ((GL_VERTEX_SHADER, vs_src), (GL_FRAGMENT_SHADER, fs_src)):
        sh = glCreateShader(typ)
        glShaderSource(sh, src)
        glCompileShader(sh)
        if not glGetShaderiv(sh, GL_COMPILE_STATUS):
            raise RuntimeError("Erreur shader :\n" + _log_to_str(glGetShaderInfoLog(sh)))
        glAttachShader(prog, sh)
        shaders.append(sh)
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError("Erreur link shader :\n" + _log_to_str(glGetProgramInfoLog(prog)))
    for sh in shaders:
        glDeleteShader(sh)
    return prog


def upload_rgba(arr, repeat=True):
    h, w = arr.shape[0], arr.shape[1]
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    wrap = GL_REPEAT if repeat else GL_CLAMP_TO_EDGE
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, np.ascontiguousarray(arr).tobytes())
    return tex


def _emit_quad(q):
    a, b, c, d, n, us, vs = q
    glNormal3f(*n)
    glTexCoord2f(0, 0); glVertex3f(*a)
    glTexCoord2f(us, 0); glVertex3f(*b)
    glTexCoord2f(us, vs); glVertex3f(*c)
    glTexCoord2f(0, vs); glVertex3f(*d)


def box_quads(x0, y0, z0, x1, y1, z1):
    return [((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, 1), 1, 1),
            ((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (0, 0, -1), 1, 1),
            ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (-1, 0, 0), 1, 1),
            ((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (1, 0, 0), 1, 1),
            ((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0), (0, 1, 0), 1, 1)]


def compile_quads(quads):
    lst = glGenLists(1)
    glNewList(lst, GL_COMPILE)
    glBegin(GL_QUADS)
    for q in quads:
        _emit_quad(q)
    glEnd()
    glEndList()
    return lst


# =============================================================================
# MOTEUR DE RENDU
# =============================================================================
class Renderer:
    def __init__(self, win_w, win_h, quality_index):
        self.win_w, self.win_h = win_w, win_h
        self.fbo = self.color_tex = self.depth_rb = None
        self.iw, self.ih = QUALITY_LEVELS[quality_index]
        self.scene_prog = build_program(SCENE_VS, SCENE_FS)
        self.post_prog = build_program(POST_VS, POST_FS)
        self.u = {}
        for name in ("uTex", "uFlash", "uAmb", "uFogCol", "uFogDen", "uLP", "uLC"):
            self.u[name] = self._loc(self.scene_prog, name)
        for name in ("uScene", "uTime", "uRes", "uHurt", "uFear", "uFade"):
            self.u["p" + name] = self._loc(self.post_prog, name)
        self.tex = {k: upload_rgba(v) for k, v in build_texture_arrays().items()}
        self.sprites = {}
        self.sprite_aspect = {}
        for kind in ZTYPES:
            for fr in (0, 1):
                surf = make_zombie_surface(kind, fr)
                key = "z_%s_%d" % (kind, fr)
                self.sprites[key] = upload_rgba(surface_rgba(surf), False)
                self.sprite_aspect[key] = surf.get_width() / float(surf.get_height())
        for iid in ITEM_IDS:
            self.sprites["i_" + iid] = upload_rgba(surface_rgba(make_item_surface(iid), True), False)
        self.ui_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.ui_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, UI_W, UI_H, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        # formes partagees
        hw = CELL / 2.0
        self.door_panel = compile_quads(box_quads(-hw, 0, -0.15, hw, WALL_H, 0.15))
        self.door_planks = compile_quads(box_quads(-hw, 0.25, -0.2, hw, 2.55, 0.2))
        self.door_chain = compile_quads(box_quads(-hw, 0.3, -0.19, hw, 2.5, 0.19))
        self.cable_list = compile_quads(box_quads(-hw, 0, -0.12, hw, WALL_H, 0.12))
        self.world = None
        self.lists = {}
        self.cont_over = {}
        self.lamp_pos = np.zeros((0, 3))
        self.create_fbo()

    @staticmethod
    def _loc(prog, name):
        loc = glGetUniformLocation(prog, name)
        if loc == -1:
            loc = glGetUniformLocation(prog, name + "[0]")
        return loc

    # ---------------------------------------------------------------- FBO
    def create_fbo(self):
        self.destroy_fbo()
        self.fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        self.color_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.color_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.iw, self.ih, 0, GL_RGB, GL_UNSIGNED_BYTE, None)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.color_tex, 0)
        self.depth_rb = glGenRenderbuffers(1)
        glBindRenderbuffer(GL_RENDERBUFFER, self.depth_rb)
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, self.iw, self.ih)
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self.depth_rb)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("Framebuffer incomplet (code %s)" % status)

    def destroy_fbo(self):
        if self.fbo is not None:
            glDeleteFramebuffers(1, [self.fbo])
            glDeleteTextures([self.color_tex])
            glDeleteRenderbuffers(1, [self.depth_rb])
            self.fbo = self.color_tex = self.depth_rb = None

    def set_quality(self, index):
        self.iw, self.ih = QUALITY_LEVELS[index]
        self.create_fbo()

    # ---------------------------------------------------------------- construction du niveau
    def _free(self):
        for lst in list(self.lists.values()):
            glDeleteLists(lst, 1)
        for dct in self.cont_over.values():
            for lst in dct.values():
                glDeleteLists(lst, 1)
        self.lists, self.cont_over = {}, {}

    def build_world(self, w):
        self._free()
        self.world = w
        C, H = CELL, WALL_H
        B = defaultdict(list)
        rng = random.Random(w.idx * 977 + 3)
        wall_faces, floor_cells = [], []
        for cz in range(w.H):
            for cx in range(w.W):
                x0, z0, x1, z1 = cx * C, cz * C, (cx + 1) * C, (cz + 1) * C
                if w.walk_l[cz][cx]:
                    zn = w.zone_at(cx, cz)
                    ft = "exit" if (cx, cz) == w.exit_cell else zn["floor"]
                    B[ft].append(((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1), (0, 1, 0), 1, 1))
                    B["ceiling"].append(((x0, H, z0), (x1, H, z0), (x1, H, z1), (x0, H, z1), (0, -1, 0), 1, 1))
                    if (cx, cz) not in w.boxes and (cx, cz) not in w.doors and (cx, cz) != w.exit_cell:
                        floor_cells.append((cx, cz))
                else:
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if not w._walk(cx + dx, cz + dz):
                            continue
                        tex = w.zone_at(cx + dx, cz + dz)["wall"]
                        if dx == 1:
                            q = ((x1, 0, z0), (x1, 0, z1), (x1, H, z1), (x1, H, z0), (1, 0, 0))
                        elif dx == -1:
                            q = ((x0, 0, z0), (x0, 0, z1), (x0, H, z1), (x0, H, z0), (-1, 0, 0))
                        elif dz == 1:
                            q = ((x0, 0, z1), (x1, 0, z1), (x1, H, z1), (x0, H, z1), (0, 0, 1))
                        else:
                            q = ((x0, 0, z0), (x1, 0, z0), (x1, H, z0), (x0, H, z0), (0, 0, -1))
                        B[tex].append(q + (1, 1))
                        wall_faces.append((dx, dz, cx, cz, q))
        # decors : taches de sang au sol, griffures sur les murs
        for (cx, cz) in rng.sample(floor_cells, max(0, min(len(floor_cells) // 10, len(floor_cells)))):
            x, z = (cx + rng.uniform(0.25, 0.75)) * C, (cz + rng.uniform(0.25, 0.75)) * C
            s = rng.uniform(0.6, 1.3)
            B["blood"].append(((x - s, 0.012, z - s), (x + s, 0.012, z - s), (x + s, 0.012, z + s),
                               (x - s, 0.012, z + s), (0, 1, 0), 1, 1))
        for (dx, dz, cx, cz, q) in wall_faces:
            if rng.random() < 0.05:
                if dx != 0:
                    x, zc = q[0][0] + dx * 0.012, (cz + 0.5) * C
                    B["scratch"].append(((x, 0.9, zc - 0.7), (x, 0.9, zc + 0.7), (x, 2.1, zc + 0.7),
                                         (x, 2.1, zc - 0.7), (dx, 0, 0), 1, 1))
                else:
                    z, xc = q[0][2] + dz * 0.012, (cx + 0.5) * C
                    B["scratch"].append(((xc - 0.7, 0.9, z), (xc + 0.7, 0.9, z), (xc + 0.7, 2.1, z),
                                         (xc - 0.7, 2.1, z), (0, 0, dz), 1, 1))
        # lampes au plafond
        for l in w.lamps:
            x, z = l["x"], l["z"]
            B["lamp"].append(((x - 0.35, H - 0.01, z - 0.35), (x + 0.35, H - 0.01, z - 0.35),
                              (x + 0.35, H - 0.01, z + 0.35), (x - 0.35, H - 0.01, z + 0.35), (0, -1, 0), 1, 1))
        # accessoires
        for (kind, cx, cz) in w.props:
            tex, hx, hz, h = PROP_DEF[kind]
            x, z = (cx + 0.5) * C, (cz + 0.5) * C
            if kind == "T":
                B[tex] += box_quads(x - hx, 0.72, z - hz, x + hx, h, z + hz)
                for sx in (-1, 1):
                    for sz in (-1, 1):
                        lx, lz = x + sx * (hx - 0.08), z + sz * (hz - 0.08)
                        B[tex] += box_quads(lx - 0.05, 0, lz - 0.05, lx + 0.05, 0.72, lz + 0.05)
            else:
                B[tex] += box_quads(x - hx, 0, z - hz, x + hx, h, z + hz)
        for c in w.containers:
            tex, hx, hz, h = CONT_DEF[c.kind]
            B[tex] += box_quads(c.x - hx, 0, c.z - hz, c.x + hx, h, c.z + hz)
            g = 0.03
            self.cont_over[(c.cx, c.cz)] = {
                "planks": compile_quads(box_quads(c.x - hx - g, 0.04, c.z - hz - g, c.x + hx + g, h * 0.95, c.z + hz + g)),
                "lock": compile_quads(box_quads(c.x - 0.1, h * 0.5 - 0.1, c.z + hz, c.x + 0.1, h * 0.5 + 0.1, c.z + hz + 0.09)),
            }
        for tex, qs in B.items():
            self.lists[tex] = compile_quads(qs)
        # lampes (pour l'eclairage dynamique)
        if w.lamps:
            self.lamp_pos = np.array([[l["x"], l["y"], l["z"]] for l in w.lamps], dtype=np.float64)
            self.lamp_col = np.array([l["col"] for l in w.lamps], dtype=np.float64)
            self.lamp_flk = [l["flicker"] for l in w.lamps]
            self.lamp_alarm = [l["alarm"] for l in w.lamps]
        else:
            self.lamp_pos = np.zeros((0, 3))
            self.lamp_col = np.zeros((0, 3))
            self.lamp_flk, self.lamp_alarm = [], []

    # ---------------------------------------------------------------- eclairage
    @staticmethod
    def _view_rot(P):
        cr, sr = math.cos(-P["roll"]), math.sin(-P["roll"])
        cp, sp = math.cos(-P["pitch"]), math.sin(-P["pitch"])
        cy, sy = math.cos(-P["yaw"]), math.sin(-P["yaw"])
        Rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        return Rz @ Rx @ Ry

    def _lights(self, P, t):
        LP = np.zeros((4, 3), np.float32)
        LC = np.zeros((4, 3), np.float32)
        n = len(self.lamp_pos)
        if n:
            eye = np.array([P["x"], P["y"], P["z"]])
            d2 = ((self.lamp_pos - eye) ** 2).sum(axis=1)
            k = min(4, n)
            idx = np.argpartition(d2, k - 1)[:k] if n > k else np.arange(n)
            R = self._view_rot(P)
            for j, i in enumerate(idx):
                f = 1.0
                if self.lamp_flk[i] and math.sin(t * 21.0 + i * 7.3) * math.sin(t * 4.7 + i) > 0.78:
                    f = 0.15
                if self.lamp_alarm[i]:
                    f *= 0.45 + 0.55 * math.sin(t * 3.2) ** 2
                LP[j] = R @ (self.lamp_pos[i] - eye)
                LC[j] = self.lamp_col[i] * f * 1.1
        return LP, LC

    # ---------------------------------------------------------------- dessin
    def _sprite(self, tex, x, y, z, w, h, right, nrm):
        glBindTexture(GL_TEXTURE_2D, tex)
        rx, rz = right
        hw = w * 0.5
        glBegin(GL_QUADS)
        glNormal3f(*nrm)
        glTexCoord2f(0, 0); glVertex3f(x - rx * hw, y, z - rz * hw)
        glTexCoord2f(1, 0); glVertex3f(x + rx * hw, y, z + rz * hw)
        glTexCoord2f(1, 1); glVertex3f(x + rx * hw, y + h, z + rz * hw)
        glTexCoord2f(0, 1); glVertex3f(x - rx * hw, y + h, z - rz * hw)
        glEnd()

    def render(self, w, P, t):
        if w is not self.world:
            self.build_world(w)
        # ---- passe 1 : scene 3D basse resolution ----
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, self.iw, self.ih)
        fc = P["fogcol"]
        glClearColor(fc[0], fc[1], fc[2], 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        near, far = 0.05, 60.0
        top = near * math.tan(math.radians(P["fov"]) / 2.0)
        glFrustum(-top * self.iw / float(self.ih), top * self.iw / float(self.ih), -top, top, near, far)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(-math.degrees(P["roll"]), 0, 0, 1)
        glRotatef(-math.degrees(P["pitch"]), 1, 0, 0)
        glRotatef(-math.degrees(P["yaw"]), 0, 1, 0)
        glTranslatef(-P["x"], -P["y"], -P["z"])

        glUseProgram(self.scene_prog)
        glUniform1i(self.u["uTex"], 0)
        glUniform1f(self.u["uFlash"], P["flash"])
        glUniform3f(self.u["uAmb"], *P["amb"])
        glUniform3f(self.u["uFogCol"], *P["fogcol"])
        glUniform1f(self.u["uFogDen"], P["fogden"])
        LP, LC = self._lights(P, t)
        glUniform3fv(self.u["uLP"], 4, LP)
        glUniform3fv(self.u["uLC"], 4, LC)
        glActiveTexture(GL_TEXTURE0)

        for name, lst in self.lists.items():
            glBindTexture(GL_TEXTURE_2D, self.tex[name])
            glCallList(lst)
        # portes
        for d in w.doors.values():
            glBindTexture(GL_TEXTURE_2D, self.tex[d.tex])
            glPushMatrix()
            glTranslatef(d.x, d.open * WALL_H, d.z)
            if not d.axis_x:
                glRotatef(90, 0, 1, 0)
            glCallList(self.door_panel)
            if d.planks:
                glBindTexture(GL_TEXTURE_2D, self.tex["planks"])
                glCallList(self.door_planks)
            if d.chain:
                glBindTexture(GL_TEXTURE_2D, self.tex["chain"])
                glCallList(self.door_chain)
            glPopMatrix()
        # cables
        glBindTexture(GL_TEXTURE_2D, self.tex["cables"])
        for cb in w.cables:
            if cb["cut"]:
                continue
            glPushMatrix()
            glTranslatef(cb["x"], 0, cb["z"])
            if not cb["axis_x"]:
                glRotatef(90, 0, 1, 0)
            glCallList(self.cable_list)
            glPopMatrix()
        # verrous des coffres
        for c in w.containers:
            if c.opened or c.lock is None:
                continue
            ov = self.cont_over[(c.cx, c.cz)]
            if c.lock == "planks":
                glBindTexture(GL_TEXTURE_2D, self.tex["planks"])
                glCallList(ov["planks"])
            else:
                glBindTexture(GL_TEXTURE_2D, self.tex["padlock" if c.lock == "padlock" else "door_" + c.lock])
                glCallList(ov["lock"])
        # sprites : zombies et objets
        ex, ey, ez = P["x"], P["y"], P["z"]
        right = (math.cos(P["yaw"]), -math.sin(P["yaw"]))

        def nrm(x, y, z):
            dx, dy, dz = ex - x, ey - y, ez - z
            l = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            return (dx / l, dy / l, dz / l)

        for it in w.items:
            if it.taken or math.hypot(it.x - ex, it.z - ez) > 22:
                continue
            y = it.y + 0.05 * math.sin(t * 2.0 + it.phase)
            self._sprite(self.sprites["i_" + it.id], it.x, y, it.z, 0.42, 0.42, right, nrm(it.x, y + 0.2, it.z))
        for z in w.zombies:
            if math.hypot(z.x - ex, z.z - ez) > 32:
                continue
            fr = int(z.anim * 2) % 2 if z.moving else 0
            key = "z_%s_%d" % (z.kind, fr)
            h = z.T["h"]
            wd = h * self.sprite_aspect[key]
            if z.dead:
                self._sprite(self.sprites[key], z.x, 0.0, z.z, wd * 1.1, h * 0.22, right, nrm(z.x, 0.2, z.z))
            else:
                yb = abs(math.sin(z.anim * 3.0)) * 0.04 if z.moving else 0.0
                self._sprite(self.sprites[key], z.x, yb, z.z, wd, h, right, nrm(z.x, h * 0.5, z.z))

        # ---- passe 2 : mise a l'echelle pixelisee + post-traitement ----
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, self.win_w, self.win_h)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)
        glDisable(GL_DEPTH_TEST)
        glUseProgram(self.post_prog)
        glUniform1i(self.u["puScene"], 0)
        glUniform1f(self.u["puTime"], t)
        glUniform2f(self.u["puRes"], float(self.iw), float(self.ih))
        glUniform1f(self.u["puHurt"], P["hurt"])
        glUniform1f(self.u["puFear"], P["fear"])
        glUniform1f(self.u["puFade"], P["fade"])
        glBindTexture(GL_TEXTURE_2D, self.color_tex)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(-1, -1)
        glTexCoord2f(1, 0); glVertex2f(1, -1)
        glTexCoord2f(1, 1); glVertex2f(1, 1)
        glTexCoord2f(0, 1); glVertex2f(-1, 1)
        glEnd()
        glUseProgram(0)

    def draw_ui(self, surf):
        data = pygame.image.tostring(surf, "RGBA", True)
        glBindTexture(GL_TEXTURE_2D, self.ui_tex)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, UI_W, UI_H, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glUseProgram(0)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1, 1, 1, 1)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(-1, -1)
        glTexCoord2f(1, 0); glVertex2f(1, -1)
        glTexCoord2f(1, 1); glVertex2f(1, 1)
        glTexCoord2f(0, 1); glVertex2f(-1, 1)
        glEnd()
        glDisable(GL_BLEND)


# =============================================================================
# INTERFACE (dessinee avec pygame sur une surface 640x360 puis mise a l'echelle)
# =============================================================================
class UI:
    SIZES = {"s": 15, "n": 19, "m": 25, "l": 38, "xl": 66}

    def __init__(self):
        self.surf = pygame.Surface((UI_W, UI_H), pygame.SRCALPHA)
        self.fonts = {k: pygame.font.Font(None, v) for k, v in self.SIZES.items()}
        self.cache = {}
        self.icons = {}

    def clear(self):
        self.surf.fill((0, 0, 0, 0))

    def _img(self, s, size, color):
        key = (s, size, color)
        im = self.cache.get(key)
        if im is None:
            if len(self.cache) > 700:
                self.cache.clear()
            im = self.fonts[size].render(s, False, color)
            self.cache[key] = im
        return im

    def text(self, s, x, y, size="n", color=(215, 215, 215), align="left", shadow=True):
        if not s:
            return 0
        color = tuple(int(c) for c in color[:3])
        im = self._img(s, size, color)
        w = im.get_width()
        if align == "center":
            x -= w // 2
        elif align == "right":
            x -= w
        if shadow:
            self.surf.blit(self._img(s, size, (0, 0, 0)), (x + 1, y + 1))
        self.surf.blit(im, (x, y))
        return w

    def width(self, s, size="n"):
        return self.fonts[size].size(s)[0]

    def rect(self, x, y, w, h, color):
        pygame.draw.rect(self.surf, color, (x, y, w, h))

    def frame(self, x, y, w, h, color):
        pygame.draw.rect(self.surf, color, (x, y, w, h), 1)

    def icon(self, iid, x, y, scale=2):
        key = (iid, scale)
        im = self.icons.get(key)
        if im is None:
            base = make_item_surface(iid)
            im = pygame.transform.scale(base, (16 * scale, 16 * scale))
            self.icons[key] = im
        self.surf.blit(im, (x, y))

    def wrap(self, s, size, maxw):
        lines = []
        for para in s.split("\n"):
            cur = ""
            for word in para.split(" "):
                test = (cur + " " + word).strip()
                if self.width(test, size) <= maxw:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines


def fmt_time(sec):
    m = int(sec // 60)
    return "%dh%02d" % (m // 60, m % 60)


UP_KEYS = (pygame.K_UP, pygame.K_z, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_q, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)


def draw_hud(ui, app, g):
    p = g.player
    cx, cy = UI_W // 2, UI_H // 2
    # barres
    bars = ((tr("hud_hp"), p.hp / p.max_hp, (200, 40, 40)),
            (tr("hud_stamina"), p.stamina / 100.0, (140, 120, 40) if p.exhausted else (220, 200, 60)),
            (tr("hud_battery"), p.battery / 100.0, (80, 200, 230)))
    for i, (lab, f, col) in enumerate(bars):
        y = 314 + i * 14
        ui.text(lab, 10, y - 3, "s", (190, 190, 200))
        ui.rect(86, y, 110, 8, (0, 0, 0, 150))
        ui.rect(86, y, int(110 * max(0.0, min(1.0, f))), 8, col + (235,))
        ui.frame(86, y, 110, 8, (160, 160, 170, 200))
    if p.bleeding:
        ui.text(tr("hud_bleeding"), 10, 292, "s", (230, 60, 60) if int(g.t * 3) % 2 else (150, 30, 30))
    # objets cles
    x = UI_W - 40
    for iid, n in p.inv.slots:
        if ITEM_KIND.get(iid) in ("key", "tool"):
            ui.icon(iid, x, UI_H - 44, 2)
            x -= 36
    # bruit
    nz = max(0.0, min(1.0, g.noise_disp / 10.0))
    ui.text(tr("hud_noise"), cx - 60, UI_H - 22, "s", (170, 170, 180))
    ui.rect(cx - 20, UI_H - 18, 80, 5, (0, 0, 0, 150))
    ui.rect(cx - 20, UI_H - 18, int(80 * nz), 5, (int(60 + 190 * nz), int(220 - 170 * nz), 60, 230))
    # viseur + invite
    tgt = g.target
    col = (255, 230, 120, 230) if (tgt and tgt["ok"]) else (255, 255, 255, 150)
    ui.rect(cx - 1, cy - 1, 2, 2, col)
    if tgt:
        ui.text(tgt["prompt"], cx, cy + 16, "n", (235, 235, 235) if tgt["ok"] else (210, 150, 150), "center")
        if g.hold > 0 and tgt["hold"] > 0:
            f = min(1.0, g.hold / tgt["hold"])
            ui.rect(cx - 40, cy + 36, 80, 6, (0, 0, 0, 170))
            ui.rect(cx - 40, cy + 36, int(80 * f), 6, (230, 190, 60, 240))
            ui.frame(cx - 40, cy + 36, 80, 6, (200, 200, 200, 200))
    # messages
    for i, (txt, ttl) in enumerate(g.msgs):
        a = max(0.0, min(1.0, ttl))
        ui.text(txt, 10, 10 + i * 17, "n", (235 * a, 235 * a, 220 * a))
    if g.toast_t > 0:
        a = min(1.0, g.toast_t / 1.5)
        ui.text(g.toast, cx, 62, "m", (225 * a, 60 * a, 60 * a), "center")


# =============================================================================
# ECRANS ET MENUS
# =============================================================================
class Screen:
    dim = 120

    def __init__(self, app):
        self.app = app

    def on_event(self, ev):
        pass

    def update(self, dt):
        pass

    def draw(self, ui):
        pass

    def back(self):
        self.app.pop()


class ListScreen(Screen):
    title_key = ""
    y0 = 120
    row_h = 24
    vis = 12

    def __init__(self, app):
        super().__init__(app)
        self.index = 0
        self.scroll = 0
        self.items = []
        self.rebuild()
        for i, it in enumerate(self.items):
            if it.get("enabled", True):
                self.index = i
                break

    def build_items(self):
        return []

    def rebuild(self):
        self.items = self.build_items()
        self.index = max(0, min(self.index, len(self.items) - 1))
        self._fix_scroll()

    def _fix_scroll(self):
        if self.index < self.scroll:
            self.scroll = self.index
        if self.index >= self.scroll + self.vis:
            self.scroll = self.index - self.vis + 1
        self.scroll = max(0, self.scroll)

    def header(self, ui):
        ui.text(tr(self.title_key), UI_W // 2, 34, "l", (220, 60, 60), "center")

    def move(self, d):
        n = len(self.items)
        if not n:
            return
        for _ in range(n):
            self.index = (self.index + d) % n
            if self.items[self.index].get("enabled", True):
                break
        self._fix_scroll()
        self.app.audio.play("ui", 0.6)

    def activate(self):
        if not self.items:
            return
        it = self.items[self.index]
        if not it.get("enabled", True):
            return
        self.app.audio.play("ui", 0.8)
        if "action" in it:
            it["action"]()
        elif "change" in it:
            it["change"](1)

    def change(self, d):
        if not self.items:
            return
        it = self.items[self.index]
        if "change" in it and it.get("enabled", True):
            self.app.audio.play("ui", 0.5)
            it["change"](d)

    def row_at(self, x, y):
        if y < self.y0:
            return -1
        i = self.scroll + int((y - self.y0) // self.row_h)
        return i if 0 <= i < len(self.items) and i < self.scroll + self.vis else -1

    def on_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            k = ev.key
            if k in UP_KEYS:
                self.move(-1)
            elif k in DOWN_KEYS:
                self.move(1)
            elif k in LEFT_KEYS:
                self.change(-1)
            elif k in RIGHT_KEYS:
                self.change(1)
            elif k in OK_KEYS:
                self.activate()
            elif k == pygame.K_ESCAPE:
                self.back()
        elif ev.type == pygame.MOUSEMOTION:
            x, y = self.app.ui_pos(ev.pos)
            i = self.row_at(x, y)
            if i >= 0 and i != self.index and self.items[i].get("enabled", True):
                self.index = i
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            x, y = self.app.ui_pos(ev.pos)
            i = self.row_at(x, y)
            if i >= 0 and self.items[i].get("enabled", True):
                self.index = i
                it = self.items[i]
                if "change" in it and "action" not in it and x >= 400:
                    self.change(1 if x >= 470 else -1)
                else:
                    self.activate()

    def draw(self, ui):
        ui.rect(0, 0, UI_W, UI_H, (0, 0, 0, self.dim))
        self.header(ui)
        t = self.app.t
        for row, i in enumerate(range(self.scroll, min(len(self.items), self.scroll + self.vis))):
            it = self.items[i]
            y = self.y0 + row * self.row_h
            sel = i == self.index
            en = it.get("enabled", True)
            if not en:
                col = (90, 90, 100)
            elif sel:
                col = (255, 80, 80) if int(t * 20) % 9 else (255, 170, 170)
            else:
                col = (175, 175, 185)
            if "value" not in it:
                ui.text(it["label"], UI_W // 2, y, "m", col, "center")
                if sel:
                    w = ui.width(it["label"], "m")
                    ui.text(">", UI_W // 2 - w // 2 - 18, y, "m", col)
                    ui.text("<", UI_W // 2 + w // 2 + 10, y, "m", col)
            else:
                ui.text(it["label"], 110, y + 2, "n", col)
                v = ("< %s >" % it["value"]) if (sel and "change" in it) else it["value"]
                ui.text(v, 470, y + 2, "n", col, "center")
        if self.scroll > 0:
            ui.text("^", UI_W // 2, self.y0 - 14, "n", (150, 150, 160), "center")
        if self.scroll + self.vis < len(self.items):
            ui.text("v", UI_W // 2, self.y0 + self.vis * self.row_h, "n", (150, 150, 160), "center")


def btn(label, action, enabled=True):
    return dict(label=label, action=action, enabled=enabled)


class MainMenu(ListScreen):
    y0 = 128
    row_h = 27
    dim = 80

    def header(self, ui):
        t = self.app.t
        ox = random.choice((-3, 3)) if random.random() < 0.04 else 0
        ui.text(GAME_NAME, UI_W // 2 + ox + 2, 30, "xl", (110, 0, 130), "center", False)
        col = (205, 25, 35) if int(t * 9) % 23 else (255, 255, 255)
        ui.text(GAME_NAME, UI_W // 2 + ox, 28, "xl", col, "center")
        ui.text(GAME_VERSION, UI_W // 2, 86, "n", (140, 140, 165), "center")

    def build_items(self):
        a = self.app
        return [btn(tr("menu_continue"), a.continue_game, bool(a.db.list_saves())),
                btn(tr("menu_new"), a.new_game_dialog),
                btn(tr("menu_saves"), lambda: a.push(SavesMenu(a))),
                btn(tr("menu_options"), lambda: a.push(OptionsMenu(a))),
                btn(tr("menu_language"), lambda: a.push(LanguageMenu(a))),
                btn(tr("menu_credits"), lambda: a.push(CreditsScreen(a))),
                btn(tr("menu_quit"), a.quit)]

    def back(self):
        pass


class SavesMenu(ListScreen):
    title_key = "saves_title"
    y0 = 84
    row_h = 24
    vis = 10

    def build_items(self):
        a = self.app
        items = [btn(tr("saves_new"), a.new_game_dialog)]
        for s in a.db.list_saves():
            label = tr("save_line", s["name"], s["level"] + 1, fmt_time(s["playtime"]))
            items.append(btn(label, (lambda sv=s: a.push(SaveActions(a, sv)))))
        items.append(btn(tr("back"), self.back))
        return items


class SaveActions(ListScreen):
    y0 = 130

    def __init__(self, app, save):
        self.save = save
        super().__init__(app)

    def header(self, ui):
        ui.text(self.save["name"], UI_W // 2, 40, "l", (220, 60, 60), "center")
        ui.text(tr("save_line_info", self.save["level"] + 1, fmt_time(self.save["playtime"]),
                   time.strftime("%d/%m/%Y %H:%M", time.localtime(self.save["updated"]))),
                UI_W // 2, 84, "n", (150, 150, 170), "center")

    def build_items(self):
        a, s = self.app, self.save
        return [btn(tr("save_load"), lambda: a.load_save(s["id"])),
                btn(tr("save_rename"), lambda: a.push(TextInput(a, tr("enter_name"), s["name"], self._rename))),
                btn(tr("save_delete"), lambda: a.push(Confirm(a, tr("confirm_delete", s["name"]), self._delete))),
                btn(tr("back"), self.back)]

    def _rename(self, name):
        self.app.db.rename_save(self.save["id"], name)
        self.save["name"] = name

    def _delete(self):
        self.app.db.delete_save(self.save["id"])
        if self.app.save_id == self.save["id"]:
            self.app.save_id = None
        self.app.pop()


class TextInput(Screen):
    def __init__(self, app, prompt, initial, on_ok, maxlen=20, prefill=True):
        super().__init__(app)
        self.prompt, self.initial, self.on_ok, self.maxlen = prompt, initial, on_ok, maxlen
        self.text = initial if prefill else ""

    def on_event(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            txt = self.text.strip() or self.initial
            self.app.pop()
            self.on_ok(txt)
        elif ev.key == pygame.K_ESCAPE:
            self.app.pop()
        elif ev.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif ev.unicode and ev.unicode.isprintable() and len(self.text) < self.maxlen:
            self.text += ev.unicode

    def draw(self, ui):
        ui.rect(0, 0, UI_W, UI_H, (0, 0, 0, 150))
        ui.text(self.prompt, UI_W // 2, 120, "m", (220, 60, 60), "center")
        ui.rect(170, 160, 300, 30, (10, 10, 16, 230))
        ui.frame(170, 160, 300, 30, (200, 60, 60, 255))
        cur = "_" if int(self.app.t * 2) % 2 == 0 else " "
        if self.text:
            ui.text(self.text + cur, 180, 168, "m", (235, 235, 235))
        else:
            ui.text(cur, 180, 168, "m", (235, 235, 235))
            ui.text(self.initial, 192, 168, "m", (95, 95, 110))
        ui.text(tr("input_hint"), UI_W // 2, 210, "n", (150, 150, 165), "center")


class Confirm(ListScreen):
    y0 = 170
    row_h = 28

    def __init__(self, app, question, on_yes):
        self.question, self.on_yes = question, on_yes
        super().__init__(app)
        self.index = 1

    def header(self, ui):
        ui.text(self.question, UI_W // 2, 110, "m", (230, 90, 90), "center")

    def build_items(self):
        return [btn(tr("yes"), self._yes), btn(tr("no"), self.back)]

    def _yes(self):
        self.app.pop()
        self.on_yes()


class OptionsMenu(ListScreen):
    title_key = "opt_title"
    y0 = 78
    row_h = 21
    vis = 12

    def build_items(self):
        a = self.app
        s = a.settings

        def slider(key, label, lo, hi, step, fmt):
            def ch(d):
                s[key] = max(lo, min(hi, round(s[key] + d * step, 3)))
                self.after(key)
            return dict(label=tr(label), value=fmt(s[key]), change=ch)

        def toggle(key, label):
            def ch(d):
                s[key] = not s[key]
                self.after(key)
            return dict(label=tr(label), value=tr("on") if s[key] else tr("off"), change=ch)

        def choice(key, label, options, fmt):
            def ch(d):
                s[key] = (s[key] + d) % len(options) if key == "quality" else options[(options.index(s[key]) + d) % len(options)]
                self.after(key)
            return dict(label=tr(label), value=fmt(s[key]), change=ch)

        pct = lambda v: "%d%%" % round(v * 100)
        return [
            slider("sensitivity", "opt_sens", 0.03, 0.40, 0.01, lambda v: "%.2f" % v),
            toggle("invert_y", "opt_invert"),
            toggle("headbob", "opt_headbob"),
            slider("fov", "opt_fov", 60, 100, 5, lambda v: "%d" % v),
            slider("master", "opt_master", 0.0, 1.0, 0.05, pct),
            slider("music", "opt_music", 0.0, 1.0, 0.05, pct),
            slider("sfx", "opt_sfx", 0.0, 1.0, 0.05, pct),
            choice("quality", "opt_quality", QUALITY_LEVELS, lambda v: "%dx%d" % QUALITY_LEVELS[v]),
            choice("fps", "opt_fps", FPS_CHOICES, lambda v: "%d" % v),
            btn(tr("opt_controls"), lambda: a.push(ControlsMenu(a))),
            btn(tr("back"), self.back),
        ]

    def after(self, key):
        a = self.app
        if key == "quality":
            a.renderer.set_quality(a.settings["quality"])
        if key in ("master", "music", "sfx"):
            a.audio.apply_settings(a.settings)
            a.audio.play("ui", 0.8)
        a.save_settings()
        self.rebuild()

    def back(self):
        self.app.save_settings()
        self.app.pop()


class ControlsMenu(ListScreen):
    title_key = "opt_controls"
    y0 = 66
    row_h = 21
    vis = 13

    def __init__(self, app):
        self.waiting = None
        super().__init__(app)

    def build_items(self):
        a = self.app
        items = []
        for act in ACTION_ORDER:
            val = "..." if self.waiting == act else a.key_name(act)
            items.append(dict(label=tr("act_" + act), value=val, action=(lambda x=act: self._wait(x))))
        items.append(btn(tr("opt_reset_keys"), self._reset))
        items.append(btn(tr("back"), self.back))
        return items

    def _wait(self, act):
        self.waiting = act
        self.rebuild()

    def _reset(self):
        self.app.settings["keys"] = default_keys()
        self.app.save_settings()
        self.rebuild()

    def on_event(self, ev):
        if self.waiting:
            if ev.type == pygame.KEYDOWN:
                if ev.key != pygame.K_ESCAPE:
                    keys = self.app.settings["keys"]
                    old = keys[self.waiting]
                    for other, code in keys.items():
                        if code == ev.key and other != self.waiting:
                            keys[other] = old
                    keys[self.waiting] = ev.key
                    self.app.save_settings()
                self.waiting = None
                self.rebuild()
            return
        super().on_event(ev)

    def back(self):
        self.app.save_settings()
        self.app.pop()


class LanguageMenu(ListScreen):
    title_key = "menu_language"
    y0 = 130
    row_h = 30

    def build_items(self):
        cur = self.app.settings["language"]
        return [btn(("> " if cur == "fr" else "") + "Francais", lambda: self._set("fr")),
                btn(("> " if cur == "en" else "") + "English", lambda: self._set("en")),
                btn(tr("back"), self.back)]

    def _set(self, code):
        self.app.settings["language"] = code
        set_language(code)
        self.app.save_settings()
        self.rebuild()


class CreditsScreen(Screen):
    def on_event(self, ev):
        if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.app.pop()

    def draw(self, ui):
        ui.rect(0, 0, UI_W, UI_H, (0, 0, 0, 170))
        ui.text(tr("menu_credits"), UI_W // 2, 40, "l", (220, 60, 60), "center")
        y = 110
        for line in tr("credits_text").split("\n"):
            ui.text(line, UI_W // 2, y, "n", (200, 200, 210), "center")
            y += 22
        ui.text(tr("press_any"), UI_W // 2, 320, "n", (130, 130, 150), "center")


class PauseMenu(ListScreen):
    title_key = "paused"
    y0 = 120
    row_h = 30

    def build_items(self):
        a = self.app
        return [btn(tr("resume"), self.back),
                btn(tr("save_now"), lambda: a.save_game(auto=False)),
                btn(tr("menu_options"), lambda: a.push(OptionsMenu(a))),
                btn(tr("to_menu"), lambda: a.push(Confirm(a, tr("confirm_menu"), a.to_menu)))]


class DeathScreen(ListScreen):
    y0 = 190
    row_h = 30
    dim = 150

    def header(self, ui):
        ui.text(tr("you_died"), UI_W // 2, 90, "xl", (200, 20, 20), "center")

    def build_items(self):
        a = self.app
        return [btn(tr("reload_last"), lambda: a.load_save(a.save_id) if a.save_id else a.to_menu()),
                btn(tr("to_menu"), a.to_menu)]

    def back(self):
        pass


class EndScreen(ListScreen):
    y0 = 250
    row_h = 30
    dim = 170

    def header(self, ui):
        ui.text(tr("end_title"), UI_W // 2, 60, "l", (220, 60, 60), "center")
        y = 120
        for line in tr("end_text").split("\n"):
            ui.text(line, UI_W // 2, y, "n", (200, 200, 210), "center")
            y += 22

    def build_items(self):
        return [btn(tr("to_menu"), self.app.to_menu)]

    def back(self):
        pass


class InventoryScreen(Screen):
    dim = 160
    COLS, ROWS, SLOT = 4, 4, 46
    OX, OY = 36, 66

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.sel = 0

    def _n(self):
        return len(self.game.player.inv.slots)

    def _clamp(self):
        self.sel = max(0, min(max(0, self._n() - 1), self.sel))

    def on_event(self, ev):
        K = self.app.settings["keys"]
        if ev.type == pygame.KEYDOWN:
            k = ev.key
            if k in (pygame.K_ESCAPE, pygame.K_TAB) or k == K["inventory"]:
                self.app.pop()
            elif k in LEFT_KEYS:
                self.sel -= 1
            elif k in RIGHT_KEYS:
                self.sel += 1
            elif k in UP_KEYS:
                self.sel -= self.COLS
            elif k in DOWN_KEYS:
                self.sel += self.COLS
            elif k in OK_KEYS or k == K["interact"]:
                self.game.use_item(self.sel)
            self._clamp()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            x, y = self.app.ui_pos(ev.pos)
            c, r = int((x - self.OX) // self.SLOT), int((y - self.OY) // self.SLOT)
            if 0 <= c < self.COLS and 0 <= r < self.ROWS and x >= self.OX and y >= self.OY:
                i = r * self.COLS + c
                if i < self._n():
                    if i == self.sel:
                        self.game.use_item(i)
                    self.sel = i
            elif 260 <= x <= 400 and 300 <= y <= 322:
                self.game.use_item(self.sel)
            self._clamp()

    def draw(self, ui):
        inv = self.game.player.inv
        self._clamp()
        ui.rect(0, 0, UI_W, UI_H, (0, 0, 0, self.dim))
        ui.text(tr("inventory"), 36, 30, "l", (220, 60, 60))
        ui.text("%d/%d" % (len(inv.slots), inv.CAP), 220, 38, "n", (150, 150, 165))
        for i in range(self.COLS * self.ROWS):
            c, r = i % self.COLS, i // self.COLS
            x, y = self.OX + c * self.SLOT, self.OY + r * self.SLOT
            ui.rect(x, y, self.SLOT - 4, self.SLOT - 4, (20, 22, 30, 230))
            ui.frame(x, y, self.SLOT - 4, self.SLOT - 4, (255, 90, 90, 255) if i == self.sel and i < self._n() else (70, 74, 90, 255))
            if i < self._n():
                iid, n = inv.slots[i]
                ui.icon(iid, x + 5, y + 5, 2)
                if n > 1:
                    ui.text("x%d" % n, x + self.SLOT - 6, y + self.SLOT - 18, "s", (240, 240, 200), "right")
        # description
        px, py, pw = 250, 66, 360
        ui.rect(px, py, pw, 220, (14, 16, 22, 230))
        ui.frame(px, py, pw, 220, (90, 60, 70, 255))
        if self._n():
            iid = inv.slots[self.sel][0]
            kind = ITEM_KIND.get(iid, "tool")
            ui.icon(iid, px + 10, py + 10, 3)
            ui.text(tr("item_" + iid), px + 68, py + 12, "m", (235, 235, 235))
            ui.text(tr("kind_" + kind), px + 68, py + 36, "n", (150, 150, 170))
            y = py + 66
            for line in ui.wrap(tr("itemd_" + iid), "n", pw - 24):
                ui.text(line, px + 12, y, "n", (200, 200, 210))
                y += 18
            if kind == "use":
                ui.rect(260, 300, 140, 22, (60, 20, 24, 240))
                ui.frame(260, 300, 140, 22, (230, 80, 80, 255))
                ui.text(tr("use"), 330, 303, "n", (240, 200, 200), "center")
        else:
            ui.text(tr("inv_empty"), px + pw // 2, py + 100, "n", (150, 150, 165), "center")
        ui.text(tr("inv_hint"), UI_W // 2, 338, "s", (130, 130, 150), "center")


# =============================================================================
# APPLICATION
# =============================================================================
class App:
    def __init__(self):
        try:
            pygame.mixer.pre_init(22050, -16, 2, 512)
        except Exception:
            pass
        pygame.init()
        self.db = Database()
        self.settings = self.db.load_settings()
        set_language(self.settings["language"])
        pygame.display.set_caption(GAME_TITLE)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        try:
            self.screen = pygame.display.set_mode((WIN_W, WIN_H), flags, vsync=1)
        except TypeError:
            self.screen = pygame.display.set_mode((WIN_W, WIN_H), flags)
        self.win_w, self.win_h = self.screen.get_size()
        print("[%s] OpenGL : %s | GPU : %s" % (GAME_TITLE, glGetString(GL_VERSION).decode(),
                                              glGetString(GL_RENDERER).decode()))
        self.audio = Audio(self.settings)
        self.renderer = Renderer(self.win_w, self.win_h, self.settings["quality"])
        self.ui = UI()
        self.clock = pygame.time.Clock()
        self.t = 0.0
        self.running = True
        self.mode = "menu"
        self.stack = []
        self.game = None
        self.save_id = None
        self.fps_t, self.fps_n = 0.0, 0
        self.menu_world = World(0)
        self.renderer.build_world(self.menu_world)
        self.push(MainMenu(self))

    # ---------------------------------------------------------------- utilitaires
    def key_name(self, action):
        n = pygame.key.name(self.settings["keys"][action])
        return (n or "?").upper()

    def ui_pos(self, pos):
        return pos[0] * UI_W / float(self.win_w), pos[1] * UI_H / float(self.win_h)

    def save_settings(self):
        self.db.save_settings(self.settings)

    def quit(self):
        self.running = False

    def push(self, screen):
        self.stack.append(screen)
        self.sync_input()

    def pop(self):
        if self.stack:
            self.stack.pop()
        if self.stack and hasattr(self.stack[-1], "rebuild"):
            self.stack[-1].rebuild()
        self.sync_input()

    def sync_input(self):
        free = self.mode == "game" and not self.stack
        pygame.event.set_grab(free)
        pygame.mouse.set_visible(not free)
        if free:
            pygame.key.set_repeat()
        else:
            pygame.key.set_repeat(350, 45)
        pygame.mouse.get_rel()

    # ---------------------------------------------------------------- parties
    def new_game_dialog(self):
        n = len(self.db.list_saves()) + 1
        self.push(TextInput(self, tr("enter_name"), tr("default_save", n), self.new_game, prefill=False))

    def new_game(self, name):
        self.save_id = self.db.create_save(name)
        g = Game(self, 0)
        g.need_autosave = True
        self.begin(g)

    def begin(self, game):
        self.game = game
        self.mode = "game"
        self.stack = []
        self.renderer.build_world(game.world)
        self.sync_input()

    def continue_game(self):
        s = self.db.list_saves()
        if s:
            self.load_save(s[0]["id"])

    def load_save(self, sid):
        data = self.db.read_save(sid)
        self.save_id = sid
        if not data:
            g = Game(self, 0)
            g.need_autosave = True
            self.begin(g)
            return
        lvl = max(0, min(len(LEVELS) - 1, int(data.get("level", 0))))
        g = Game(self, lvl)
        g.load_state(data)
        g.toast_t = 3.0
        self.begin(g)

    def save_game(self, auto=False):
        g = self.game
        if g is None or self.save_id is None:
            return
        self.db.write_save(self.save_id, g.idx, g.playtime, g.get_state())
        g.say(tr("m_autosaved") if auto else tr("m_saved"), 2.5 if auto else 3.5)

    def next_level(self):
        g = self.game
        if g.idx + 1 >= len(LEVELS):
            self.push(EndScreen(self))
            return
        ng = Game(self, g.idx + 1, g.save_carry())
        ng.need_autosave = True
        self.begin(ng)

    def to_menu(self):
        self.mode = "menu"
        self.game = None
        self.stack = []
        self.renderer.build_world(self.menu_world)
        self.push(MainMenu(self))

    # ---------------------------------------------------------------- boucle
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
            return
        if self.mode == "game" and not self.stack:
            K = self.settings["keys"]
            g = self.game
            if ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_ESCAPE:
                    self.push(PauseMenu(self))
                elif k == K["inventory"] or k == pygame.K_TAB:
                    self.push(InventoryScreen(self, g))
                elif k == K["flashlight"]:
                    g.toggle_flashlight()
                elif k == K["battery"]:
                    g.reload_battery()
                elif k == K["interact"]:
                    g.on_interact_down()
                elif k == K["action"]:
                    g.attack()
            elif ev.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                self.push(PauseMenu(self))
        elif self.stack:
            self.stack[-1].on_event(ev)

    def update(self, dt):
        self.t += dt
        if self.mode == "game":
            g = self.game
            if self.stack:
                self.stack[-1].update(dt)
                self.audio.update(dt, 0.0, True)
            else:
                keys = pygame.key.get_pressed()
                K = self.settings["keys"]
                inp = dict(fwd=int(bool(keys[K["forward"]])) - int(bool(keys[K["back"]])),
                           side=int(bool(keys[K["right"]])) - int(bool(keys[K["left"]])),
                           run=bool(keys[K["run"]]), crouch=bool(keys[K["crouch"]]),
                           interact=bool(keys[K["interact"]]), mouse=pygame.mouse.get_rel())
                g.update(dt, inp)
                self.audio.update(dt, 1.0 if g.any_chasing() else 0.0, True)
                if g.dead:
                    self.push(DeathScreen(self))
                elif g.exit_reached:
                    self.next_level()
        else:
            if self.stack:
                self.stack[-1].update(dt)
            self.audio.update(dt, 0.0, False)

    def menu_params(self):
        sx, sz = self.menu_world.start
        t = self.t
        return dict(x=sx, y=1.5, z=sz, yaw=t * 0.12, pitch=-0.05, roll=0.0, fov=70,
                    flash=1.0 if int(t * 3) % 11 else 0.3, amb=(0.07, 0.09, 0.09),
                    fogcol=(0.03, 0.04, 0.04), fogden=0.1, hurt=0.0,
                    fear=0.15 + 0.1 * math.sin(t), fade=min(1.0, t / 2.0))

    def draw(self):
        ui = self.ui
        ui.clear()
        if self.mode == "game":
            g = self.game
            self.renderer.render(g.world, g.render_params(), self.t)
            draw_hud(ui, self, g)
        else:
            self.renderer.render(self.menu_world, self.menu_params(), self.t)
        if self.stack:
            self.stack[-1].draw(ui)
        self.renderer.draw_ui(ui.surf)

    def run(self):
        try:
            while self.running:
                dt = min(self.clock.tick(self.settings["fps"]) / 1000.0, 0.05)
                for ev in pygame.event.get():
                    self.handle_event(ev)
                self.update(dt)
                self.draw()
                pygame.display.flip()
                self.fps_n += 1
                self.fps_t += dt
                if self.fps_t >= 0.5:
                    pygame.display.set_caption("%s  |  %d FPS" % (GAME_TITLE, self.fps_n / self.fps_t))
                    self.fps_n, self.fps_t = 0, 0.0
        finally:
            try:
                if self.game is not None and self.save_id is not None and not self.game.dead:
                    self.save_game(auto=True)
            except Exception:
                pass
            try:
                pygame.event.set_grab(False)
                pygame.mouse.set_visible(True)
            except Exception:
                pass
            try:
                self.renderer.destroy_fbo()
            except Exception:
                pass
            self.audio.shutdown()
            pygame.quit()


def main():
    import traceback
    try:
        App().run()
    except Exception:
        traceback.print_exc()
        try:
            pygame.quit()
        except Exception:
            pass


# =============================================================================
# TEXTES (FR par defaut / EN)
# =============================================================================
STRINGS = {
    "fr": {
        "menu_continue": "CONTINUER", "menu_new": "NOUVELLE PARTIE", "menu_saves": "MES PARTIES",
        "menu_options": "PARAMETRES", "menu_language": "LANGUE", "menu_credits": "CREDITS",
        "menu_quit": "QUITTER", "back": "RETOUR",
        "saves_title": "MES PARTIES", "saves_new": "+ NOUVELLE PARTIE",
        "save_line": "{0}  -  Niv.{1}  -  {2}", "save_line_info": "Niveau {0}  -  Temps de jeu {1}  -  {2}",
        "save_load": "CHARGER", "save_rename": "RENOMMER", "save_delete": "SUPPRIMER",
        "confirm_delete": "Supprimer la partie \"{0}\" ?", "enter_name": "Nom de la partie",
        "default_save": "Partie {0}", "input_hint": "Entree : valider    Echap : annuler",
        "yes": "OUI", "no": "NON", "on": "OUI", "off": "NON",
        "opt_title": "PARAMETRES", "opt_sens": "Sensibilite souris", "opt_invert": "Inverser l'axe Y",
        "opt_headbob": "Mouvement de tete", "opt_fov": "Champ de vision", "opt_master": "Volume general",
        "opt_music": "Volume musique", "opt_sfx": "Volume effets", "opt_quality": "Resolution interne",
        "opt_fps": "Images par seconde", "opt_controls": "TOUCHES...", "opt_reset_keys": "REINITIALISER LES TOUCHES",
        "act_forward": "Avancer", "act_back": "Reculer", "act_left": "Gauche", "act_right": "Droite",
        "act_interact": "Interagir", "act_run": "Courir", "act_crouch": "S'accroupir",
        "act_flashlight": "Lampe torche", "act_battery": "Changer la batterie", "act_inventory": "Inventaire",
        "act_action": "Frapper / pousser",
        "credits_text": "KURTOS LAB - Beta v0.1\nJeu d'horreur et de survie\nPython + Pygame + NumPy + OpenGL\n\nTextures, sprites et sons\ngeneres de maniere procedurale.\n\nMerci d'avoir joue !",
        "press_any": "Appuie sur une touche",
        "paused": "PAUSE", "resume": "REPRENDRE", "save_now": "SAUVEGARDER", "to_menu": "MENU PRINCIPAL",
        "confirm_menu": "Quitter vers le menu ? (progression non sauvegardee perdue)",
        "you_died": "VOUS ETES MORT", "reload_last": "RECHARGER LA DERNIERE SAUVEGARDE",
        "end_title": "FIN DE LA BETA v0.1",
        "end_text": "Vous avez quitte le laboratoire Kurtos...\nmais le Sujet 09 court toujours.\n\nA suivre.",
        "inventory": "INVENTAIRE", "inv_empty": "Vos poches sont vides.",
        "inv_hint": "Fleches/ZQSD : choisir   E/Entree : utiliser   I/Echap : fermer", "use": "UTILISER",
        "kind_tool": "Outil", "kind_key": "Cle", "kind_use": "Consommable", "kind_doc": "Document",
        "hud_hp": "VIE", "hud_stamina": "ENDURANCE", "hud_battery": "LAMPE", "hud_bleeding": "SAIGNEMENT !",
        "hud_noise": "BRUIT",
        "level_n": "NIVEAU {0} - {1}",
        "lvl1_name": "L'INFIRMERIE", "lvl2_name": "LE LABORATOIRE", "lvl3_name": "LE REACTEUR",
        "p_take": "Ramasser : {0}", "p_close": "Fermer", "p_open": "Ouvrir",
        "p_planks": "Arracher les planches (bruyant)", "p_planks_no": "Des planches bloquent la porte",
        "p_chain": "Couper la chaine", "p_chain_no": "Une chaine ferme la porte",
        "p_unlock": "Deverrouiller (cle {0})", "p_locked": "Verrouille - cle {0} requise",
        "p_force": "Forcer la porte (tres bruyant)", "p_jammed": "Porte coincee",
        "p_nopower": "Pas de courant", "p_cont_planks": "{0} cloue de planches",
        "p_cont_padlock": "{0} ferme par un cadenas", "p_search": "Fouiller ({0})",
        "p_padlock": "Couper le cadenas", "p_cable": "Couper les cables", "p_cable_no": "Des cables bloquent le passage",
        "p_gen_on": "Le generateur tourne", "p_gen_fuse": "Inserer le fusible", "p_gen_no": "Generateur : fusible manquant",
        "m_need_crowbar": "Il faut un pied de biche.", "m_need_cutters": "Il faut une pince coupante.",
        "m_need_key": "Il faut la cle {0}.", "m_nopower": "La porte n'est pas alimentee en courant.",
        "m_exit_locked": "Cette porte est verrouillee.", "m_gen_no": "Il manque un fusible pour le generateur.",
        "m_blocked": "Quelque chose bloque la porte.", "m_unlocked": "Deverrouille.",
        "m_forced": "La porte cede dans un grand fracas !", "m_planks_off": "Les planches craquent... tout le monde a du l'entendre.",
        "m_chain_cut": "La chaine tombe.", "m_cable_cut": "Les cables sont coupes.",
        "inv_full": "Inventaire plein !", "found": "Trouve : {0}", "empty": "C'est vide.",
        "picked": "Ramasse : {0}",
        "m_gen_started": "Le generateur demarre ! Le bruit va attirer des creatures...",
        "m_no_battery": "Plus de batterie.", "m_no_spare": "Pas de batterie de rechange.",
        "m_batt_full": "La lampe est deja bien chargee.", "m_batt_ok": "Batterie remplacee.",
        "m_bandage": "Bandage applique.", "m_not_needed": "Pas necessaire.", "m_medkit": "Trousse de soin utilisee.",
        "m_pills": "Vous vous sentez mieux.", "m_auto_use": "Cet objet s'utilise tout seul.",
        "m_batt_dead": "La lampe s'eteint...", "m_batt_low": "La batterie faiblit !",
        "m_autosaved": "Sauvegarde automatique.", "m_saved": "Partie sauvegardee.",
        "cont_chest": "coffre", "cont_locker": "casier", "cont_cabinet": "armoire",
        "color_red": "rouge", "color_blue": "bleue", "color_yellow": "jaune", "color_green": "verte",
        "item_crowbar": "Pied de biche", "itemd_crowbar": "Un solide levier en acier. Ouvre les portes coincees et arrache les planches, mais fait un bruit d'enfer. Peut aussi servir d'arme (Espace).",
        "item_bolt_cutters": "Pince coupante", "itemd_bolt_cutters": "Coupe les chaines, les cadenas et les cables. Discrete.",
        "item_fuse": "Fusible", "itemd_fuse": "Un gros fusible industriel. Il doit aller dans un generateur.",
        "item_key_red": "Cle rouge", "itemd_key_red": "Ouvre les portes rouges.",
        "item_key_blue": "Cle bleue", "itemd_key_blue": "Ouvre les portes bleues.",
        "item_key_yellow": "Cle jaune", "itemd_key_yellow": "Ouvre les portes jaunes.",
        "item_key_green": "Cle verte", "itemd_key_green": "Ouvre les portes vertes.",
        "item_bandage": "Bandage", "itemd_bandage": "Arrete les saignements et rend un peu de vie.",
        "item_medkit": "Trousse de soin", "itemd_medkit": "Rend beaucoup de vie et arrete les saignements.",
        "item_pills": "Medicaments", "itemd_pills": "Redonnent toute l'endurance et un peu de vie.",
        "item_battery": "Batterie", "itemd_battery": "Recharge la lampe torche de 50%. Touche R pour l'utiliser directement.",
        "item_note1": "Note : le reveil", "itemd_note1": "\"Si vous lisez ceci, vous etes l'un des rares sujets stables. Ne faites pas de bruit. Ils entendent TOUT. Le pied de biche est dans la reserve, a l'ouest. - Dr Kurtos\"",
        "item_note2": "Journal du dortoir", "itemd_note2": "\"Jour 12. Ceux qui ont ete mordus ne dorment plus. Ils ne mangent plus. Ils attendent derriere les portes. Nous avons barricade le dortoir avec des planches.\"",
        "item_note3": "Rapport d'archives", "itemd_note3": "\"PROJET KURTOS. Agent K-9 : il reanime les tissus morts. Trois formes observees : le Rodeur, le Coureur et le Rampant. Le Sujet 09 est introuvable.\"",
        "item_note4": "Message laisse au sol", "itemd_note4": "\"Les portes de couleur ont chacune leur cle. La bleue est dans le laboratoire nord, derriere les cables... et un coffre cloue.\"",
        "item_note5": "Notes d'experience", "itemd_note5": "\"Les creatures reagissent au bruit, bien plus qu'a la lumiere. Marcher accroupi les trompe. Courir les appelle.\"",
        "item_note6": "Salle des serveurs", "itemd_note6": "\"Cle jaune rangee dans le casier du fond. La sortie du niveau est juste derriere la porte jaune.\"",
        "item_note7": "Message de l'equipe de securite", "itemd_note7": "\"Le generateur de secours est dans la salle sud. Il lui manque un fusible : il est dans le reacteur, sous des planches. Quand le courant reviendra, la porte de sortie s'ouvrira... et tout le laboratoire l'entendra.\"",
        "item_note8": "Derniere note du Dr Kurtos", "itemd_note8": "\"J'ai cree le Sujet 09 pour sauver ma fille. J'ai tout detruit. Courez. Ne vous retournez pas.\"",
    },
    "en": {
        "menu_continue": "CONTINUE", "menu_new": "NEW GAME", "menu_saves": "MY SAVES",
        "menu_options": "SETTINGS", "menu_language": "LANGUAGE", "menu_credits": "CREDITS",
        "menu_quit": "QUIT", "back": "BACK",
        "saves_title": "MY SAVES", "saves_new": "+ NEW GAME",
        "save_line": "{0}  -  Lvl.{1}  -  {2}", "save_line_info": "Level {0}  -  Play time {1}  -  {2}",
        "save_load": "LOAD", "save_rename": "RENAME", "save_delete": "DELETE",
        "confirm_delete": "Delete save \"{0}\"?", "enter_name": "Save name",
        "default_save": "Save {0}", "input_hint": "Enter: confirm    Esc: cancel",
        "yes": "YES", "no": "NO", "on": "ON", "off": "OFF",
        "opt_title": "SETTINGS", "opt_sens": "Mouse sensitivity", "opt_invert": "Invert Y axis",
        "opt_headbob": "Head bobbing", "opt_fov": "Field of view", "opt_master": "Master volume",
        "opt_music": "Music volume", "opt_sfx": "Effects volume", "opt_quality": "Internal resolution",
        "opt_fps": "Frames per second", "opt_controls": "KEY BINDINGS...", "opt_reset_keys": "RESET KEY BINDINGS",
        "act_forward": "Move forward", "act_back": "Move back", "act_left": "Move left", "act_right": "Move right",
        "act_interact": "Interact", "act_run": "Run", "act_crouch": "Crouch",
        "act_flashlight": "Flashlight", "act_battery": "Change battery", "act_inventory": "Inventory",
        "act_action": "Strike / shove",
        "credits_text": "KURTOS LAB - Beta v0.1\nHorror survival game\nPython + Pygame + NumPy + OpenGL\n\nTextures, sprites and sounds\nare procedurally generated.\n\nThanks for playing!",
        "press_any": "Press any key",
        "paused": "PAUSED", "resume": "RESUME", "save_now": "SAVE GAME", "to_menu": "MAIN MENU",
        "confirm_menu": "Back to menu? (unsaved progress will be lost)",
        "you_died": "YOU DIED", "reload_last": "RELOAD LAST SAVE",
        "end_title": "END OF BETA v0.1",
        "end_text": "You left the Kurtos laboratory...\nbut Subject 09 is still out there.\n\nTo be continued.",
        "inventory": "INVENTORY", "inv_empty": "Your pockets are empty.",
        "inv_hint": "Arrows/WASD: select   E/Enter: use   I/Esc: close", "use": "USE",
        "kind_tool": "Tool", "kind_key": "Key", "kind_use": "Consumable", "kind_doc": "Document",
        "hud_hp": "HEALTH", "hud_stamina": "STAMINA", "hud_battery": "LIGHT", "hud_bleeding": "BLEEDING!",
        "hud_noise": "NOISE",
        "level_n": "LEVEL {0} - {1}",
        "lvl1_name": "THE INFIRMARY", "lvl2_name": "THE LABORATORY", "lvl3_name": "THE REACTOR",
        "p_take": "Pick up: {0}", "p_close": "Close", "p_open": "Open",
        "p_planks": "Tear off the planks (loud)", "p_planks_no": "Planks block the door",
        "p_chain": "Cut the chain", "p_chain_no": "A chain locks the door",
        "p_unlock": "Unlock ({0} key)", "p_locked": "Locked - {0} key required",
        "p_force": "Force the door (very loud)", "p_jammed": "The door is jammed",
        "p_nopower": "No power", "p_cont_planks": "{0} nailed shut",
        "p_cont_padlock": "{0} padlocked", "p_search": "Search ({0})",
        "p_padlock": "Cut the padlock", "p_cable": "Cut the cables", "p_cable_no": "Cables block the way",
        "p_gen_on": "The generator is running", "p_gen_fuse": "Insert the fuse", "p_gen_no": "Generator: missing fuse",
        "m_need_crowbar": "You need a crowbar.", "m_need_cutters": "You need bolt cutters.",
        "m_need_key": "You need the {0} key.", "m_nopower": "The door has no power.",
        "m_exit_locked": "This door is locked.", "m_gen_no": "The generator needs a fuse.",
        "m_blocked": "Something is blocking the door.", "m_unlocked": "Unlocked.",
        "m_forced": "The door gives way with a crash!", "m_planks_off": "The planks crack... everyone must have heard.",
        "m_chain_cut": "The chain falls.", "m_cable_cut": "The cables are cut.",
        "inv_full": "Inventory full!", "found": "Found: {0}", "empty": "It's empty.",
        "picked": "Picked up: {0}",
        "m_gen_started": "The generator starts! The noise will attract creatures...",
        "m_no_battery": "No battery left.", "m_no_spare": "No spare battery.",
        "m_batt_full": "The flashlight is already well charged.", "m_batt_ok": "Battery replaced.",
        "m_bandage": "Bandage applied.", "m_not_needed": "Not needed.", "m_medkit": "Medkit used.",
        "m_pills": "You feel better.", "m_auto_use": "This item is used automatically.",
        "m_batt_dead": "The flashlight dies...", "m_batt_low": "The battery is running low!",
        "m_autosaved": "Autosaved.", "m_saved": "Game saved.",
        "cont_chest": "chest", "cont_locker": "locker", "cont_cabinet": "cabinet",
        "color_red": "red", "color_blue": "blue", "color_yellow": "yellow", "color_green": "green",
        "item_crowbar": "Crowbar", "itemd_crowbar": "A sturdy steel lever. Opens jammed doors and tears off planks, but makes a hell of a noise. Can also be used as a weapon (Space).",
        "item_bolt_cutters": "Bolt cutters", "itemd_bolt_cutters": "Cuts chains, padlocks and cables. Quiet.",
        "item_fuse": "Fuse", "itemd_fuse": "A big industrial fuse. It belongs in a generator.",
        "item_key_red": "Red key", "itemd_key_red": "Opens red doors.",
        "item_key_blue": "Blue key", "itemd_key_blue": "Opens blue doors.",
        "item_key_yellow": "Yellow key", "itemd_key_yellow": "Opens yellow doors.",
        "item_key_green": "Green key", "itemd_key_green": "Opens green doors.",
        "item_bandage": "Bandage", "itemd_bandage": "Stops bleeding and restores a little health.",
        "item_medkit": "Medkit", "itemd_medkit": "Restores a lot of health and stops bleeding.",
        "item_pills": "Pills", "itemd_pills": "Restore all stamina and a little health.",
        "item_battery": "Battery", "itemd_battery": "Recharges the flashlight by 50%. Press R to use it directly.",
        "item_note1": "Note: waking up", "itemd_note1": "\"If you are reading this, you are one of the few stable subjects. Make no noise. They hear EVERYTHING. The crowbar is in the storage room, to the west. - Dr Kurtos\"",
        "item_note2": "Dormitory journal", "itemd_note2": "\"Day 12. The bitten ones no longer sleep. They no longer eat. They wait behind the doors. We barricaded the dormitory with planks.\"",
        "item_note3": "Archive report", "itemd_note3": "\"PROJECT KURTOS. Agent K-9 reanimates dead tissue. Three forms observed: the Prowler, the Runner and the Crawler. Subject 09 cannot be found.\"",
        "item_note4": "Message left on the floor", "itemd_note4": "\"Each coloured door has its own key. The blue one is in the north lab, behind the cables... and a nailed chest.\"",
        "item_note5": "Experiment notes", "itemd_note5": "\"The creatures react to noise far more than to light. Walking crouched fools them. Running calls them.\"",
        "item_note6": "Server room", "itemd_note6": "\"Yellow key is in the locker at the back. The level exit is right behind the yellow door.\"",
        "item_note7": "Security team message", "itemd_note7": "\"The backup generator is in the south room. It lacks a fuse: it is in the reactor, under planks. When the power returns, the exit door will open... and the whole lab will hear it.\"",
        "item_note8": "Dr Kurtos' last note", "itemd_note8": "\"I created Subject 09 to save my daughter. I destroyed everything. Run. Do not look back.\"",
    },
}


if __name__ == "__main__":
    main()
