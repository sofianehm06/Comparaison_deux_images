import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import time
from PIL import Image
import math


# CHARGEMENT ET REDIMENSION

def load_and_match_size(p1, p2):
    """Charge et redimensionne les deux images pour qu'elles aient la même taille"""
    img1 = Image.open(p1).convert("RGB")
    img2 = Image.open(p2).convert("RGB")

    w1, h1 = img1.size
    w2, h2 = img2.size

    w = min(w1, w2)
    h = min(h1, h2)

    ratio1 = min(w / w1, h / h1)
    ratio2 = min(w / w2, h / h2)

    new1 = (int(w1 * ratio1), int(h1 * ratio1))
    new2 = (int(w2 * ratio2), int(h2 * ratio2))

    img1 = img1.resize(new1)
    img2 = img2.resize(new2)

    final_w = min(img1.size[0], img2.size[0])
    final_h = min(img1.size[1], img2.size[1])

    img1 = img1.crop((0, 0, final_w, final_h))
    img2 = img2.crop((0, 0, final_w, final_h))

    return img1, img2


# HISTOGRAMME

def similarity_histogram(img1, img2):
    """Calcule la similarité basée sur les histogrammes"""
    h1 = img1.histogram()
    h2 = img2.histogram()

    i = 0
    u = 0

    for a, b in zip(h1, h2):
        i += min(a, b)
        u += max(a, b)

    return i / u if u != 0 else 0


# PIXEL RGB

