# -*- coding: utf-8 -*-
"""
Fenêtre du score de similarité.

Calcule et présente plusieurs métriques de ressemblance entre A et B :
  • SSIM   : indice de similarité structurelle (le standard, en %).
  • PSNR   : rapport signal/bruit (qualité, en dB ; plus haut = plus proche).
  • RMSE   : erreur quadratique moyenne (sur 255 ; plus bas = plus proche).
  • Histogramme : corrélation des distributions de couleurs (en %).

Un score global (basé sur le SSIM) est affiché avec une jauge colorée,
accompagné d'une carte de similarité structurelle.
"""

import math
import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageTk
from skimage.metrics import structural_similarity

from theme import C, FONT, FONT_LABEL, FONT_INFO, FONT_HELP, hex_to_rgb

MAX_DIM = 1400  # borne la résolution de calcul (vitesse)


def score_color(s):
    """Couleur interpolée rouge → orange → vert pour un score 0..100."""
    s = max(0.0, min(100.0, s))
    if s <= 50:
        t, c0, c1 = s / 50, hex_to_rgb(C.RED), hex_to_rgb(C.ORANGE)
    else:
        t, c0, c1 = (s - 50) / 50, hex_to_rgb(C.ORANGE), hex_to_rgb(C.GREEN)
    r, g, b = (int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def verdict(s):
    if s >= 90:
        return "Images quasi identiques"
    if s >= 75:
        return "Images très similaires"
    if s >= 50:
        return "Images moyennement similaires"
    if s >= 25:
        return "Images assez différentes"
    return "Images très différentes"


class SimilarityWindow(tk.Toplevel):
    def __init__(self, master, cv_a, cv_b, name_a="A", name_b="B"):
        super().__init__(master, bg=C.BG)
        self.title("Score de similarité")
        self.geometry("780x840")
        self.minsize(620, 720)
        self.configure(bg=C.BG)
        self._thumb = None

        metrics = self._compute(cv_a, cv_b)
        self._build_ui(metrics)
        self.bind("<Escape>", lambda e: self.destroy())

    # =====================================================================
    #  Calcul des métriques
    # =====================================================================
    def _compute(self, cv_a, cv_b):
        h, w = cv_a.shape[:2]
        scale = min(1.0, MAX_DIM / max(h, w))
        nw, nh = max(int(w * scale), 1), max(int(h * scale), 1)
        a = cv2.resize(cv_a, (nw, nh), interpolation=cv2.INTER_AREA)
        b = cv2.resize(cv_b, (nw, nh), interpolation=cv2.INTER_AREA)

        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

        # SSIM (+ carte complète)
        ssim, ssim_map = structural_similarity(ga, gb, data_range=255, full=True)
        ssim_pct = max(0.0, ssim) * 100

        # MSE / RMSE / PSNR
        diff = a.astype(np.float64) - b.astype(np.float64)
        mse = float(np.mean(diff ** 2))
        rmse = math.sqrt(mse)
        psnr = math.inf if mse == 0 else 10 * math.log10(255 ** 2 / mse)

        # Corrélation d'histogrammes (moyenne sur les 3 canaux)
        corr = []
        for ch in range(3):
            ha = cv2.calcHist([a], [ch], None, [256], [0, 256])
            hb = cv2.calcHist([b], [ch], None, [256], [0, 256])
            cv2.normalize(ha, ha)
            cv2.normalize(hb, hb)
            corr.append(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
        hist_pct = max(0.0, float(np.mean(corr))) * 100

        # Carte de similarité structurelle (les écarts ressortent en chaud)
        inv = ((1.0 - np.clip(ssim_map, 0, 1)) * 255).astype(np.uint8)
        heat = cv2.applyColorMap(inv, cv2.COLORMAP_JET)
        ssim_img = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)

        return {
            "score": ssim_pct, "ssim": ssim_pct, "psnr": psnr,
            "rmse": rmse, "hist": hist_pct, "ssim_img": ssim_img,
            "size": (w, h),
        }

    # =====================================================================
    #  Interface
    # =====================================================================
    def _build_ui(self, m):
        top = tk.Frame(self, bg=C.PANEL)
        top.pack(fill="x")
        tk.Label(top, text="📊  Score de similarité", bg=C.PANEL, fg=C.FG,
                 font=FONT_LABEL).pack(side="left", padx=16, pady=10)
        tk.Frame(self, bg=C.GREEN, height=2).pack(fill="x")

        score = m["score"]
        col = score_color(score)

        # --- Section héros : score + jauge -------------------------------
        hero = tk.Frame(self, bg=C.PANEL)
        hero.pack(fill="x", padx=16, pady=14)
        tk.Label(hero, text="SCORE GLOBAL (SSIM)", bg=C.PANEL, fg=C.FG_DIM,
                 font=(FONT, 10, "bold")).pack(pady=(14, 2))
        tk.Label(hero, text=f"{score:.1f} %", bg=C.PANEL, fg=col,
                 font=(FONT, 52, "bold")).pack()
        tk.Label(hero, text=verdict(score), bg=C.PANEL, fg=C.FG,
                 font=(FONT, 13)).pack(pady=(0, 10))
        Gauge(hero, score).pack(fill="x", padx=40, pady=(0, 18))

        # --- Grille de métriques -----------------------------------------
        grid = tk.Frame(self, bg=C.BG)
        grid.pack(fill="x", padx=12, pady=(0, 6))
        for i in range(2):
            grid.columnconfigure(i, weight=1, uniform="m")

        psnr_txt = "∞ dB" if math.isinf(m["psnr"]) else f"{m['psnr']:.1f} dB"
        cards = [
            ("Similarité structurelle", f"{m['ssim']:.1f} %",
             "SSIM — perception humaine", score_color(m["ssim"])),
            ("Qualité (PSNR)", psnr_txt,
             "Rapport signal/bruit", C.ACCENT),
            ("Erreur moyenne (RMSE)", f"{m['rmse']:.1f}",
             "écart de couleur sur 255", C.ACCENT2),
            ("Couleurs (histogramme)", f"{m['hist']:.1f} %",
             "corrélation des teintes", score_color(m["hist"])),
        ]
        for idx, (title, value, sub, accent) in enumerate(cards):
            self._card(grid, title, value, sub, accent).grid(
                row=idx // 2, column=idx % 2, sticky="nsew", padx=6, pady=6)

        # --- Carte de similarité structurelle ----------------------------
        mapf = tk.Frame(self, bg=C.PANEL)
        mapf.pack(fill="both", expand=True, padx=16, pady=(8, 8))
        tk.Label(mapf, text="Carte de similarité structurelle "
                 "(zones rouges = plus différentes)",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_INFO).pack(pady=(10, 6))
        pil = Image.fromarray(m["ssim_img"])
        pil.thumbnail((420, 280), Image.LANCZOS)
        self._thumb = ImageTk.PhotoImage(pil)
        tk.Label(mapf, image=self._thumb, bg=C.PANEL).pack(pady=(0, 12))

        foot = tk.Frame(self, bg=C.PANEL)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, text=f"Résolution comparée : {m['size'][0]} × "
                 f"{m['size'][1]} px   •   Échap = fermer",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_HELP,
                 anchor="w").pack(side="left", padx=14, pady=5)

    def _card(self, parent, title, value, sub, accent):
        f = tk.Frame(parent, bg=C.CARD, highlightthickness=1,
                     highlightbackground=C.BORDER)
        tk.Label(f, text=title, bg=C.CARD, fg=C.FG_DIM,
                 font=FONT_INFO).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(f, text=value, bg=C.CARD, fg=accent,
                 font=(FONT, 22, "bold")).pack(anchor="w", padx=14)
        tk.Label(f, text=sub, bg=C.CARD, fg=C.FG_DIM,
                 font=FONT_INFO).pack(anchor="w", padx=14, pady=(0, 12))
        return f


# =========================================================================
#  Jauge horizontale colorée
# =========================================================================
class Gauge(tk.Canvas):
    def __init__(self, master, score):
        super().__init__(master, height=26, bg=C.PANEL, highlightthickness=0)
        self.score = score
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        bh = 16
        y = (h - bh) // 2
        self._bar(2, y, w - 2, bh, C.CARD)                      # piste
        fill = 2 + (w - 4) * self.score / 100
        self._bar(2, y, max(fill, 2 + bh), bh, score_color(self.score))

    def _bar(self, x1, y, x2, bh, color):
        r = bh / 2
        if x2 - x1 < bh:
            x2 = x1 + bh
        self.create_oval(x1, y, x1 + bh, y + bh, fill=color, outline="")
        self.create_oval(x2 - bh, y, x2, y + bh, fill=color, outline="")
        self.create_rectangle(x1 + r, y, x2 - r, y + bh, fill=color, outline="")
