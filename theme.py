# -*- coding: utf-8 -*-
"""
Thème, constantes et composants UI partagés par toute l'application.
"""

import os
import tkinter as tk

import cv2
import numpy as np
from PIL import Image

# --- Rendu net sur écrans Windows HiDPI -----------------------------------
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# =========================================================================
#  Palette de couleurs (thème sombre moderne — "Tokyo Night")
# =========================================================================
class C:
    BG      = "#1a1b26"   # fond de la fenêtre
    PANEL   = "#1f2335"   # panneaux
    CARD    = "#24283b"   # zones d'aperçu
    ELEV    = "#2a2e42"   # éléments survolés
    BORDER  = "#3b4261"   # bordures
    FG      = "#c0caf5"   # texte principal
    FG_DIM  = "#565f89"   # texte secondaire
    ACCENT  = "#7aa2f7"   # bleu
    ACCENT2 = "#bb9af7"   # violet
    TEAL    = "#2ac3de"   # cyan
    PINK    = "#ff75a0"   # rose
    GREEN   = "#9ece6a"
    ORANGE  = "#e0af68"
    RED     = "#f7768e"


FONT        = "Segoe UI"
FONT_TITLE  = (FONT, 20, "bold")
FONT_SUB    = (FONT, 10)
FONT_BTN    = (FONT, 10, "bold")
FONT_LABEL  = (FONT, 11, "bold")
FONT_INFO   = (FONT, 9)
FONT_STATUS = (FONT, 9)
FONT_HELP   = (FONT, 9)

IMG_EXT = [
    ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
    ("Tous les fichiers", "*.*"),
]


# =========================================================================
#  Helpers couleur / image
# =========================================================================
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def imread_unicode(path):
    """Lit une image même si le chemin contient des caractères accentués."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def imwrite_unicode(path, img):
    """Écrit une image même si le chemin contient des caractères accentués."""
    try:
        ext = os.path.splitext(path)[1] or ".png"
        ok, buf = cv2.imencode(ext, img)
        if ok:
            buf.tofile(path)
            return True
    except Exception:
        pass
    return False


def cv2_to_pil(bgr):
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def pil_to_cv2(pil):
    return cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)


def fit_size(w, h, max_w, max_h, allow_upscale=True):
    """Retourne (w, h) ajusté à la boîte (max_w, max_h) en gardant le ratio."""
    s = min(max_w / w, max_h / h)
    if not allow_upscale:
        s = min(s, 1.0)
    return max(int(round(w * s)), 1), max(int(round(h * s)), 1)


# =========================================================================
#  Bouton stylé avec effet de survol
# =========================================================================
class HoverButton(tk.Button):
    def __init__(self, master, bg, fg=C.BG, hover=None, **kw):
        self._bg = bg
        self._hover = hover or C.ELEV
        super().__init__(
            master,
            bg=bg, fg=fg,
            activebackground=self._hover, activeforeground=fg,
            relief="flat", bd=0, font=FONT_BTN,
            cursor="hand2", padx=16, pady=9,
            **kw,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._hover)

    def _on_leave(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._bg)
