# -*- coding: utf-8 -*-
"""
Fenêtre de reconnaissance / correspondance (robuste à la rotation).

Contrairement au SSIM/RMSE qui comparent les pixels à la même position,
cette analyse repère des points caractéristiques (ORB), les met en
correspondance entre A et B, puis estime la transformation géométrique
(rotation, échelle, translation). Elle détecte ainsi qu'une image est la
« même » qu'une autre même si elle a été pivotée.

  • Vue « Correspondances » : les points appariés reliés entre A et B.
  • Vue « Réalignement »     : B redressée sur A + SSIM recalculé.
"""

import tkinter as tk

import cv2
import numpy as np
from skimage.metrics import structural_similarity

from theme import (C, FONT, FONT_LABEL, FONT_INFO, FONT_HELP,
                   HoverButton, hex_to_rgb, fit_size)
from widgets import ZoomPanCanvas

PINK_BGR = hex_to_rgb(C.PINK)[::-1]   # OpenCV utilise le BGR
MAX_MATCH_LINES = 60


class MatchingWindow(tk.Toplevel):
    BASE = 820
    MAX_W = 1200
    MAX_H = 680

    def __init__(self, master, cv_a, cv_b, name_a="A", name_b="B"):
        super().__init__(master, bg=C.BG)
        self.title("Correspondance (robuste à la rotation)")
        self.geometry("1200x880")
        self.minsize(760, 560)
        self.configure(bg=C.BG)

        # Redimensionner chaque image pour rester raisonnable (indépendamment)
        self.a = self._fit(cv_a)
        self.b = self._fit(cv_b)
        self.ha, self.wa = self.a.shape[:2]

        self.view = "matches"
        self._compute()
        self._build_ui()
        self._refresh()
        self.bind("<Escape>", lambda e: self.destroy())

    def _fit(self, img):
        h, w = img.shape[:2]
        nw, nh = fit_size(w, h, self.BASE, self.BASE, allow_upscale=False)
        return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)

    # =====================================================================
    #  Détection + correspondance + transformation
    # =====================================================================
    def _compute(self):
        ga = cv2.cvtColor(self.a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(self.b, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(nfeatures=2000)
        self.kpA, desA = orb.detectAndCompute(ga, None)
        self.kpB, desB = orb.detectAndCompute(gb, None)

        good = []
        if desA is not None and desB is not None and len(self.kpA) >= 2 and len(self.kpB) >= 2:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING)
            for pair in bf.knnMatch(desA, desB, k=2):
                if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                    good.append(pair[0])
        self.good = good

        self.M = None
        self.inlier_mask = None
        self.n_inliers = 0
        self.angle = 0.0
        self.scale = 1.0
        if len(good) >= 4:
            ptsB = np.float32([self.kpB[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            ptsA = np.float32([self.kpA[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            M, inliers = cv2.estimateAffinePartial2D(
                ptsB, ptsA, method=cv2.RANSAC, ransacReprojThreshold=5)
            if M is not None and inliers is not None:
                self.M = M
                self.inlier_mask = inliers.ravel().astype(bool)
                self.n_inliers = int(inliers.sum())
                self.angle = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
                self.scale = float(np.hypot(M[0, 0], M[1, 0]))

        ratio = self.n_inliers / max(1, len(good))
        if self.M is not None and self.n_inliers >= 12 and ratio >= 0.25:
            self.verdict, self.vcolor, self.can_align = "Même image / même contenu", C.GREEN, True
        elif self.M is not None and self.n_inliers >= 6:
            self.verdict, self.vcolor, self.can_align = "Contenu partiellement similaire", C.ORANGE, True
        else:
            self.verdict, self.vcolor, self.can_align = "Images différentes", C.RED, False

        # SSIM avant (B brute alignée en taille) et après (B réalignée)
        gb_resized = cv2.cvtColor(cv2.resize(self.b, (self.wa, self.ha)), cv2.COLOR_BGR2GRAY)
        self.ssim_before = max(0.0, structural_similarity(ga, gb_resized, data_range=255)) * 100
        self.ssim_after = None
        if self.can_align:
            aligned = cv2.warpAffine(self.b, self.M, (self.wa, self.ha))
            gal = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
            self.ssim_after = max(0.0, structural_similarity(ga, gal, data_range=255)) * 100
            self._aligned = aligned

    # =====================================================================
    #  Interface
    # =====================================================================
    def _build_ui(self):
        top = tk.Frame(self, bg=C.PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🧭  Correspondance", bg=C.PANEL, fg=C.FG,
                 font=FONT_LABEL).pack(side="left", padx=16, pady=10)
        self.btn_m = HoverButton(top, bg=C.PINK, text="🔗  Correspondances",
                                 command=lambda: self._set_view("matches"))
        self.btn_m.pack(side="left", padx=(0, 6), pady=8)
        self.btn_a = HoverButton(top, bg=C.CARD, fg=C.FG, hover=C.ELEV,
                                 text="↺  Réalignement",
                                 command=lambda: self._set_view("aligned"))
        self.btn_a.pack(side="left", pady=8)
        if not self.can_align:
            self.btn_a.config(state="disabled", cursor="arrow")
        self.zoom_lbl = tk.Label(top, text="Zoom 100 %", bg=C.PANEL,
                                 fg=C.FG_DIM, font=FONT_INFO)
        self.zoom_lbl.pack(side="right", padx=12)
        tk.Frame(self, bg=C.PINK, height=2).pack(fill="x")

        # Bandeau de statistiques + verdict
        stat = tk.Frame(self, bg=C.BG)
        stat.pack(fill="x", padx=14, pady=(10, 4))
        rot = "aucune" if abs(self.angle) < 1 else f"≈ {abs(self.angle):.0f}°"
        self.stat_lbl = tk.Label(
            stat, bg=C.BG, fg=C.FG, font=FONT_INFO, anchor="w",
            text=(f"Points-clés  A : {len(self.kpA)}   B : {len(self.kpB)}      "
                  f"Correspondances fiables : {self.n_inliers} / {len(self.good)}      "
                  f"Rotation : {rot}      Échelle : {self.scale:.2f}"))
        self.stat_lbl.pack(side="left")
        tk.Label(stat, text=f"  {self.verdict}  ", bg=self.vcolor, fg=C.BG,
                 font=(FONT, 10, "bold")).pack(side="right")

        self.detail_lbl = tk.Label(self, bg=C.BG, fg=C.FG_DIM, font=FONT_INFO,
                                   anchor="w")
        self.detail_lbl.pack(fill="x", padx=14, pady=(0, 4))

        self.viewer = ZoomPanCanvas(self, self.MAX_W, self.MAX_H,
                                    zoom_cb=lambda p: self.zoom_lbl.config(
                                        text=f"Zoom {p} %"))
        self.viewer.pack(fill="both", expand=True, padx=8, pady=4)

        foot = tk.Frame(self, bg=C.PANEL)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, text="Molette = zoom   •   Clic droit = déplacer   •   "
                 "Double-clic = réinitialiser   •   Échap = fermer",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_HELP,
                 anchor="w").pack(side="left", padx=14, pady=5)

    # =====================================================================
    #  Vues
    # =====================================================================
    def _set_view(self, v):
        if v == "aligned" and not self.can_align:
            return
        self.view = v
        self._refresh()

    def _refresh(self):
        for btn, active in ((self.btn_m, self.view == "matches"),
                            (self.btn_a, self.view == "aligned")):
            if str(btn["state"]) == "disabled":
                continue
            btn._bg = C.PINK if active else C.CARD
            btn.config(bg=btn._bg, fg=C.BG if active else C.FG)

        if self.view == "matches":
            self.detail_lbl.config(
                text="Chaque ligne relie un point identifié dans A à son "
                     "correspondant dans B.")
            self.viewer.set_image(self._matches_image())
        else:
            after = f"{self.ssim_after:.1f} %" if self.ssim_after is not None else "—"
            self.detail_lbl.config(
                text=f"Gauche : image A   |   Droite : image B réalignée.      "
                     f"SSIM : {self.ssim_before:.1f} %  →  {after} après réalignement.",
                fg=C.GREEN)
            self.viewer.set_image(self._aligned_image())

    def _matches_image(self):
        if self.inlier_mask is not None:
            draw = [m for m, ok in zip(self.good, self.inlier_mask) if ok]
        else:
            draw = list(self.good)
        draw = sorted(draw, key=lambda m: m.distance)[:MAX_MATCH_LINES]
        vis = cv2.drawMatches(
            self.a, self.kpA, self.b, self.kpB, draw, None,
            matchColor=PINK_BGR, singlePointColor=(90, 90, 90),
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        return cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)

    def _aligned_image(self):
        gap = np.full((self.ha, 12, 3), hex_to_rgb(C.BORDER), dtype=np.uint8)
        comp = np.concatenate([
            cv2.cvtColor(self.a, cv2.COLOR_BGR2RGB), gap,
            cv2.cvtColor(self._aligned, cv2.COLOR_BGR2RGB)], axis=1)
        return comp
