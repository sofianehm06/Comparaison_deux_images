# -*- coding: utf-8 -*-
"""
Composants réutilisables.

ZoomPanCanvas : affiche une image (numpy RGB ou PIL) avec zoom à la molette
(centré sur le curseur), déplacement au clic droit, double-clic pour
réinitialiser. La vue est préservée lorsqu'on remplace l'image par une autre
de même taille (utile pour les mises à jour interactives).
"""

import tkinter as tk

import numpy as np
from PIL import Image, ImageTk

from theme import C, fit_size


class ZoomPanCanvas(tk.Frame):
    ZOOM_MIN = 0.2
    ZOOM_MAX = 6.0

    def __init__(self, master, max_w=1100, max_h=700, zoom_cb=None):
        super().__init__(master, bg=C.BG)
        self.max_w, self.max_h = max_w, max_h
        self.zoom_cb = zoom_cb
        self.base = None
        self.base_w = self.base_h = 0
        self.zoom = 1.0
        self.off_x = self.off_y = 0
        self._pan_last = None
        self._centered = False
        self.photo = None

        self.canvas = tk.Canvas(self, bg=C.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.img_item = self.canvas.create_image(0, 0, anchor="nw")

        self.canvas.bind("<Button-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Double-Button-1>", lambda e: self.reset_view())
        self.canvas.bind("<Configure>", self._configure)

    # ---- API ------------------------------------------------------------
    def set_image(self, img):
        """Affiche une image. La vue est recentrée seulement si la taille change."""
        if isinstance(img, np.ndarray):
            img = Image.fromarray(img)
        bw, bh = fit_size(img.width, img.height, self.max_w, self.max_h)
        size_changed = (bw, bh) != (self.base_w, self.base_h)
        self.base = img.resize((bw, bh), Image.LANCZOS)
        self.base_w, self.base_h = bw, bh
        self._zoom_image()
        if size_changed:
            self._center()
            self._render()

    def reset_view(self):
        self.zoom = 1.0
        self._zoom_image()
        self._center()
        self._render()

    # ---- Rendu ----------------------------------------------------------
    def _zoom_image(self):
        if self.base is None:
            return
        zw = max(int(self.base_w * self.zoom), 1)
        zh = max(int(self.base_h * self.zoom), 1)
        resample = Image.LANCZOS if self.zoom < 1 else Image.BILINEAR
        self.zw, self.zh = zw, zh
        self._disp = self.base.resize((zw, zh), resample)
        if self.zoom_cb:
            self.zoom_cb(int(round(self.zoom * 100)))
        self._render()

    def _render(self):
        if self.base is None:
            return
        self.photo = ImageTk.PhotoImage(self._disp)
        self.canvas.itemconfig(self.img_item, image=self.photo)
        self.canvas.coords(self.img_item, self.off_x, self.off_y)

    def _center(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or self.base is None:
            return
        self.off_x = (cw - self.zw) // 2
        self.off_y = (ch - self.zh) // 2

    # ---- Interactions ---------------------------------------------------
    def _wheel(self, e):
        factor = 1.1 if e.delta > 0 else 1 / 1.1
        new = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom * factor))
        if abs(new - self.zoom) < 1e-6:
            return
        bx = (e.x - self.off_x) / self.zoom
        by = (e.y - self.off_y) / self.zoom
        self.zoom = new
        self.off_x = e.x - bx * self.zoom
        self.off_y = e.y - by * self.zoom
        self._zoom_image()

    def _pan_start(self, e):
        self._pan_last = (e.x, e.y)

    def _pan_move(self, e):
        if self._pan_last is None:
            return
        self.off_x += e.x - self._pan_last[0]
        self.off_y += e.y - self._pan_last[1]
        self._pan_last = (e.x, e.y)
        self._render()

    def _configure(self, e):
        if not self._centered and e.width > 1:
            self._centered = True
            self._center()
            self._render()
