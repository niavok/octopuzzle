# TODO Octopuzzle

## Interface & UX

- [x] Renommer l’application en Octopuzzle et moderniser le thème (couleurs, états disabled lisibles)
- [ ] Afficher la grille du trou et permettre de sélectionner/visualiser la case à remplir
- [ ] Annoter directement les pièces candidates sur les photos des stocks (numérotation si plusieurs options)
- [ ] Ajouter une vue listant toutes les suggestions triées par confiance pour faciliter un choix manuel
- [ ] Simuler visuellement l’insertion d’une pièce validée dans la grille (overlay, position précise, rotation)
- [ ] Mémoriser visuellement les pièces déjà utilisées (badge, opacité réduite, tag dans les panneaux)
- [ ] Fournir un raccourci pour recharger rapidement les lots « trou + pièces » d’une session précédente

## Matching & Algorithmes

- [x] Uniformiser les identifiants des pièces (évite les collisions puzzle/stock)
- [ ] Calculer un score multi-critères (forme + couleur/texture locale) pour améliorer la fiabilité des suggestions
- [ ] Tirer parti du voisinage (nombre de pièces adjacentes connues) pour prioriser les zones les plus simples
- [ ] Permettre à l’utilisateur de choisir la pièce qu’il souhaite tester et proposer les meilleurs emplacements compatibles
- [ ] Gérer plusieurs propositions simultanées : annotation numérotée sur les images + panneau récapitulatif
- [ ] Enregistrer une trace de décision (pièce proposée, validée/rejetée, score) pour affiner les heuristiques

## Détection & Calibration

- [ ] Évaluer/ajuster l’heuristique de détection des tabs sur le jeu d’images `test/`
- [ ] Améliorer le filtrage des contours (bruit/échos lumineux) sans dépendre d’une ROI manuelle
- [ ] Mettre en place un assistant de calibration automatique (estimation des limites min/max area)
- [ ] Ajouter des métriques de qualité de détection (rapport pièces détectées / attendues) pour guider l’utilisateur

## Persistance & Outils

- [ ] Sauvegarder/recharger une session (calibration, pièces détectées, état du solver)
- [ ] Fournir un export léger (JSON) des pièces détectées pour analyse hors ligne
- [ ] Mettre en place des tests de non-régression visuels en utilisant le dossier `test/`
- [ ] Documenter un workflow de benchmark (avant/après une amélioration d’algorithme)
