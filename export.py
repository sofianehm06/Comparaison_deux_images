# -*- coding: utf-8 -*-
"""
Génération et export d'un rapport de comparaison (image PNG).

Le rapport rassemble sur une seule image :
  • un en-tête (titre, noms des fichiers, date) ;
  • le score de similarité (SSIM) avec jauge colorée et 4 métriques ;
  • les images A et B et la vue des différences, côte à côte.
"""

import math
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity

from theme import C, hex_to_rgb
from similarity_view import score_color, verdict

RED = hex_to_rgb(C.RED)


# -------------------------------------------------------------------------
#  Polices
# -------------------------------------------------------------------------
def _font(size, bold=False):
    for name in ((r"C:\Windows\Fonts\segoeuib.ttf", "segoeuib.ttf")
                 if bold else (r"C:\Windows\Fonts\segoeui.ttf", "segoeui.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _ctext(draw, cx, y, text, font, fill):
    """Texte centré horizontalement sur cx."""
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


# -------------------------------------------------------------------------
#  Calculs
# -------------------------------------------------------------------------
def compute_metrics(cv_a, cv_b):
    h, w = cv_a.shape[:2]
    scale = min(1.0, 1400 / max(h, w))
    size = (max(int(w * scale), 1), max(int(h * scale), 1))
    a = cv2.resize(cv_a, size, interpolation=cv2.INTER_AREA)
    b = cv2.resize(cv_b, size, interpolation=cv2.INTER_AREA)

    ssim = structural_similarity(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY),
                                 cv2.cvtColor(b, cv2.COLOR_BGR2GRAY),
                                 data_range=255)
    diff = a.astype(np.float64) - b.astype(np.float64)
    mse = float(np.mean(diff ** 2))
    rmse = math.sqrt(mse)
    psnr = math.inf if mse == 0 else 10 * math.log10(255 ** 2 / mse)

    corr = []
    for ch in range(3):
        ha = cv2.calcHist([a], [ch], None, [256], [0, 256])
        hb = cv2.calcHist([b], [ch], None, [256], [0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        corr.append(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))

    return {
        "score": max(0.0, ssim) * 100,
        "ssim": max(0.0, ssim) * 100,
        "psnr": psnr,
        "rmse": rmse,
        "hist": max(0.0, float(np.mean(corr))) * 100,
    }


def _overlay_rgb(cv_a, cv_b):
    """Vue des différences : zones modifiées teintées en rouge sur A (RGB)."""
    h, w = cv_a.shape[:2]
    b = cv2.resize(cv_b, (w, h), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(cv2.absdiff(cv_a, b), cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(g, 25, 255, cv2.THRESH_BINARY)
    out = cv2.cvtColor(cv_a, cv2.COLOR_BGR2RGB)
    sel = m > 0
    out[sel] = (out[sel].astype(np.float32) * 0.4
                + np.array(RED, np.float32) * 0.6).astype(np.uint8)
    return out


# -------------------------------------------------------------------------
#  Construction du rapport
# -------------------------------------------------------------------------
def build_report(cv_a, cv_b, name_a, name_b):
    W, M, GAP = 1400, 40, 30
    m = compute_metrics(cv_a, cv_b)

    # Vignettes : A, B, différences
    cell_w = (W - 2 * M - 2 * GAP) // 3
    target_h = 360
    thumbs = []
    for img in (cv2.cvtColor(cv_a, cv2.COLOR_BGR2RGB),
                cv2.cvtColor(cv_b, cv2.COLOR_BGR2RGB),
                _overlay_rgb(cv_a, cv_b)):
        im = Image.fromarray(img)
        im.thumbnail((cell_w, target_h), Image.LANCZOS)
        thumbs.append(im)
    thumb_h = max(t.height for t in thumbs)

    header_h, score_h, foot_h = 122, 250, 56
    img_h = thumb_h + 54
    H = header_h + score_h + img_h + foot_h

    canvas = Image.new("RGB", (W, H), hex_to_rgb(C.BG))
    d = ImageDraw.Draw(canvas)

    fg, dim, panel, card = (hex_to_rgb(C.FG), hex_to_rgb(C.FG_DIM),
                            hex_to_rgb(C.PANEL), hex_to_rgb(C.CARD))

    # --- En-tête ------------------------------------------------------
    d.rectangle([0, 0, W, header_h], fill=panel)
    d.rectangle([0, header_h, W, header_h + 3], fill=hex_to_rgb(C.ACCENT))
    # Pastille d'accent + titre (on évite les emojis : pas de glyphe dans la police)
    d.ellipse([M, 34, M + 26, 60], outline=hex_to_rgb(C.ACCENT), width=4)
    d.line([M + 23, 57, M + 34, 68], fill=hex_to_rgb(C.ACCENT), width=4)
    d.text((M + 48, 26), "Rapport de comparaison d'images",
           font=_font(34, True), fill=fg)
    date = datetime.datetime.now().strftime("%d/%m/%Y  %H:%M")
    d.text((M, 78), f"A : {name_a[:40]}     B : {name_b[:40]}     •     {date}",
           font=_font(18), fill=dim)

    # --- Score --------------------------------------------------------
    y = header_h + 3
    score = m["score"]
    col = hex_to_rgb(score_color(score))
    _ctext(d, W / 2, y + 18, "SCORE DE SIMILARITÉ (SSIM)", _font(16, True), dim)
    _ctext(d, W / 2, y + 40, f"{score:.1f} %", _font(60, True), col)
    _ctext(d, W / 2, y + 116, verdict(score), _font(22), fg)

    # Jauge
    gw, gh = 620, 18
    gx, gy = (W - gw) // 2, y + 156
    d.rounded_rectangle([gx, gy, gx + gw, gy + gh], gh // 2, fill=card)
    fw = max(int(gw * score / 100), gh)
    d.rounded_rectangle([gx, gy, gx + fw, gy + gh], gh // 2, fill=col)

    # Métriques (4 chips)
    psnr_txt = "∞ dB" if math.isinf(m["psnr"]) else f"{m['psnr']:.1f} dB"
    chips = [("SSIM", f"{m['ssim']:.1f} %"), ("PSNR", psnr_txt),
             ("RMSE", f"{m['rmse']:.1f}"), ("Histogramme", f"{m['hist']:.1f} %")]
    chip_w = (W - 2 * M - 3 * GAP) // 4
    cy = y + 192
    for i, (title, value) in enumerate(chips):
        cx = M + i * (chip_w + GAP)
        d.rounded_rectangle([cx, cy, cx + chip_w, cy + 48], 8, fill=card)
        d.text((cx + 16, cy + 6), title, font=_font(14), fill=dim)
        d.text((cx + 16, cy + 23), value, font=_font(20, True), fill=fg)

    # --- Images -------------------------------------------------------
    y = header_h + score_h
    captions = ["Image A", "Image B", "Différences"]
    for i, (im, cap) in enumerate(zip(thumbs, captions)):
        cell_x = M + i * (cell_w + GAP)
        px = cell_x + (cell_w - im.width) // 2
        canvas.paste(im, (px, y + 6))
        _ctext(d, cell_x + cell_w / 2, y + thumb_h + 16, cap, _font(18, True), dim)

    # --- Pied de page -------------------------------------------------
    d.rectangle([0, H - foot_h, W, H], fill=panel)
    d.text((M, H - foot_h + 18), "Généré par Image Comparator Pro",
           font=_font(15), fill=dim)
    return canvas


# -------------------------------------------------------------------------
#  Export interactif
# -------------------------------------------------------------------------
def export_report(parent, cv_a, cv_b, name_a, name_b):
    """Construit le rapport, demande où l'enregistrer, ouvre le fichier."""
    try:
        report = build_report(cv_a, cv_b, name_a, name_b)
    except Exception as exc:
        messagebox.showerror("Export", f"Échec de la génération :\n{exc}",
                             parent=parent)
        return None

    default = "rapport_comparaison.png"
    path = filedialog.asksaveasfilename(
        parent=parent, title="Enregistrer le rapport",
        defaultextension=".png", initialfile=default,
        filetypes=[("Image PNG", "*.png"), ("Image JPEG", "*.jpg")])
    if not path:
        return None

    try:
        if path.lower().endswith((".jpg", ".jpeg")):
            report.save(path, quality=95)
        else:
            report.save(path)
    except Exception as exc:
        messagebox.showerror("Export", f"Impossible d'enregistrer :\n{exc}",
                             parent=parent)
        return None

    try:
        import os
        os.startfile(path)          # ouvre le rapport (Windows)
    except Exception:
        pass
    return path
