% Octopuzzle – Analyse du trou
% Révision: `python octopuzzle.py` au 2024-XX-XX

# Objectif

Modéliser automatiquement la grille de pièces manquantes à partir d’une photo du puzzle partiellement résolu. L’utilisateur fournit deux sélections :

1. **ROI extérieure** – englobe la cavité complète, bord compris.
2. **ROI intérieure** – zone homogène à l’intérieur du trou, sans chevaucher les bordures.

Le pipeline exploite ces deux zones pour dériver :

- le contour du trou (bord continu),
- les séparations internes entre pièces,
- la grille estimée,
- un nuancier moyen utilisable comme fond de référence.

# Pipeline

```
image
 ├─ ROI extérieure (cropped)
 │   ├─ Gris + blur (5×5)
 │   ├─ Seuils Canny dynamiques (σ 0.75/1.75)
 │   ├─ Masque « anneau » (ROI ext – ROI int)
 │   └─ Morph close → contour(s) → plus long = bord du trou
 │
 └─ ROI intérieure (cropped)
     ├─ Gris + blur (5×5)
     ├─ Seuils Canny dynamiques (σ 1.2/2.3)
     ├─ Masque d’ombre (mean − 0.8·σ)
     ├─ Canny & masque → ouverture/fermeture
     └─ HoughLinesP (min len = min(w,h)/3)
           ├─ θ < 25° → horizontales
           └─ θ > 65° → verticales
         → clustering tolérance 8% → lignes de grille
```

S’y ajoutent :

- **Grille estimée** : combinaison des lignes verticales/horizontales, associée à des cellules `(x, y, w, h)`.
- **Couleur moyenne** : moyenne BGR de la ROI interne (stockée comme `background_sample`).
- **Couches debug** : bord, anneau, contour interne, masque ombre, grille.

# Paramètres clés

| Étape                   | Paramètre                        | Rôle                                                    |
|-------------------------|----------------------------------|---------------------------------------------------------|
| Canny bord externe      | `σ` dynamique (0.75/1.75)        | suit le bord même sur photos sous/surexposées          |
| Masque anneau           | `outer_roi - inner_roi`          | élimine les détails internes du puzzle                 |
| Canny interne           | `σ` dynamique (1.2/2.3)          | détecte les lignes d’ombre entre pièces                |
| Masque ombre            | `mean − 0.8·σ`                   | supprime la texture homogène de la zone centrale       |
| Hough                   | `minLineLength = min(w,h)/3`     | ignore les traces trop courtes                         |
| Clustering lignes       | tolérance `0.08 * dimension`     | fusionne les lignes proches (évite doublons)           |

Valeurs adaptatives pour éviter les réglages manuels sur chaque image. À ajuster si les fichiers de test évoluent (voir TODO.md).

# Limitations connues

- **Textures internes** : une nervure de table ou une bordure de zone complétée peut passer le filtre si elle présente un contraste équivalent aux joints des pièces.
- **Concavités / trous non convexes** : pas encore d’analyse des « dents » du trou ; la grille reste rectangulaire.
- **Lignes manquantes** : la Hough peut rater une limite si la zone interne n’englobe pas suffisamment de contraste.
- **ROI externe** : toujours manuel. Prochain jalon : snapper automatiquement sur le contour détecté.

# Futur proche

- Ajouter un « snap » du ROI externe sur le contour du trou (ballon qui gonfle jusqu’au bord).
- Mesurer et signaler les concavités pour raffiner la grille.
- Offrir un réglage visuel (slider sigma) ou auto-ajustement si la grille renvoyée est vide.
