# Octopuzzle – Journal de progression

## État (session en cours)
- **Infrastructure UI** : Étape 1 refondue (double ROI, affichage temps réel, mode debug couches multiples, curseur croix, stat pièces persistante).
- **Analyses automatiques** : adaptation dynamique des seuils Canny pour les bords et les lignes internes, masque d’ombre pour réduire les textures homogènes, couleur moyenne stockée automatiquement.
- **Visualisation** : surbrillance renforcée des ROI, grille plus visible, combo debug avec `Contours (bord)`, `Edges anneau`, `Contours internes`, `Masque ombre`, `Grille estimée`.
- **Détection puzzle-hole** : fiable sur bord principal mais encore sensible aux nervures/bois (faux positifs du masque interne). La grille peut remonter le long du puzzle fini si la ROI interne touche sa bordure.

## Observations tests
- `test/` (bord en bois) : contour externe OK ; la colonne de bois sombre peut être interprétée comme séparation -> faux segment vertical.
- Puzzle partiellement complété : si la ROI interne mord sur la partie déjà assemblée, Canny/Hough récupèrent le joint périphérique -> lignes non désirées.

## Prochaines actions suggérées
1. **Raffiner la ROI externe** : auto-ajustement (snap) sur le contour détecté, voire remplacement complet de la sélection manuelle.
2. **Détection concavitée / grille** : analyser la forme du trou pour détecter coins concaves et contraindre la grille rectangulaire proposée.
3. **Filtre texture interne** : identifier et ignorer les lignes parallèles persistantes (ex. nervure de table) via densité/variation longitudinale.
4. **Feedback visuel** : ajout d’un indicateur « qualité de détection » (ex. ratio lignes détectées / zone analysée) pour aider l’utilisateur à recadrer ses ROI.
5. **Étape 2** : intégrer la couleur moyenne du trou comme signal pour filtrer les pièces disponibles (matching couleur de fond).

## Notes de reprise
- Cf. `docs/hole_detection.md` pour le pipeline mis en place.
- Les paramétrages de seuils dépendent encore fortement de la luminosité : prévoir un ajustement automatique (ex. CLAHE) ou une normalisation couleur pour stabiliser.
- TODO mis à jour (détection concavités, stabilisation ROI auto, suivi des faux positifs). EOF
