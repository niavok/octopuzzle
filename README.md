# Octopuzzle

Assistant semi-automatique pour reconstituer les zones « monotones » d’un puzzle (ciels, aplats de couleur, neiges, etc.).  
L’idée n’est pas de résoudre tout le puzzle, mais d’aider à remplir les trous : l’utilisateur fournit une photo de la zone manquante et plusieurs photos des pièces disponibles ; Octopuzzle calibre les images, suggère les pièces les plus probables puis garde la trace de ce qui a déjà été placé.

## Comment ça marche ?

1. **Photo du trou** – on charge une photo de la zone à combler (ex. le morceau de ciel).  
2. **Photos des pièces disponibles** – on charge N photos des pièces encore libres (en vrac dans une boîte, sur la table, etc.).  
3. **Calibration optionnelle** – on peut définir une zone d’intérêt (ROI), un échantillon de fond et des bornes de surface pour aider la détection. Quand la détection fonctionne sans réglage, on peut passer directement à l’étape suivante.  
4. **Détection & archivage** – les pièces du trou et celles disponibles sont détectées, catégorisées et stockées.  
5. **Assistance utilisateur** – Octopuzzle affiche les pièces détectées et propose des correspondances basées sur la forme des tabs. *(L’annotation automatique sur les photos et la visualisation de la grille cible sont en cours de conception.)*  
6. **Validation** – l’utilisateur confirme ou rejette chaque suggestion ; Octopuzzle conserve l’historique, marque les pièces utilisées et prépare la proposition suivante. *(Une simulation visuelle du placement dans la grille est prévue pour une version ultérieure.)*

## Installation rapide

```bash
python -m venv .venv
source .venv/bin/activate   # ou .\.venv\Scripts\activate sur Windows
pip install opencv-python numpy pillow
```

## Lancer Octopuzzle

```bash
python octopuzzle.py
```

ou, sous Windows :

```bash
run_octopuzzle.bat
```

## Jeu d’essai

Le dossier `test/` contient un exemple de « trou » et des photos de pièces utilisées pour les expérimentations en cours. Ils permettent de vérifier rapidement la détection et les propositions.

## Structure du projet

- `octopuzzle.py` – application principale en 3 étapes (calibration, pièces disponibles, suggestions)
- `models.py` – détection des pièces, matching et moteur de résolution
- `widgets.py` – widgets personnalisés (canvas interactif, panneaux d’images, barre de stats)
- `image_utils.py` – conversions OpenCV ↔ PIL ↔ interface graphique, mise en cache, visualisations
- `assets/` – ressources (icônes) et script `generate_icon.py`
- `docs/` – notes techniques (`hole_detection.md`) et journal (`progress.md`)
- `test/` – images d’exemple

## Fonctionnalités actuelles

- Charge les photos du trou et des pièces, avec calibration optionnelle (ROI, fond, surface min/max)
- Analyse en direct de la zone à combler (double ROI, estimation de la grille manquante, mode debug multi-couches)
- Détection de pièces via OpenCV (seuillage adaptatif + morphologie) et classification heuristique des tabs
- Interface unifiée native avec thème moderne, boutons lisibles et panneaux de comparaison
- Système de suggestions basé sur la compatibilité des tabs et sur la taille normalisée des pièces
- Gestion de l’état : pièces utilisées, rejets, progression globale

## Vision produit

- Annotation directe sur les photos pour indiquer les candidats (numérotation s’il y a plusieurs options)
- Affichage de la grille du trou avec simulation visuelle des pièces validées
- Prise en compte de la sélection manuelle d’une pièce pour générer la liste de candidats la plus fiable
- Sauvegarde/reprise de session et meilleure autonomie (détection robuste sans calibration manuelle)
- Amélioration de l’algorithme de matching (analyse couleur/texture locale, scoring multi-critères)

## État actuel

La version historique web (Eel) a été retirée : Octopuzzle fonctionne exclusivement via cette interface native.  
Certaines fonctionnalités majeures restent à développer (notamment la simulation de placement dans la grille et la génération d’annotations multiples sur les photos des pièces). Consultez `TODO.md` pour l’état d’avancement détaillé.
