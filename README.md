# Puzzle Solver (Tkinter)

Application de détection et d'assistance à l'assemblage de puzzle, réalisée en Python + Tkinter.

## Installation

```bash
pip install opencv-python numpy pillow
```

## Lancement

```bash
python puzzle_solver_tk.py
```

ou sous Windows :

```bash
run_tkinter.bat
```

## Structure

- `puzzle_solver_tk.py` – application Tkinter en 3 étapes (calibration, pièces disponibles, résolution)
- `models.py` – détection des pièces, matching et moteur de résolution
- `widgets.py` – widgets Tkinter personnalisés (canvas interactif, panneaux d'images, statistiques)
- `image_utils.py` – utilitaires OpenCV ↔ PIL/Tkinter et mise en cache

> La précédente version web (Eel) a été retirée : toutes les fonctionnalités sont désormais réunies dans l'interface Tkinter.
