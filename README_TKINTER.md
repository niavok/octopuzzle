# Puzzle Solver - Tkinter Version

Version portée en Tkinter pour un débogage plus simple, sans séparation frontend/backend.

## Installation

```bash
pip install opencv-python numpy pillow
```

Note: Pas besoin d'installer `eel` pour cette version!

## Lancement

```bash
python puzzle_solver_tk.py
```

## Architecture (4 fichiers Python)

### 1. **models.py**
- `CalibrationData` - Configuration de calibration (ROI, background, min/max area)
- `PuzzlePiece` - Représentation d'une pièce détectée
- `PuzzlePieceDetector` - Détection avec OpenCV (adaptiveThreshold + morphologie)
- `PuzzleMatcher` - Matching de pièces basé sur les tabs
- `PuzzleSolver` - Gestion de la résolution

### 2. **image_utils.py**
- Conversion OpenCV ↔ PIL ↔ Tkinter PhotoImage
- Cache d'images pour éviter les rechargements
- Fonctions de dessin (ROI overlay, rectangles, highlights)
- Extraction de pièces avec highlight

### 3. **widgets.py**
- `CalibrationCanvas` - Canvas interactif avec drag ROI/background
  - Feedback visuel temps réel pendant le drag
  - Mode ROI ou background
- `ImagePanel` - Affichage pièce reference/suggestion
- `StatsBar` - Barre de progression et statistiques
- `CalibrationStatusDisplay` - Indicateurs de statut calibration

### 4. **puzzle_solver_tk.py**
- `PuzzleSolverApp` - Application principale (Tk)
- `Step1Frame` - Calibration puzzle state (1 image)
- `Step2Frame` - Calibration available pieces (multi-images)
- `Step3Frame` - Interface de résolution

## Workflow

### Étape 1: Puzzle State
1. Cliquer "📷 Browse Image" pour charger l'image du puzzle à compléter
2. Cliquer "1. Select Fill Zone" puis drag sur l'image pour sélectionner la zone
3. Cliquer "2. Select Background" puis drag sur le fond pour échantillonner
4. Ajuster Min/Max Area si nécessaire
5. Cocher "Show Debug" pour voir la détection en temps réel
6. Cliquer "Next: Load Available Pieces →"

### Étape 2: Available Pieces
1. Cliquer "📷 Browse Images (multiple)" pour charger les images des pièces disponibles
2. Configurer ROI et Background (s'applique à toutes les images)
3. Utiliser le menu déroulant pour prévisualiser chaque image
4. Ajuster les paramètres et vérifier avec "Show Debug"
5. Cliquer "Next: Validate & Start →"

### Étape 3: Solving
1. L'interface affiche:
   - **Panneau gauche** 🔴: Pièce de référence (déjà placée)
   - **Panneau droit** 🟢: Pièce suggérée à connecter
2. Choisir:
   - **✓ It Fits!** - La pièce correspond, elle est placée
   - **✗ No Match** - La pièce ne correspond pas, marquer comme rejeté
   - **⊘ Skip** - Passer à la suggestion suivante
3. La barre de progression montre l'avancement

## Améliorations par rapport à la version Eel

✅ **Pas de problèmes de sync frontend/backend**
- Tout en Python, un seul process

✅ **Drag & drop natif plus fiable**
- Tkinter Canvas avec binding direct
- Pas de conversion coordonnées JS ↔ Python

✅ **Débogage simplifié**
- `print()` fonctionne directement
- Breakpoints Python utilisables
- Pas de console JavaScript à surveiller

✅ **Gestion d'état simplifiée**
- Variables Python directes
- Pas de `await eel.xxx()`
- Pas de cache d'images fragmenté

✅ **Preview temps réel garanti**
- Événements souris natifs
- Pas de latence réseau

## Détection de pièces

L'algorithme utilise:
1. **Gaussian Blur** - Réduction du bruit
2. **Adaptive Threshold** - Binarisation adaptative (fonctionne mieux que OTSU)
3. **Morphological Operations** - Fermeture puis ouverture pour nettoyer
4. **Contour Detection** - Extraction des contours
5. **Area Filtering** - Filtrage par min/max area

**Légende debug:**
- **Vert** = Pièce valide (area dans la plage)
- **Rouge** = Rejeté (area hors plage)

## Paramètres recommandés

**Pour petites pièces de puzzle:**
- Min Area: 500-1000 px²
- Max Area: 20000-50000 px²

**Pour grandes pièces:**
- Min Area: 2000-5000 px²
- Max Area: 100000+ px²

## Troubleshooting

**Problème:** Aucune pièce détectée
- Vérifier que ROI est bien sélectionné
- Essayer avec/sans background sample
- Ajuster Min/Max Area
- Activer "Show Debug" pour voir les contours

**Problème:** Trop de faux positifs
- Augmenter Min Area
- Sélectionner un background sample
- Réduire la ROI pour exclure les bords

**Problème:** Images ne s'affichent pas dans Step 3
- Vérifier que les pièces ont bien été détectées (Step 1 et 2)
- Regarder les messages dans la console Python

## Nettoyage

Les fichiers temporaires sont automatiquement nettoyés à la fermeture de l'application.
