# Journal des modifications

Les changements notables de ce projet sont consignés ici. Le format suit
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet utilise le [versionnement sémantique](https://semver.org/lang/fr/).

## [0.2.1][0.2.1] - 2026-11-10

### Corrigé

- **Types de lignes étendus** (702 express, 705 nuit, 711 navette, 713 scolaire, 714 substitution)
  classés par famille au lieu de « autre » ; le détail par code reste dans le manifeste.
- **Emprise de contrôle** élargie à tout le réseau SYTRAL : les 581 arrêts scolaires de la Loire
  n'étaient pas des anomalies.
- **Jour de référence de l'exploration** : le mardi ou jeudi où le plus de lignes de métro,
  tramway et funiculaire circulent. Le premier mardi tombait pendant la fermeture du métro C.

### Ajouté

- Lignes de métro, tramway et funiculaire à l'arrêt le jour même, dans l'exploration.
- Nombre d'arrêts situés dans la métropole dans le manifeste (`stops_in_metropole`).
- Note d'exploration du GTFS TCL : `docs/exploration-gtfs.md`.
- Test d'intégration : les quatre lignes de métro circulent le jour de référence.

## [0.2.0][0.2.0] - 2026-11-10

### Ajouté

- **GTFS TCL** : téléchargement des horaires théoriques du réseau TCL depuis data.grandlyon.com
  (authentification HTTP Basic, Licence Mobilités), écriture atomique, extraction sécurisée et
  manifeste (empreinte SHA-256, période de validité, comptages par mode, alertes qualité).
  Le fichier reste en local et n'est pas republié.
- **Exploration DuckDB du GTFS** : lignes par mode, courses par jour (jours fériés compris),
  intervalle moyen entre deux départs en heure de pointe, stations les plus desservies.
- Test d'intégration sur le vrai GTFS (validité en cours, présence du métro, du tramway, du
  funiculaire et des bus, fréquence du métro en pointe).

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

[0.2.1]: https://github.com/Kevynflrs/lyon-bas-carbone/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Kevynflrs/lyon-bas-carbone/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Kevynflrs/lyon-bas-carbone/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Kevynflrs/lyon-bas-carbone/releases/tag/v0.1.0