def similarity_pixel(img1, img2, threshold=25):
    """Calcule la similarité pixel par pixel"""
    w, h = img1.size
    p1 = img1.load()
    p2 = img2.load()

    diff = 0
    total = w * h

    for x in range(w):
        for y in range(h):
            r1, g1, b1 = p1[x, y]
            r2, g2, b2 = p2[x, y]
            dist = math.sqrt((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)

            if dist > threshold:
                diff += 1

    return 1 - diff / total


# COMPARAISON PAR BLOCS

def similarity_blocks(img1, img2, block=20):
    """Calcule la similarité par blocs"""
    w, h = img1.size
    p1 = img1.load()
    p2 = img2.load()

    good = 0
    total = 0

    for x in range(0, w, block):
        for y in range(0, h, block):
            diff = 0
            count = 0

            for i in range(block):
                for j in range(block):
                    if x+i < w and y+j < h:
                        g1 = sum(p1[x+i, y+j]) / 3
                        g2 = sum(p2[x+i, y+j]) / 3
                        
                        if abs(g1 - g2) > 15:
                            diff += 1
                        count += 1

            if count > 0 and diff / count < 0.20:
                good += 1
            total += 1

    return good / total if total > 0 else 0


# REDIMENSIONNEMENT POUR ROTATIONS

def match_rotated_size(img1, img2_rotated):
    """Redimensionne deux images pour qu'elles aient la même taille après rotation"""
    w1, h1 = img1.size
    w2, h2 = img2_rotated.size
    
    # Prendre la plus petite dimension commune
    target_w = min(w1, w2)
    target_h = min(h1, h2)
    
    # Redimensionner les deux images
    img1_resized = img1.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img2_resized = img2_rotated.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    return img1_resized, img2_resized


# ÉVALUATION DES TRANSFORMATIONS AVEC DÉTECTION DE ROTATION

def evaluate_transformations(img1, img2):
    """Teste toutes les transformations possibles (rotations et miroirs)"""
    best_score = 0
    best_transform = "original"
    best_scores = (0, 0, 0)
    
    transformations = [
        ("original", img2),
        ("rotation 90°", img2.rotate(-90, expand=True)),
        ("rotation 180°", img2.rotate(180, expand=True)),
        ("rotation 270°", img2.rotate(-270, expand=True)),
        ("miroir horizontal", img2.transpose(Image.FLIP_LEFT_RIGHT)),
        ("miroir vertical", img2.transpose(Image.FLIP_TOP_BOTTOM)),
    ]
    
    for transform_name, img2_transformed in transformations:
        try:
            # Redimensionner pour correspondre aux dimensions
            img1_test, img2_test = match_rotated_size(img1, img2_transformed)
            
            # Calculer les scores
            s_pixel = similarity_pixel(img1_test, img2_test)
            s_hist = similarity_histogram(img1_test, img2_test)
            s_blocks = similarity_blocks(img1_test, img2_test)
            
            # Score final pondéré avec pénalisation
            final_score = 0.6 * s_pixel + 0.25 * s_hist + 0.15 * s_blocks
            
            if final_score > best_score:
                best_score = final_score
                best_transform = transform_name
                best_scores = (s_pixel, s_hist, s_blocks)
                
        except Exception as e:
            continue
    
    return best_score, best_transform, best_scores


# DÉTERMINER SI C'EST LA MÊME IMAGE

def determine_if_same_image(score, transform):
    """Détermine si les images sont identiques en fonction du score"""
    if score >= 0.95:
        if transform == "original":
            return "MÊME IMAGE (originale)"
        else:
            return f"MÊME IMAGE ({transform})"
    elif score >= 0.90:
        if transform == "original":
            return "SIMILITUDE FORTE (images très proches)"
        else:
            return f"SIMILITUDE FORTE ({transform})"
    elif score >= 0.65:
        if transform == "original":
            return "DIFFÉRENT (largement différent)"
        else:
            return f"DIFFÉRENT ({transform})"
    else:
        return "COMPLÈTEMENT DIFFÉRENT"


# COMPARAISON PRINCIPALE

def compare_images(path1, path2):
    """Compare deux images avec toutes les transformations possibles"""
    start_time = time.time()

    img1, img2 = load_and_match_size(path1, path2)
    
    final_score, best_transform, scores = evaluate_transformations(img1, img2)
    s_pixel, s_hist, s_blocks = scores
    
    category = determine_if_same_image(final_score, best_transform)
    
    defiance = 1 - final_score
    exec_time = time.time() - start_time

    return final_score, defiance, exec_time, s_pixel, s_hist, s_blocks, category


# INTERFACE GRAPHIQUE

class ImageComparatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Détecteur d'Images Identiques")
        self.root.geometry("550x600")
        self.root.configure(bg="#f0f0f0")
        
        self.image1_path = None
        self.image2_path = None
        
        title_label = tk.Label(root, text="🔍 Détecteur d'Images Identiques", 
                              font=("Arial", 18, "bold"), bg="#f0f0f0", fg="#2c3e50")
        title_label.pack(pady=15)
        
        # Frame pour les boutons de chargement
        load_frame = tk.Frame(root, bg="#f0f0f0")
        load_frame.pack(pady=10)
        
        # Bouton Image 1
        self.btn_load1 = tk.Button(load_frame, text="📁 Image 1", 
                                  command=self.load_image1, width=18, height=2,
                                  bg="#27ae60", fg="white", font=("Arial", 10, "bold"))
        self.btn_load1.grid(row=0, column=0, padx=10, pady=5)
        
        # Label pour image 1
        self.label_img1 = tk.Label(load_frame, text="Aucune image", 
                                  bg="#d5f4e6", width=20, height=2, relief="groove")
        self.label_img1.grid(row=1, column=0, padx=10, pady=5)
        
        # Bouton Image 2
        self.btn_load2 = tk.Button(load_frame, text="📁 Image 2", 
                                  command=self.load_image2, width=18, height=2,
                                  bg="#3498db", fg="white", font=("Arial", 10, "bold"))
        self.btn_load2.grid(row=0, column=1, padx=10, pady=5)
        
        # Label pour image 2
        self.label_img2 = tk.Label(load_frame, text="Aucune image", 
                                  bg="#d6eaf8", width=20, height=2, relief="groove")
        self.label_img2.grid(row=1, column=1, padx=10, pady=5)
        
        # Bouton Comparer
        self.btn_compare = tk.Button(root, text="🔍 Vérifier si c'est la même image", 
                                    command=self.compare_images, width=30, height=2,
                                    bg="#e74c3c", fg="white", font=("Arial", 12, "bold"),
                                    state="disabled")
        self.btn_compare.pack(pady=15)
        
        # Frame pour les résultats
        result_container = tk.Frame(root, bg="#2c3e50", relief="groove", bd=2)
        result_container.pack(pady=10, padx=20, fill="x")
        
        result_title = tk.Label(result_container, text="📊 RÉSULTAT DE DÉTECTION", 
                               font=("Arial", 12, "bold"), bg="#34495e", fg="white")
        result_title.pack(fill="x", pady=2)
        
        self.result_frame = tk.Frame(result_container, bg="#ecf0f1")
        self.result_frame.pack(padx=10, pady=10, fill="x")
        
        # Labels pour les résultats
        self.result_labels = {}
        methods = ["Détection", "Pixel RGB", "Histogramme", "Blocs", 
                  "Score final", "Temps"]
        
        for i, method in enumerate(methods):
            line_frame = tk.Frame(self.result_frame, bg="#ecf0f1")
            line_frame.grid(row=i, column=0, columnspan=2, sticky="ew", pady=3)
            
            label_title = tk.Label(line_frame, text=method + ":", 
                                  font=("Arial", 10, "bold"), bg="#ecf0f1", 
                                  width=12, anchor="w")
            label_title.pack(side="left", padx=(0, 10))
            
            label_value = tk.Label(line_frame, text="--", 
                                  font=("Arial", 10), bg="#ecf0f1", 
                                  width=30, anchor="w")
            label_value.pack(side="left")
            self.result_labels[method] = label_value
        
        # Barre de progression
        self.progress_frame = tk.Frame(root, bg="#f0f0f0")
        self.progress_frame.pack(pady=10, fill="x", padx=20)
        
        self.progress_label = tk.Label(self.progress_frame, text="", 
                                      bg="#f0f0f0", font=("Arial", 10))
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='indeterminate', length=450)
        self.progress_bar.pack(pady=5)
        
        # Label d'état
        self.status_label = tk.Label(root, text="", bg="#f0f0f0", font=("Arial", 9), fg="#666666")
        self.status_label.pack(pady=5)
        
        # Frame pour les boutons d'action
        action_frame = tk.Frame(root, bg="#f0f0f0")
        action_frame.pack(pady=10)
        
        # Bouton Effacer
        btn_clear = tk.Button(action_frame, text="🗑️ Effacer", 
                             command=self.clear_all, width=15,
                             bg="#95a5a6", fg="white", font=("Arial", 10))
        btn_clear.grid(row=0, column=0, padx=5)
        
        # Bouton Quitter
        btn_quit = tk.Button(action_frame, text="🚪 Quitter", 
                            command=root.quit, width=15,
                            bg="#e74c3c", fg="white", font=("Arial", 10))
        btn_quit.grid(row=0, column=1, padx=5)
        
    def load_image1(self):
        """Charge la première image"""
        path = filedialog.askopenfilename(
            title="Sélectionner la première image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.gif"), 
                      ("Tous les fichiers", "*.*")]
        )
        if path:
            self.image1_path = path
            filename = os.path.basename(path)
            self.label_img1.config(text=filename[:18] + ("..." if len(filename) > 18 else ""))
            self.check_ready()
            self.update_status(f"✅ Image 1 chargée : {filename}")
    
    def load_image2(self):
        """Charge la deuxième image"""
        path = filedialog.askopenfilename(
            title="Sélectionner la deuxième image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.gif"), 
                      ("Tous les fichiers", "*.*")]
        )
        if path:
            self.image2_path = path
            filename = os.path.basename(path)
            self.label_img2.config(text=filename[:18] + ("..." if len(filename) > 18 else ""))
            self.check_ready()
            self.update_status(f"✅ Image 2 chargée : {filename}")
    
    def check_ready(self):
        """Vérifie si les deux images sont chargées"""
        if self.image1_path and self.image2_path:
            self.btn_compare.config(state="normal", bg="#c0392b")
            self.update_status("✅ Prêt à vérifier si c'est la même image")
        else:
            self.btn_compare.config(state="disabled", bg="#e74c3c")
    
    def update_status(self, message):
        """Met à jour le message de statut"""
        self.status_label.config(text=message)
        self.root.update()
    
    def compare_images(self):
        """Lance la comparaison des images"""
        if not self.image1_path or not self.image2_path:
            messagebox.showerror("Erreur", "Veuillez charger les deux images d'abord")
            return
        
        try:
            self.btn_compare.config(state="disabled", text="Vérification...")
            self.btn_load1.config(state="disabled")
            self.btn_load2.config(state="disabled")
            
            self.progress_bar.start()
            self.progress_label.config(text="Vérification des transformations...")
            self.update_status("🔍 Test en cours : originale, rotations, miroirs...")
            
            final, defiance, exec_time, s_pixel, s_hist, s_blocks, category = compare_images(
                self.image1_path, self.image2_path
            )
            
            self.progress_bar.stop()
            self.progress_label.config(text="✅ Vérification terminée!")
            
            self.display_results(s_pixel, s_hist, s_blocks, final, exec_time, category)
            
            self.update_status("✅ Analyse terminée")
            
        except Exception as e:
            self.progress_bar.stop()
            self.progress_label.config(text="")
            messagebox.showerror("Erreur", f"Une erreur est survenue : {str(e)}")
            self.update_status("❌ Erreur lors de la vérification")
        finally:
            self.btn_compare.config(state="normal", text="🔍 Vérifier si c'est la même image")
            self.btn_load1.config(state="normal")
            self.btn_load2.config(state="normal")
    
    def display_results(self, s_pixel, s_hist, s_blocks, final, exec_time, category):
        """Affiche les résultats dans l'interface"""
        self.result_labels["Détection"].config(text=category)
        self.result_labels["Pixel RGB"].config(text=f"{s_pixel:.2%}")
        self.result_labels["Histogramme"].config(text=f"{s_hist:.2%}")
        self.result_labels["Blocs"].config(text=f"{s_blocks:.2%}")
        self.result_labels["Score final"].config(text=f"{final:.2%}")
        self.result_labels["Temps"].config(text=f"{exec_time:.3f}s")
        
        if "MÊME IMAGE" in category:
            self.result_labels["Détection"].config(fg="#27ae60", font=("Arial", 10, "bold"))
            self.root.title(f"✅ MÊME IMAGE - Détecteur d'Images Identiques")
        elif "SIMILITUDE FORTE" in category:
            self.result_labels["Détection"].config(fg="#f39c12", font=("Arial", 10, "bold"))
            self.root.title(f"⚠️ SIMILITÉ FORTE - Détecteur d'Images Identiques")
        elif "DIFFÉRENT" in category:
            self.result_labels["Détection"].config(fg="#e74c3c", font=("Arial", 10, "bold"))
            self.root.title(f"❌ DIFFÉRENT - Détecteur d'Images Identiques")
        else:
            self.result_labels["Détection"].config(fg="#c0392b", font=("Arial", 10, "bold"))
            self.root.title(f"❌ COMPLÈTEMENT DIFFÉRENT - Détecteur d'Images Identiques")
        
        if final >= 0.95:
            self.result_labels["Score final"].config(fg="#27ae60")
        elif final >= 0.90:
            self.result_labels["Score final"].config(fg="#f39c12")
        elif final >= 0.70:
            self.result_labels["Score final"].config(fg="#e74c3c")
        else:
            self.result_labels["Score final"].config(fg="#c0392b")
    
    def clear_all(self):
        """Réinitialise l'interface"""
        self.image1_path = None
        self.image2_path = None
        self.label_img1.config(text="Aucune image")
        self.label_img2.config(text="Aucune image")
        
        for label in self.result_labels.values():
            label.config(text="--", fg="black", font=("Arial", 10))
        
        self.progress_label.config(text="")
        self.status_label.config(text="")
        self.btn_compare.config(state="disabled", bg="#e74c3c")
        self.root.title("Détecteur d'Images Identiques")
        self.update_status("📤 Chargez deux images pour vérifier si c'est la même")


# Point d'entrée principal
if __name__ == "__main__":
    root = tk.Tk()
    app = ImageComparatorGUI(root)
    app.update_status("📤 Chargez deux images pour vérifier si c'est la même")
    root.mainloop()