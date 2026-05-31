# -*- coding: utf-8 -*-
"""
Fenêtre de comparaison interactive.

Deux modes :
  • Avant / Après  : un curseur révèle l'image A par-dessus l'image B.
  • Côte à côte     : les deux images alignées à la même échelle.

Zoom à la molette (centré sur le curseur) et déplacement (pan) au clic droit
sont synchronisés sur les deux images.
"""

import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageTk

from theme import (C, FONT_LABEL, FONT_INFO, FONT_HELP,
                   HoverButton, hex_to_rgb, fit_size)


class CompareWindow(tk.Toplevel):
    MAX_BASE_W = 1100
    MAX_BASE_H = 720
    ZOOM_MIN = 0.2
    ZOOM_MAX = 6.0
    GAP = 12  # espace entre les images en mode côte à côte

    def __init__(self, master, cv_a, cv_b, name_a="A", name_b="B"):
        super().__init__(master, bg=C.BG)
        self.title("Comparaison côte à côte")
        self.geometry("1180x880")
        self.minsize(720, 540)
        self.configure(bg=C.BG)

        self.name_a, self.name_b = name_a, name_b
        self.mode = "split"          # "split" (avant/après) ou "sxs" (côte à côte)
        self.zoom = 1.0
        self.split = 0.5             # position du curseur, fraction [0, 1]
        self.off_x = 0
        self.off_y = 0
        self._pan_last = None
        self._centered = False

        # --- Préparer les deux images à une même base (taille commune) ----
        rgb_a = cv2.cvtColor(cv_a, cv2.COLOR_BGR2RGB)
        rgb_b = cv2.cvtColor(cv_b, cv2.COLOR_BGR2RGB)
        ha, wa = rgb_a.shape[:2]
        hb, wb = rgb_b.shape[:2]
        self.base_w, self.base_h = fit_size(wa, ha, self.MAX_BASE_W, self.MAX_BASE_H)
        self.baseA = Image.fromarray(rgb_a).resize((self.base_w, self.base_h), Image.LANCZOS)
        self.baseB = Image.fromarray(rgb_b).resize((self.base_w, self.base_h), Image.LANCZOS)
        self.diff_size = (wa, ha) != (wb, hb)
        self._sep = hex_to_rgb(C.BORDER)

        self._build_ui()
        self._zoom_images()
        self._set_mode("split")

    # =====================================================================
    #  Construction de l'interface
    # =====================================================================
    def _build_ui(self):
        top = tk.Frame(self, bg=C.PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🖼️  Comparaison", bg=C.PANEL, fg=C.FG,
                 font=FONT_LABEL).pack(side="left", padx=16, pady=10)

        self.btn_split = HoverButton(top, bg=C.TEAL, text="◑  Avant / Après",
                                     command=lambda: self._set_mode("split"))
        self.btn_split.pack(side="left", padx=(0, 6), pady=8)
        self.btn_sxs = HoverButton(top, bg=C.CARD, fg=C.FG, hover=C.ELEV,
                                   text="▥  Côte à côte",
                                   command=lambda: self._set_mode("sxs"))
        self.btn_sxs.pack(side="left", pady=8)

        HoverButton(top, bg=C.CARD, fg=C.FG, hover=C.ELEV,
                    text="⟲  Réinitialiser la vue",
                    command=self._reset_view).pack(side="right", padx=10, pady=8)
        self.zoom_lbl = tk.Label(top, text="Zoom 100 %", bg=C.PANEL, fg=C.FG_DIM,
                                 font=FONT_INFO)
        self.zoom_lbl.pack(side="right", padx=6)

        tk.Frame(self, bg=C.TEAL, height=2).pack(fill="x")

        # Canvas + items (image puis surcouches)
        self.canvas = tk.Canvas(self, bg=C.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.img_item = self.canvas.create_image(0, 0, anchor="nw")
        self.line_item = self.canvas.create_line(0, 0, 0, 0, fill="#ffffff", width=2)
        self.handle_item = self.canvas.create_oval(0, 0, 0, 0, fill=C.TEAL,
                                                   outline="#ffffff", width=2)
        self.lblA_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill=C.TEAL, outline="")
        self.lblA = self.canvas.create_text(0, 0, text=" A ", fill=C.BG, font=FONT_LABEL)
        self.lblB_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill=C.ACCENT2, outline="")
        self.lblB = self.canvas.create_text(0, 0, text=" B ", fill=C.BG, font=FONT_LABEL)

        # Pied de page : aide
        foot = tk.Frame(self, bg=C.PANEL)
        foot.pack(fill="x", side="bottom")
        msg = ("Glissez pour déplacer la séparation   •   Molette = zoom   •   "
               "Clic droit = déplacer   •   Double-clic = réinitialiser   •   Échap = fermer")
        if self.diff_size:
            msg = "⚠ Tailles différentes : l'image B est redimensionnée.    " + msg
        tk.Label(foot, text=msg, bg=C.PANEL, fg=C.FG_DIM, font=FONT_HELP,
                 anchor="w").pack(side="left", padx=14, pady=5)

        # Événements souris / clavier
        self.canvas.bind("<Button-1>", self._on_left)
        self.canvas.bind("<B1-Motion>", self._on_left)
        self.canvas.bind("<Double-Button-1>", lambda e: self._reset_view())
        self.canvas.bind("<Button-3>", self._on_pan_start)
        self.canvas.bind("<B3-Motion>", self._on_pan_move)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_configure)
        self.bind("<Escape>", lambda e: self.destroy())

    # =====================================================================
    #  Rendu
    # =====================================================================
    def _zoom_images(self):
        """Recrée les deux images à l'échelle de zoom courante."""
        zw = max(int(self.base_w * self.zoom), 1)
        zh = max(int(self.base_h * self.zoom), 1)
        resample = Image.LANCZOS if self.zoom < 1 else Image.BILINEAR
        self.zw, self.zh = zw, zh
        self.arrZA = np.asarray(self.baseA.resize((zw, zh), resample))
        self.arrZB = np.asarray(self.baseB.resize((zw, zh), resample))
        self.zoom_lbl.config(text=f"Zoom {int(round(self.zoom * 100))} %")
        self._render()

    def _render(self):
        if self.mode == "split":
            sx = max(0, min(self.zw, int(self.split * self.zw)))
            comp = np.concatenate([self.arrZA[:, :sx], self.arrZB[:, sx:]], axis=1)
        else:
            sep = np.full((self.zh, self.GAP, 3), self._sep, dtype=np.uint8)
            comp = np.concatenate([self.arrZA, sep, self.arrZB], axis=1)

        self.photo = ImageTk.PhotoImage(Image.fromarray(np.ascontiguousarray(comp)))
        self.canvas.itemconfig(self.img_item, image=self.photo)
        self.canvas.coords(self.img_item, self.off_x, self.off_y)
        self._update_overlays()

    def _update_overlays(self):
        c = self.canvas
        if self.mode == "split":
            sx = int(self.split * self.zw)
            x = self.off_x + sx
            y0, y1 = self.off_y, self.off_y + self.zh
            c.coords(self.line_item, x, y0, x, y1)
            r, cy = 9, (y0 + y1) / 2
            c.coords(self.handle_item, x - r, cy - r, x + r, cy + r)
            self._place_label(self.lblA_bg, self.lblA,
                              self.off_x + 12, self.off_y + 12, "nw")
            self._place_label(self.lblB_bg, self.lblB,
                              self.off_x + self.zw - 12, self.off_y + 12, "ne")
            for it in (self.line_item, self.handle_item):
                c.itemconfig(it, state="normal")
        else:
            for it in (self.line_item, self.handle_item):
                c.itemconfig(it, state="hidden")
            self._place_label(self.lblA_bg, self.lblA,
                              self.off_x + 12, self.off_y + 12, "nw")
            self._place_label(self.lblB_bg, self.lblB,
                              self.off_x + self.zw + self.GAP + 12, self.off_y + 12, "nw")

        for it in (self.lblA_bg, self.lblA, self.lblB_bg, self.lblB):
            c.itemconfig(it, state="normal")
        for it in (self.line_item, self.handle_item, self.lblA_bg, self.lblA,
                   self.lblB_bg, self.lblB):
            c.tag_raise(it)

    def _place_label(self, bg, txt, x, y, anchor):
        c = self.canvas
        c.itemconfig(txt, anchor=anchor)
        c.coords(txt, x, y)
        bb = c.bbox(txt)
        if bb:
            c.coords(bg, bb[0] - 5, bb[1] - 3, bb[2] + 5, bb[3] + 3)

    # =====================================================================
    #  Interactions
    # =====================================================================
    def _on_left(self, e):
        if self.mode == "split" and self.zw > 0:
            self.split = max(0.0, min(1.0, (e.x - self.off_x) / self.zw))
            self._render()

    def _on_pan_start(self, e):
        self._pan_last = (e.x, e.y)

    def _on_pan_move(self, e):
        if self._pan_last is None:
            return
        self.off_x += e.x - self._pan_last[0]
        self.off_y += e.y - self._pan_last[1]
        self._pan_last = (e.x, e.y)
        self._render()

    def _on_wheel(self, e):
        factor = 1.1 if e.delta > 0 else 1 / 1.1
        new = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom * factor))
        if abs(new - self.zoom) < 1e-6:
            return
        # Conserver le point de l'image situé sous le curseur
        bx = (e.x - self.off_x) / self.zoom
        by = (e.y - self.off_y) / self.zoom
        self.zoom = new
        self.off_x = e.x - bx * self.zoom
        self.off_y = e.y - by * self.zoom
        self._zoom_images()

    def _on_configure(self, e):
        if not self._centered and e.width > 1:
            self._centered = True
            self._center()
            self._render()

    # =====================================================================
    #  Modes / vue
    # =====================================================================
    def _set_mode(self, m):
        self.mode = m
        for btn, active in ((self.btn_split, m == "split"),
                            (self.btn_sxs, m == "sxs")):
            btn._bg = C.TEAL if active else C.CARD
            btn.config(bg=btn._bg, fg=C.BG if active else C.FG)
        self._center()
        self._render()

    def _center(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1:
            return
        total_w = self.zw * 2 + self.GAP if self.mode == "sxs" else self.zw
        self.off_x = (cw - total_w) // 2
        self.off_y = (ch - self.zh) // 2

    def _reset_view(self):
        self.zoom = 1.0
        self.split = 0.5
        self._zoom_images()
        self._center()
        self._render()
