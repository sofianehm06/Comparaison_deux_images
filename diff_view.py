# -*- coding: utf-8 -*-
"""
Fenêtre des différences visuelles.

Compare A et B pixel par pixel et propose quatre visualisations :
  • Surbrillance : les zones modifiées teintées en rouge sur l'image A.
  • Rectangles   : un cadre autour de chaque zone de différence détectée.
  • Masque       : les pixels différents en blanc sur fond noir.
  • Carte de chaleur : intensité des différences (bleu = faible, rouge = fort).

Un curseur de seuil ajuste la sensibilité en temps réel.
"""

import tkinter as tk

import cv2
import numpy as np

from theme import (C, FONT_LABEL, FONT_INFO, FONT_HELP,
                   HoverButton, hex_to_rgb, fit_size)
from widgets import ZoomPanCanvas

RED = hex_to_rgb(C.RED)
MIN_AREA = 20  # ignore les différences plus petites que ça (px²)


class DiffWindow(tk.Toplevel):
    MAX_W = 1100
    MAX_H = 680

    MODES = [
        ("overlay", "🔴  Surbrillance"),
        ("boxes",   "▢  Rectangles"),
        ("mask",    "◧  Masque"),
        ("heatmap", "🌡  Carte de chaleur"),
    ]

    def __init__(self, master, cv_a, cv_b, name_a="A", name_b="B"):
        super().__init__(master, bg=C.BG)
        self.title("Différences visuelles")
        self.geometry("1180x880")
        self.minsize(740, 560)
        self.configure(bg=C.BG)

        # Aligner les deux images à une base commune (taille de A ajustée)
        h, w = cv_a.shape[:2]
        bw, bh = fit_size(w, h, self.MAX_W, self.MAX_H)
        a = cv2.resize(cv_a, (bw, bh), interpolation=cv2.INTER_AREA)
        b = cv2.resize(cv_b, (bw, bh), interpolation=cv2.INTER_AREA)
        self.bw, self.bh = bw, bh
        self.a_rgb = cv2.cvtColor(a, cv2.COLOR_BGR2RGB)
        self.diff_gray = cv2.cvtColor(cv2.absdiff(a, b), cv2.COLOR_BGR2GRAY)

        # Carte de chaleur (indépendante du seuil) : JET + fond en niveaux de gris
        heat = cv2.applyColorMap(self.diff_gray, cv2.COLORMAP_JET)
        gray3 = cv2.cvtColor(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        self.heat_rgb = cv2.cvtColor(
            cv2.addWeighted(heat, 0.75, gray3, 0.25, 0), cv2.COLOR_BGR2RGB)

        self.mode = "overlay"
        self.thresh = 25
        self._mask = None
        self._boxes = []
        self._mode_btns = {}

        self._build_ui()
        self._recompute()
        self.bind("<Escape>", lambda e: self.destroy())

    # =====================================================================
    #  Interface
    # =====================================================================
    def _build_ui(self):
        top = tk.Frame(self, bg=C.PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🔬  Différences", bg=C.PANEL, fg=C.FG,
                 font=FONT_LABEL).pack(side="left", padx=16, pady=10)
        for key, label in self.MODES:
            b = HoverButton(top, bg=C.CARD, fg=C.FG, hover=C.ELEV, text=label,
                            command=lambda k=key: self._set_mode(k))
            b.pack(side="left", padx=(0, 6), pady=8)
            self._mode_btns[key] = b
        self.zoom_lbl = tk.Label(top, text="Zoom 100 %", bg=C.PANEL,
                                 fg=C.FG_DIM, font=FONT_INFO)
        self.zoom_lbl.pack(side="right", padx=12)
        tk.Frame(self, bg=C.ORANGE, height=2).pack(fill="x")

        # Barre de réglage : seuil + statistiques
        ctrl = tk.Frame(self, bg=C.BG)
        ctrl.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(ctrl, text="Seuil de différence", bg=C.BG, fg=C.FG_DIM,
                 font=FONT_INFO).pack(side="left")
        self.scale = tk.Scale(ctrl, from_=1, to=100, orient="horizontal",
                              length=220, showvalue=True, bg=C.BG, fg=C.FG,
                              troughcolor=C.CARD, highlightthickness=0, bd=0,
                              activebackground=C.ORANGE, sliderrelief="flat",
                              command=self._on_thresh)
        self.scale.set(self.thresh)
        self.scale.pack(side="left", padx=10)
        self.stats_lbl = tk.Label(ctrl, text="", bg=C.BG, fg=C.FG,
                                  font=FONT_INFO)
        self.stats_lbl.pack(side="right")

        self.viewer = ZoomPanCanvas(self, self.MAX_W, self.MAX_H,
                                    zoom_cb=lambda p: self.zoom_lbl.config(
                                        text=f"Zoom {p} %"))
        self.viewer.pack(fill="both", expand=True, padx=8, pady=8)

        foot = tk.Frame(self, bg=C.PANEL)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, text="Molette = zoom   •   Clic droit = déplacer   •   "
                 "Double-clic = réinitialiser   •   Échap = fermer",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_HELP,
                 anchor="w").pack(side="left", padx=14, pady=5)

    # =====================================================================
    #  Calculs
    # =====================================================================
    def _on_thresh(self, val):
        self.thresh = int(val)
        self._recompute()

    def _recompute(self):
        _, mask = cv2.threshold(self.diff_gray, self.thresh, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        self._mask = mask

        dil = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)
        cnts, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self._boxes = [cv2.boundingRect(c) for c in cnts
                       if cv2.contourArea(c) >= MIN_AREA]

        ratio = float(np.count_nonzero(mask)) / (self.bw * self.bh) * 100
        self.stats_lbl.config(
            text=f"🔴 {ratio:.2f} % différents     ▢ {len(self._boxes)} zone(s)")
        self._refresh()

    def _refresh(self):
        for key, b in self._mode_btns.items():
            active = key == self.mode
            b._bg = C.ORANGE if active else C.CARD
            b.config(bg=b._bg, fg=C.BG if active else C.FG)
        self.viewer.set_image(self._mode_image())

    def _set_mode(self, m):
        self.mode = m
        self._refresh()

    def _mode_image(self):
        if self.mode == "heatmap":
            return self.heat_rgb
        if self.mode == "mask":
            return cv2.cvtColor(self._mask, cv2.COLOR_GRAY2RGB)
        if self.mode == "overlay":
            out = self.a_rgb.copy()
            sel = self._mask > 0
            tint = np.array(RED, np.float32) * 0.6
            out[sel] = (out[sel].astype(np.float32) * 0.4 + tint).astype(np.uint8)
            return out
        # boxes
        out = self.a_rgb.copy()
        for x, y, w, h in self._boxes:
            cv2.rectangle(out, (x, y), (x + w, y + h), RED, 2)
        return out
