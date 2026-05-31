# -*- coding: utf-8 -*-
"""
Image Comparator Pro
====================
Un logiciel de comparaison de deux images :
  • chargement (boutons, clic, glisser-déposer) et aperçu côte à côte ;
  • comparaison avant/après et côte à côte (zoom synchronisé) ;
  • différences visuelles (4 modes) ;
  • score de similarité (SSIM, PSNR, RMSE, histogramme) ;
  • analyse pixel par pixel (loupe, stats par canal, histogrammes) ;
  • export d'un rapport PNG.

Lancement :  python app.py   (ou double-clic sur lancer.bat)
"""

import os
import re
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk, ImageDraw

from theme import (C, FONT, FONT_TITLE, FONT_SUB, FONT_LABEL, FONT_INFO,
                   FONT_STATUS, IMG_EXT, imread_unicode, cv2_to_pil,
                   hex_to_rgb, HoverButton)
from compare_view import CompareWindow
from diff_view import DiffWindow
from similarity_view import SimilarityWindow
from pixels_view import PixelsWindow
from matching_view import MatchingWindow
from export import export_report


# =========================================================================
#  Icône de l'application (loupe dessinée, sans fichier externe)
# =========================================================================
def make_icon(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 3, size - 3], size // 5,
                        fill=hex_to_rgb(C.ACCENT))
    ink = hex_to_rgb(C.BG)
    cx, cy, r = size * 0.42, size * 0.40, size * 0.20
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink,
              width=max(3, size // 16))
    d.line([cx + r * 0.7, cy + r * 0.7, size * 0.76, size * 0.80],
           fill=ink, width=max(4, size // 11))
    return img


# =========================================================================
#  Panneau d'image (titre, zone d'aperçu cliquable, infos)
# =========================================================================
class ImagePanel(tk.Frame):
    def __init__(self, master, title, on_click):
        super().__init__(master, bg=C.PANEL)
        self._on_click = on_click
        self._photo = None       # référence pour éviter le garbage collector
        self._pil = None         # image PIL source (pour re-render au resize)
        self._last_size = (0, 0)

        head = tk.Frame(self, bg=C.PANEL)
        head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(head, text=title, bg=C.PANEL, fg=C.ACCENT,
                 font=FONT_LABEL).pack(side="left")
        self.dim_lbl = tk.Label(head, text="", bg=C.PANEL, fg=C.FG_DIM,
                                font=FONT_INFO)
        self.dim_lbl.pack(side="right")

        self.card = tk.Frame(self, bg=C.CARD, highlightthickness=1,
                             highlightbackground=C.BORDER)
        self.card.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.preview = tk.Label(
            self.card, bg=C.CARD, fg=C.FG_DIM,
            text="\n\n📂\n\nCliquez pour charger\nune image",
            font=(FONT, 11), cursor="hand2", justify="center",
        )
        self.preview.pack(fill="both", expand=True)

        self.name_lbl = tk.Label(self, text="Aucun fichier", bg=C.PANEL,
                                 fg=C.FG_DIM, font=FONT_INFO, anchor="w")
        self.name_lbl.pack(fill="x", padx=14, pady=(0, 12))

        for w in (self.card, self.preview):
            w.bind("<Button-1>", lambda _: self._on_click())
        self.card.bind("<Configure>", self._on_resize)

    def set_image(self, pil_img, filename, dims):
        self._pil = pil_img
        self.name_lbl.config(text=filename, fg=C.FG)
        self.dim_lbl.config(text=dims)
        self._render()

    def clear(self):
        self._pil = None
        self._photo = None
        self.preview.config(image="", text="\n\n📂\n\nCliquez pour charger\nune image")
        self.name_lbl.config(text="Aucun fichier", fg=C.FG_DIM)
        self.dim_lbl.config(text="")

    def _on_resize(self, _):
        size = (self.card.winfo_width(), self.card.winfo_height())
        if self._pil is not None and size != self._last_size:
            self._last_size = size
            self._render()

    def _render(self):
        if self._pil is None:
            return
        cw = max(self.card.winfo_width() - 16, 50)
        ch = max(self.card.winfo_height() - 16, 50)
        img = self._pil.copy()
        img.thumbnail((cw, ch), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.preview.config(image=self._photo, text="")


# =========================================================================
#  Application principale
# =========================================================================
class ImageComparatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Comparator Pro")
        self.root.configure(bg=C.BG)
        self._center(1120, 740)
        self.root.minsize(900, 600)

        self.cv_a = None
        self.cv_b = None
        self.path_a = None
        self.path_b = None
        self._mode_buttons = []

        self._build_header()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._update_button_states()
        self._set_icon()
        self._bind_shortcuts()
        self._enable_dnd()

    # ---- Icône / raccourcis / glisser-déposer ---------------------------
    def _set_icon(self):
        try:
            self._icon = ImageTk.PhotoImage(make_icon(64))
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass

    def _bind_shortcuts(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.load_image("a"))
        r.bind("<Control-O>", lambda e: self.load_image("b"))   # Ctrl+Maj+O
        r.bind("<Control-r>", lambda e: self.reset())
        r.bind("<Control-e>", lambda e: self.on_export())
        r.bind("<Key-1>", lambda e: self.on_side_by_side())
        r.bind("<Key-2>", lambda e: self.on_diff())
        r.bind("<Key-3>", lambda e: self.on_similarity())
        r.bind("<Key-4>", lambda e: self.on_pixels())
        r.bind("<Key-5>", lambda e: self.on_matching())

    def _enable_dnd(self):
        """Active le glisser-déposer si tkinterdnd2 est disponible."""
        try:
            from tkinterdnd2 import DND_FILES
        except Exception:
            return
        for panel, slot in ((self.panel_a, "a"), (self.panel_b, "b")):
            try:
                panel.drop_target_register(DND_FILES)
                panel.dnd_bind("<<Drop>>", lambda e, s=slot: self._on_drop(s, e))
            except Exception:
                pass

    def _on_drop(self, slot, event):
        found = re.findall(r"\{([^}]*)\}", event.data)
        path = (found[0] if found else event.data.split()[0]).strip()
        if path:
            self._load_path(slot, path)

    # ---- Construction ---------------------------------------------------
    def _build_header(self):
        head = tk.Frame(self.root, bg=C.PANEL, height=72)
        head.pack(fill="x")
        head.pack_propagate(False)
        inner = tk.Frame(head, bg=C.PANEL)
        inner.pack(side="left", padx=22, pady=12)
        tk.Label(inner, text="🔍 Image Comparator Pro", bg=C.PANEL,
                 fg=C.FG, font=FONT_TITLE).pack(anchor="w")
        tk.Label(inner, text="Comparez deux images : différences, "
                 "similarité, analyse de pixels",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_SUB).pack(anchor="w")
        tk.Frame(self.root, bg=C.ACCENT, height=2).pack(fill="x")

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=C.BG)
        bar.pack(fill="x", padx=20, pady=14)

        HoverButton(bar, bg=C.ACCENT, text="📁  Charger l'image A",
                    command=lambda: self.load_image("a")).pack(side="left")
        HoverButton(bar, bg=C.ACCENT, text="📁  Charger l'image B",
                    command=lambda: self.load_image("b")).pack(side="left", padx=(10, 0))
        HoverButton(bar, bg=C.CARD, fg=C.FG, hover=C.ELEV, text="🔄  Réinitialiser",
                    command=self.reset).pack(side="left", padx=(10, 0))

        # Modes (activés une fois les deux images chargées)
        modes = [
            ("🖼️  Côte à côte", self.on_side_by_side, C.TEAL),
            ("🔬  Différences", self.on_diff,         C.ORANGE),
            ("📊  Similarité",  self.on_similarity,   C.GREEN),
            ("🔢  Pixels",      self.on_pixels,       C.ACCENT2),
            ("🧭  Correspondance", self.on_matching,  C.PINK),
            ("💾  Exporter",    self.on_export,       C.CARD),
        ]
        for text, cmd, color in reversed(modes):
            fg = C.FG if color == C.CARD else C.BG
            b = HoverButton(bar, bg=color, fg=fg, text=text, command=cmd)
            b.pack(side="right", padx=(10, 0))
            self._mode_buttons.append(b)

    def _build_body(self):
        body = tk.Frame(self.root, bg=C.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(0, weight=1)
        self.panel_a = ImagePanel(body, "Image A", lambda: self.load_image("a"))
        self.panel_a.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.panel_b = ImagePanel(body, "Image B", lambda: self.load_image("b"))
        self.panel_b.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=C.PANEL, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text="Prêt — chargez deux images "
                               "(boutons, clic ou glisser-déposer)",
                               bg=C.PANEL, fg=C.FG_DIM, font=FONT_STATUS, anchor="w")
        self.status.pack(side="left", padx=18)
        tk.Label(bar, text="Ctrl+O / Ctrl+Maj+O : charger A / B    "
                 "1·2·3·4 : modes    Ctrl+E : exporter    Ctrl+R : réinitialiser",
                 bg=C.PANEL, fg=C.FG_DIM, font=FONT_STATUS).pack(side="right", padx=18)

    # ---- Logique --------------------------------------------------------
    def load_image(self, slot):
        path = filedialog.askopenfilename(
            title=f"Choisir l'image {slot.upper()}", filetypes=IMG_EXT)
        if path:
            self._load_path(slot, path)

    def _load_path(self, slot, path):
        img = imread_unicode(path)
        if img is None:
            self._set_status(f"❌ Impossible de lire « {os.path.basename(path)} »", C.RED)
            return

        pil = cv2_to_pil(img)
        h, w = img.shape[:2]
        dims = f"{w} × {h} px"
        name = os.path.basename(path)
        if slot == "a":
            self.cv_a, self.path_a = img, path
            self.panel_a.set_image(pil, name, dims)
        else:
            self.cv_b, self.path_b = img, path
            self.panel_b.set_image(pil, name, dims)

        self._set_status(f"✅ Image {slot.upper()} chargée : {name} ({dims})", C.GREEN)
        self._update_button_states()

    def reset(self):
        self.cv_a = self.cv_b = None
        self.path_a = self.path_b = None
        self.panel_a.clear()
        self.panel_b.clear()
        self._set_status("🔄 Réinitialisé — chargez deux images", C.FG_DIM)
        self._update_button_states()

    def _update_button_states(self):
        ready = self.cv_a is not None and self.cv_b is not None
        for b in self._mode_buttons:
            b.config(state="normal" if ready else "disabled",
                     cursor="hand2" if ready else "arrow")

    def _set_status(self, msg, color=C.FG_DIM):
        self.status.config(text=msg, fg=color)

    # ---- Modes ----------------------------------------------------------
    def on_side_by_side(self):
        if self.cv_a is None or self.cv_b is None:
            return
        CompareWindow(self.root, self.cv_a, self.cv_b,
                      os.path.basename(self.path_a), os.path.basename(self.path_b))
        self._set_status("🖼️ Comparaison côte à côte ouverte", C.TEAL)

    def on_diff(self):
        if self.cv_a is None or self.cv_b is None:
            return
        DiffWindow(self.root, self.cv_a, self.cv_b,
                   os.path.basename(self.path_a), os.path.basename(self.path_b))
        self._set_status("🔬 Analyse des différences ouverte", C.ORANGE)

    def on_similarity(self):
        if self.cv_a is None or self.cv_b is None:
            return
        SimilarityWindow(self.root, self.cv_a, self.cv_b,
                         os.path.basename(self.path_a), os.path.basename(self.path_b))
        self._set_status("📊 Score de similarité calculé", C.GREEN)

    def on_pixels(self):
        if self.cv_a is None or self.cv_b is None:
            return
        PixelsWindow(self.root, self.cv_a, self.cv_b,
                     os.path.basename(self.path_a), os.path.basename(self.path_b))
        self._set_status("🔢 Analyse pixel par pixel ouverte", C.ACCENT2)

    def on_matching(self):
        if self.cv_a is None or self.cv_b is None:
            return
        MatchingWindow(self.root, self.cv_a, self.cv_b,
                       os.path.basename(self.path_a), os.path.basename(self.path_b))
        self._set_status("🧭 Correspondance (robuste à la rotation) ouverte", C.PINK)

    def on_export(self):
        if self.cv_a is None or self.cv_b is None:
            return
        self._set_status("💾 Génération du rapport…", C.FG)
        self.root.update_idletasks()
        path = export_report(self.root, self.cv_a, self.cv_b,
                             os.path.basename(self.path_a),
                             os.path.basename(self.path_b))
        if path:
            self._set_status(f"💾 Rapport enregistré : {os.path.basename(path)}", C.GREEN)
        else:
            self._set_status("Export annulé", C.FG_DIM)

    # ---- Utilitaire -----------------------------------------------------
    def _center(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")


def main():
    # Utilise TkinterDnD si disponible (active le glisser-déposer)
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    ImageComparatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
