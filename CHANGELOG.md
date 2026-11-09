
# Journal des modifications

Les changements notables de ce projet sont consignés ici. Le format suit
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet utilise le [versionnement sémantique](https://semver.org/lang/fr/).

## [0.1.1][0.1.1] - 2026-11-09

### Corrigé

- **Fréquence de collecte** : le cron de GitHub Actions ne déclenchait que 4 à 5 collectes
  par jour au lieu de 96 (exécutions retardées ou abandonnées en cas de forte charge). La
  collecte est désormais déclenchée toutes les 15 minutes par un planificateur externe
  (cron-job.org) via l'API GitHub, avec une collecte horaire de secours par le cron GitHub.

### Ajouté

- **Couverture quotidienne** : la compaction calcule la part des 96 collectes attendues
  réellement présentes, l'inscrit dans le message de commit et la signale sous 90 %.
- **Numéro de version** affiché dans le pied de page du site, avec un lien vers les releases.
- Ce journal des modifications.

## [0.1.0][0.1.0] - 2026-10-30

Première version publique.

### Ajouté

- Collecte des disponibilités Vélo'v (GBFS 2.3 et 3.0), historisée en Parquet sur Hugging Face.
- Compaction quotidienne des fichiers et référentiel des stations.
- Contrôles qualité : coordonnées (0, 0) et stations hors de la métropole.
- Site React + TypeScript + Tailwind CSS + Leaflet sur GitHub Pages.
- CI/CD : tests unitaires, tests d'intégration sur staging, smoke test et déploiement sur `main`.
- Licence MIT, conventions de branches et de commits.

[0.1.1]: https://github.com/Kevynflrs/lyon-bas-carbone/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Kevynflrs/lyon-bas-carbone/releases/tag/v0.1.0
