
# Exploration du GTFS TCL (10 novembre 2026)

Première lecture du GTFS « Horaires théoriques du réseau Transports en Commun Lyonnais »
(SYTRAL Mobilités, Licence Mobilités), téléchargé le 10/11/2026 avec `python -m pipeline.ingest.gtfs`
et exploré avec `python -m pipeline.explore.gtfs` (DuckDB). Ce document fixe ce que contient le
fichier et ce que cela implique pour le comparateur de trajets (V1).

## Ce que contient le fichier

| Élément                      | Valeur                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Taille du ZIP                  | 21,2 Mo, 9 fichiers (dont `feed_info.txt` et `transfers.txt`)              |
| Période de validité          | du 10/11/2026 au 10/03/2027 (4 mois, et non 60 jours comme l'indique la fiche) |
| Arrêts (`location_type` 0)  | 9 766                                                                          |
| Stations (`location_type` 1) | 4 246                                                                          |
| Lignes                         | 804                                                                            |
| Courses                        | 141 875                                                                        |
| Horaires (`stop_times`)      | 2 955 338                                                                      |

### Le « réseau TCL » est en fait tout le réseau SYTRAL Mobilités

Le fichier ne se limite pas aux lignes urbaines lyonnaises :

| Famille          | Lignes | `route_type`                                         | Exemples                                                                                             |
| ---------------- | ------ | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Bus              | 784    | 3 (176), 702 (2), 705 (4), 711 (5), 713 (593), 714 (4) | 102, C3… ; express TB11 ; nuit PL1 à PL4 ; navettes N181… ; scolaires JD3xx ; substitution BRT4… |
| Tramway          | 8      | 0                                                      | T1 à T7, RX (Rhônexpress)                                                                          |
| Trolleybus       | 5      | 11                                                     | C1, C2, C13, C14, C18                                                                                |
| Métro           | 4      | 1                                                      | A, B, C, D                                                                                           |
| Funiculaire      | 2      | 7                                                      | F1, F2                                                                                               |
| Navette fluviale | 1      | 4                                                      | NAVI1                                                                                                |

Les 593 lignes `JD3xx` (`route_type` 713, bus scolaires) représentent les trois quarts des lignes.
Elles desservent aussi des communes hors du Rhône : 581 arrêts sont à Charlieu, au Coteau
(Loire)… Ce ne sont pas des erreurs de coordonnées.

Plusieurs lignes utilisent des **types de lignes étendus** (702, 705, 711, 713, 714), que la
première version du script ne savait pas classer. Ils sont désormais regroupés par famille, et le
détail par code est conservé dans `manifest.json` (`routes_by_route_type`).

## Jours de service

| Jour                            | Courses          |
| ------------------------------- | ---------------- |
| Jour ouvré (lundi à vendredi) | 21 850 à 22 342 |
| Samedi                          | 14 114 à 14 420 |
| Dimanche                        | 8 851 à 9 018   |
| Mercredi 11 novembre (férié)  | 9 107            |

Le jour férié est bien traité comme un dimanche : les services de semaine sont retirés par
`calendar_dates.txt` (exception de type 2) et remplacés par les services du dimanche (type 1).

## Fréquences en heure de pointe (7 h - 9 h, mardi 10/11/2026)

Intervalle moyen entre deux départs du terminus :

| Ligne          | Intervalle (min) | Ligne             | Intervalle (min) |
| -------------- | ---------------- | ----------------- | ---------------- |
| Métro D       | 1,8              | Tram T2           | 4,1 à 4,4       |
| Métro B       | 2,1 à 2,3       | Tram T1           | 5,0 à 5,7       |
| Métro A       | 2,9              | Tram T3           | 5,5              |
| Funiculaire F2 | 5,5              | Tram T4           | 6,0              |
| Funiculaire F1 | 6,0              | Tram T6           | 9,2 à 10,0      |
|                |                  | Tram T5           | 13,3             |
|                |                  | RX (Rhônexpress) | 15,0             |
|                |                  | Tram T7           | 17,1             |

Ces valeurs sont cohérentes avec l'offre réelle (le Rhônexpress est cadencé au quart d'heure),
ce qui valide le calcul des horaires, y compris ceux qui dépassent minuit (`25:10:00`).

## Stations les plus desservies (mardi 10/11/2026)

Gare Part-Dieu V. Merle (2 951 passages), Charpennes Charles Hernu (2 916), Gare de Vaise
(2 640), Saxe - Gambetta (2 526), Gorge de Loup (2 496). Les quais d'une même station sont
regroupés par leur station parente (`parent_station`).

## Anomalies et particularités

1. **Métro C fermé jusqu'au 15/11/2026.** Le fichier ne contient aucune course de la ligne C
   avant le lundi 16 novembre (332 courses ce jour-là), ce que confirme l'application TCL. La
   donnée est juste, mais le premier « jour de référence » choisi par le script (le premier
   mardi) tombait pendant la fermeture : une matrice de trajets calculée ce jour-là aurait ignoré
   une ligne de métro. Le jour de référence est désormais **le mardi ou jeudi des quatre semaines
   à venir où le plus de lignes de métro, tramway et funiculaire circulent**, et l'exploration
   liste les lignes structurantes à l'arrêt le jour même.
2. **Ligne nommée `106.`**, avec un point final, à côté de `106` et `106EX` : probable erreur de
   saisie côté producteur, gardée telle quelle dans les données brutes.
3. **Lignes à tarification ou statut particuliers** présentes dans le fichier : Rhônexpress (RX),
   navette fluviale (NAVI1), lignes scolaires (713), bus de substitution (714).

## Conséquences pour le comparateur (V1)

- **Périmètre** : ne garder que les arrêts de la métropole. Le manifeste compte désormais les
  arrêts situés dans l'emprise rectangulaire déjà utilisée pour Vélo'v (`stops_in_metropole`) ;
  un filtre exact sur le contour de la métropole viendra avec les points de référence (étape 3).
- **Lignes retenues** : décider explicitement du sort des lignes scolaires, du Rhônexpress (tarif
  spécifique) et de la navette fluviale, et le documenter dans la méthodologie.
- **Date de calcul** : calculer la matrice de trajets sur le jour de référence représentatif,
  jamais sur une date fixe, et vérifier que les quatre lignes de métro circulent ce jour-là
  (contrôle ajouté au test d'intégration).
- **Fraîcheur** : le fichier couvre quatre mois ; le retélécharger avant chaque calcul suffit.
