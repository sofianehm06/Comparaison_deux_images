# -*- coding: utf-8 -*-
"""
Fenêtre d'analyse pixel par pixel.

  • Inspecteur au survol : une loupe agrandit la zone sous le curseur et
    affiche les coordonnées (x, y) ainsi que la valeur RGB des deux images
    au même point, avec l'écart par canal.
  • Statistiques par canal (Rouge, Vert, Bleu) : écart moyen, écart maximum
    et pourcentage de pixels différents.
  • Histogrammes superposés : distribution des couleurs de A (zone remplie)
    et de B (ligne) pour chaque canal.
"""

import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageTk

from theme import C, FONT, FONT_LABEL, FONT_INFO, FONT_HELP, HoverButton, fit_size

CH = [("Rouge", C.RED), ("Vert", C.GREEN), ("Bleu", C.ACCENT)]
MAG_HALF = 7      # demi-fenêtre de la loupe (→ 15×15 px)
MAG_SIZE = 132    # taille d'affichage de la loupe


class PixelsWindow(tk.Toplevel):
    MAX_W = 820
    MAX_H = 720

    def __init__(self, master, cv_a, cv_b, name_a="A", name_b="B"):
        super().__init__(master, bg=C.BG)
        self.title("Analyse pixel par pixel")
        self.geometry("1200x860")
        self.minsize(900, 640)
        self.configure(bg=C.BG)

        # Aligner A et B à une base commune
        h, w = cv_a.shape[:2]
        bw, bh = fit_size(w, h, self.MAX_W, self.MAX_H)
        a = cv2.resize(cv_a, (bw, bh), interpolation=cv2.INTER_AREA)
        b = cv2.resize(cv_b, (bw, bh), interpolation=cv2.INTER_AREA)
        self.bw, self.bh = bw, bh
        self.arrA = cv2.cvtColor(a, cv2.COLOR_BGR2RGB)
        self.arrB = cv2.cvtColor(b, cv2.COLOR_BGR2RGB)

        self.show = "A"
        self._left_photo = None
        self._mag_photo = None
        self._scale = 1.0
        self._ox = self._oy = 0

        self._build_ui()
        self._compute_stats()
        self.bind("<Escape>", lambda e: self.destroy())

    # =====================================================================
    #  Interface
    # =====================================================================
    def _build_ui(self):
        top = tk.Frame(self, bg=C.PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🔢  Analyse pixel par pixel", bg=C.PANEL, fg=C.FG,
                 font=FONT_LABEL).pack(side="left", padx=16, pady=10)
        tk.Label(top, text="Image affichée :", bg=C.PANEL, fg=C.FG_DIM,
                 font=FONT_INFO).pack(side="left", padx=(10, 6))
        self.btn_a = HoverButton(top, bg=C.ACCENT, text="A",
                                 command=lambda: self._set_show("A"))
        self.btn_a.pack(side="left", padx=(0, 4), pady=8)
        self.btn_b = HoverButton(top, bg=C.CARD, fg=C.FG, hover=C.ELEV, text="B",
                                 command=lambda: self._set_show("B"))
        self.btn_b.pack(side="left", pady=8)
        tk.Frame(self, bg=C.ACCENT2, height=2).pack(fill="x")

        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # Image (gauche)
        self.canvas = tk.Canvas(body, bg=C.BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.img_item = self.canvas.create_image(0, 0, anchor="nw")
        self.cross_h = self.canvas.create_line(0, 0, 0, 0, fill=C.TEAL, state="hidden")
        self.cross_v = self.canvas.create_line(0, 0, 0, 0, fill=C.TEAL, state="hidden")
        self.canvas.bind("<Configure>", lambda e: self._render_left())
        self.canvas.bind("<Motion>", self._inspect)

        # Sidebar (droite)
        side = tk.Frame(body, bg=C.BG, width=340)
        side.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        side.grid_propagate(False)
        self._build_inspector(side)
        self._build_channel_stats(side)

        # Histogrammes (bas)
        self._build_histograms()

        foot = tk.Frame(self, bg=C.PANEL)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, text="Survolez l'image pour inspecter les pixels   •   "
                 "Échap = fermer", bg=C.PANEL, fg=C.FG_DIM, font=FONT_HELP,
                 anchor="w").pack(side="left", padx=14, pady=5)

    def _build_inspector(self, parent):
        box = tk.Frame(parent, bg=C.CARD, highlightthickness=1,
                       highlightbackground=C.BORDER)
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="INSPECTEUR", bg=C.CARD, fg=C.FG_DIM,
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        row = tk.Frame(box, bg=C.CARD)
        row.pack(fill="x", padx=12)
        self.mag = tk.Canvas(row, width=MAG_SIZE, height=MAG_SIZE, bg=C.BG,
                             highlightthickness=1, highlightbackground=C.BORDER)
        self.mag.pack(side="left")
        self.mag_img = self.mag.create_image(0, 0, anchor="nw")

        info = tk.Frame(row, bg=C.CARD)
        info.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.coord_lbl = tk.Label(info, text="(—, —)", bg=C.CARD, fg=C.FG,
                                  font=(FONT, 11, "bold"))
        self.coord_lbl.pack(anchor="w")
        self.swatchA, self.valA = self._swatch_row(info, "A")
        self.swatchB, self.valB = self._swatch_row(info, "B")
        self.delta_lbl = tk.Label(info, text="Δ —", bg=C.CARD, fg=C.ORANGE,
                                  font=FONT_INFO)
        self.delta_lbl.pack(anchor="w", pady=(4, 0))
        tk.Frame(box, bg=C.CARD, height=10).pack()

    def _swatch_row(self, parent, tag):
        row = tk.Frame(parent, bg=C.CARD)
        row.pack(anchor="w", pady=(6, 0))
        sw = tk.Frame(row, bg=C.BG, width=18, height=18,
                      highlightthickness=1, highlightbackground=C.BORDER)
        sw.pack(side="left")
        sw.pack_propagate(False)
        lbl = tk.Label(row, text=f"{tag}  —", bg=C.CARD, fg=C.FG,
                       font=FONT_INFO)
        lbl.pack(side="left", padx=8)
        return sw, lbl

    def _build_channel_stats(self, parent):
        box = tk.Frame(parent, bg=C.CARD, highlightthickness=1,
                       highlightbackground=C.BORDER)
        box.pack(fill="x")
        tk.Label(box, text="ÉCART PAR CANAL", bg=C.CARD, fg=C.FG_DIM,
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        hdr = tk.Frame(box, bg=C.CARD)
        hdr.pack(fill="x", padx=12)
        for txt, wdt in (("Canal", 8), ("Moyen", 7), ("Max", 6), ("% diff", 7)):
            tk.Label(hdr, text=txt, bg=C.CARD, fg=C.FG_DIM, font=FONT_INFO,
                     width=wdt, anchor="w").pack(side="left")
        self.stat_rows = []
        for name, color in CH:
            r = tk.Frame(box, bg=C.CARD)
            r.pack(fill="x", padx=12, pady=1)
            tk.Label(r, text=name, bg=C.CARD, fg=color, font=FONT_INFO,
                     width=8, anchor="w").pack(side="left")
            cells = []
            for wdt in (7, 6, 7):
                l = tk.Label(r, text="—", bg=C.CARD, fg=C.FG, font=FONT_INFO,
                             width=wdt, anchor="w")
                l.pack(side="left")
                cells.append(l)
            self.stat_rows.append(cells)
        tk.Frame(box, bg=C.CARD, height=10).pack()

    def _build_histograms(self):
        wrap = tk.Frame(self, bg=C.PANEL)
        wrap.pack(fill="x", side="bottom")
        head = tk.Frame(wrap, bg=C.PANEL)
        head.pack(fill="x")
        tk.Label(head, text="Histogrammes — A (zone remplie) vs B (ligne)",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_INFO).pack(side="left",
                                                              padx=14, pady=(8, 2))
        plots = tk.Frame(wrap, bg=C.PANEL)
        plots.pack(fill="x", padx=10, pady=(0, 10))
        for i, (name, color) in enumerate(CH):
            plots.columnconfigure(i, weight=1, uniform="h")
            ha = np.histogram(self.arrA[:, :, i], bins=256, range=(0, 256))[0]
            hb = np.histogram(self.arrB[:, :, i], bins=256, range=(0, 256))[0]
            HistPlot(plots, name, ha, hb, color, height=150).grid(
                row=0, column=i, sticky="nsew", padx=4)

    # =====================================================================
    #  Affichage / interactions
    # =====================================================================
    def _set_show(self, which):
        self.show = which
        self.btn_a._bg = C.ACCENT if which == "A" else C.CARD
        self.btn_b._bg = C.ACCENT if which == "B" else C.CARD
        self.btn_a.config(bg=self.btn_a._bg, fg=C.BG if which == "A" else C.FG)
        self.btn_b.config(bg=self.btn_b._bg, fg=C.BG if which == "B" else C.FG)
        self._render_left()

    def _render_left(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1:
            return
        self._scale = min(cw / self.bw, ch / self.bh)
        fw, fh = max(int(self.bw * self._scale), 1), max(int(self.bh * self._scale), 1)
        self._ox, self._oy = (cw - fw) // 2, (ch - fh) // 2
        arr = self.arrA if self.show == "A" else self.arrB
        pil = Image.fromarray(arr).resize((fw, fh), Image.LANCZOS)
        self._left_photo = ImageTk.PhotoImage(pil)
        self.canvas.itemconfig(self.img_item, image=self._left_photo)
        self.canvas.coords(self.img_item, self._ox, self._oy)

    def _inspect(self, e):
        if self._scale <= 0:
            return
        ix = int((e.x - self._ox) / self._scale)
        iy = int((e.y - self._oy) / self._scale)
        if not (0 <= ix < self.bw and 0 <= iy < self.bh):
            self.canvas.itemconfig(self.cross_h, state="hidden")
            self.canvas.itemconfig(self.cross_v, state="hidden")
            return

        # Croix de visée
        self.canvas.coords(self.cross_h, self._ox, e.y, self._ox + self.bw * self._scale, e.y)
        self.canvas.coords(self.cross_v, e.x, self._oy, e.x, self._oy + self.bh * self._scale)
        self.canvas.itemconfig(self.cross_h, state="normal")
        self.canvas.itemconfig(self.cross_v, state="normal")
        self.canvas.tag_raise(self.cross_h)
        self.canvas.tag_raise(self.cross_v)

        ra = self.arrA[iy, ix]
        rb = self.arrB[iy, ix]
        self.coord_lbl.config(text=f"({ix}, {iy})")
        self.swatchA.config(bg=f"#{ra[0]:02x}{ra[1]:02x}{ra[2]:02x}")
        self.swatchB.config(bg=f"#{rb[0]:02x}{rb[1]:02x}{rb[2]:02x}")
        self.valA.config(text=f"A  {ra[0]}, {ra[1]}, {ra[2]}")
        self.valB.config(text=f"B  {rb[0]}, {rb[1]}, {rb[2]}")
        d = np.abs(ra.astype(int) - rb.astype(int))
        self.delta_lbl.config(text=f"Δ  R {d[0]}   V {d[1]}   B {d[2]}")

        self._update_magnifier(ix, iy)

    def _update_magnifier(self, ix, iy):
        arr = self.arrA if self.show == "A" else self.arrB
        xs, xe = max(0, ix - MAG_HALF), min(self.bw, ix + MAG_HALF + 1)
        ys, ye = max(0, iy - MAG_HALF), min(self.bh, iy + MAG_HALF + 1)
        crop = arr[ys:ye, xs:xe]
        pil = Image.fromarray(crop).resize((MAG_SIZE, MAG_SIZE), Image.NEAREST)
        self._mag_photo = ImageTk.PhotoImage(pil)
        self.mag.itemconfig(self.mag_img, image=self._mag_photo)

    # =====================================================================
    #  Statistiques
    # =====================================================================
    def _compute_stats(self):
        absd = np.abs(self.arrA.astype(int) - self.arrB.astype(int))
        for i, cells in enumerate(self.stat_rows):
            ch = absd[:, :, i]
            cells[0].config(text=f"{ch.mean():.1f}")
            cells[1].config(text=f"{int(ch.max())}")
            cells[2].config(text=f"{(ch > 10).mean() * 100:.1f}%")


# =========================================================================
#  Tracé d'histogramme (A rempli, B en ligne)
# =========================================================================
class HistPlot(tk.Canvas):
    def __init__(self, master, title, ha, hb, color, **kw):
        super().__init__(master, bg=C.CARD, highlightthickness=1,
                         highlightbackground=C.BORDER, **kw)
        self.title, self.ha, self.hb, self.color = title, ha, hb, color
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        pl, pr, pt, pb = 6, 6, 18, 6
        pw, ph = w - pl - pr, h - pt - pb
        mx = max(int(self.ha.max()), int(self.hb.max()), 1)

        def pts(hist):
            out = []
            for i in range(256):
                out.append((pl + pw * i / 255, pt + ph - ph * hist[i] / mx))
            return out

        pa = pts(self.ha)
        poly = [pl, pt + ph] + [c for xy in pa for c in xy] + [pl + pw, pt + ph]
        self.create_polygon(*poly, fill=self.color, stipple="gray50", outline="")
        self.create_line(*[c for xy in pts(self.hb) for c in xy],
                         fill="#ffffff", width=1)
        self.create_text(pl + 2, 9, text=self.title, anchor="w",
                         fill=self.color, font=FONT_INFO)
