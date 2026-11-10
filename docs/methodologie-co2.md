
# Méthodologie CO2

Comment le comparateur calcule les émissions d'un trajet, avec quelles données et quelles
limites. Le but est un outil crédible, pas militant : les hypothèses sont explicites, et le
résultat est montré tel quel, y compris quand le vélo ou la marche font mieux que les transports
en commun.

## Le calcul

Pour un trajet donné et chaque mode :

    émissions (gCO2e) = distance parcourue avec ce mode (km) × facteur d'émission du mode (gCO2e/km)
    CO2 évité         = émissions en voiture − émissions avec le mode choisi

- La **distance** est celle réellement parcourue par chaque mode (itinéraire calculé sur le
  réseau, étape 4), pas la distance à vol d'oiseau : un trajet en tram fait souvent un détour.
- Le **facteur** est une moyenne par personne et par km, en équivalent CO2, sur le cycle de vie
  du véhicule (usage + construction).

## Les facteurs d'émission

Source : API Impact CO2 de l'ADEME, récupérée une fois avec
`python -m pipeline.ingest.emission_factors` et versionnée dans
[`reference/emission_factors.csv`](../reference/emission_factors.csv). Le site lit ce fichier, jamais
l'API en direct. Valeurs au 10/11/2026 :

| Mode                            | Total (gCO2e/km) |  Usage | Construction | Source sous-jacente                                              |
| ------------------------------- | ---------------: | -----: | -----------: | ---------------------------------------------------------------- |
| Voiture thermique               |           142,25 | 110,56 |        31,70 | ADEME, modélisation de l'empreinte carbone de la voiture (2025) |
| Bus thermique                   |           122,42 | 113,50 |         8,92 | Base Empreinte ADEME                                             |
| Voiture électrique             |            67,37 |  12,09 |        55,28 | ADEME, modélisation de l'empreinte carbone de la voiture (2025) |
| Bus électrique                 |            21,70 |   9,50 |        12,20 | Base Empreinte ADEME                                             |
| Vélo à assistance électrique |            10,95 |   2,23 |         8,72 | Base Empreinte ADEME                                             |
| Métro                          |             4,44 |   4,20 |         0,24 | Base Empreinte ADEME                                             |
| Tramway                         |             4,28 |   3,80 |         0,48 | Base Empreinte ADEME                                             |
| Vélo mécanique                |             0,17 |      0 |         0,17 | Base Empreinte ADEME                                             |
| Marche                          |                0 |      0 |            0 | convention (aucun véhicule)                                     |

Pour la voiture, le facteur est celui du véhicule : avec une seule personne à bord, c'est aussi
le facteur par personne. Pour les transports en commun, c'est une moyenne par voyageur, qui intègre
donc un taux de remplissage moyen national.

Ces valeurs ont été vérifiées de deux façons : par l'API elle-même, et dans le code source
d'Impact CO2 (dépôt `incubateur-ademe/impactco2`, licence MIT), dont les valeurs précalculées
donnent les mêmes totaux.

## Hypothèses retenues (modifiables)

1. **Construction incluse.** Sans elle, le vélo vaudrait 0 et la voiture électrique serait très
   sous-estimée (la fabrication représente 82 % de son facteur, et 80 % de celui du vélo à
   assistance électrique). Le CSV garde le détail usage / construction pour pouvoir montrer les
   deux.
2. **Voiture : conducteur seul par défaut**, parce que c'est le cas le plus courant pour les
   déplacements du quotidien. Le covoiturage se calcule en divisant le facteur de la voiture par le
   nombre d'occupants, comme le fait Impact CO2 ; le site pourra proposer ce réglage.
3. **Voiture thermique comme référence** du « CO2 évité ». Impact CO2 la définit comme une voiture
   moyenne diesel. La voiture électrique est affichée à côté, pour ne pas surestimer le gain.
4. **Facteurs nationaux** : il n'existe pas de facteurs publiés propres au réseau lyonnais. Pour
   le métro et le tramway, à traction électrique, le mix électrique est le même partout en France ;
   l'écart vient surtout du taux de remplissage, inconnu pour Lyon.

## Correspondance entre le GTFS TCL et les facteurs

Les familles de lignes viennent du classement des `route_type` du GTFS
(voir [exploration-gtfs.md](exploration-gtfs.md)).

| Famille GTFS                            | Facteur utilisé               | Commentaire                                                           |
| --------------------------------------- | ------------------------------ | --------------------------------------------------------------------- |
| Métro (A, B, C, D)                     | `metro`                      |                                                                       |
| Tramway (T1 à T7, RX)                  | `tramway`                    | le Rhônexpress est un tramway                                        |
| Funiculaire (F1, F2)                    | `tramway`                    | approximation : traction électrique sur rail, pas de facteur dédié |
| Trolleybus (C1, C2, C13, C14, C18)      | `bus_electrique`             | traction électrique par caténaire                                   |
| Bus (y compris express, nuit, navettes) | `bus_thermique`              | hypothèse prudente, voir les limites                                 |
| Navette fluviale (NAVI1)                | exclue                         | pas de facteur adapté, ligne marginale                               |
| Vélo'v mécanique / électrique        | `velo` / `velo_electrique` | voir les limites                                                      |
| Marche                                  | `marche`                     |                                                                       |

Choix à confirmer : les lignes scolaires (`route_type` 713) sont exclues du comparateur, car elles
sont conçues pour les trajets scolaires et non pour un déplacement quelconque.

## Limites connues

- **Bus TCL** : le parc mélange des véhicules de motorisations différentes, mais sa composition
  ligne par ligne n'est pas dans le GTFS. Le facteur « bus thermique » surestime probablement les
  émissions des lignes équipées de bus électriques. À affiner si la composition du parc est publiée.
- **Vélo'v** : le facteur du vélo personnel ne compte ni les stations, ni le rééquilibrage des
  vélos par camion. Le code d'Impact CO2 contient des valeurs pour le vélo en libre-service, mais
  elles y sont désactivées : elles ne sont donc pas utilisées ici, et la limite est signalée.
- **Moyenne et effet marginal** : un tram circule qu'on y monte ou non ; l'émission
  supplémentaire due à un voyageur de plus est presque nulle. On utilise pourtant la moyenne par
  voyageur, convention de l'ADEME, qui reflète la part du service attribuable à chacun.
- **Voiture** : pas d'embouteillages, ni de recherche de place, ni de détour ; la consommation
  réelle en ville est sans doute plus élevée que la moyenne utilisée.
- **Accès aux arrêts** : la marche jusqu'à l'arrêt compte pour 0 gCO2e, mais son temps est compté
  dans la comparaison des durées.

## Mise à jour

    python -m pipeline.ingest.emission_factors           # réécrit reference/emission_factors.csv
    python -m pipeline.ingest.emission_factors --check   # compare sans écrire

Le test d'intégration `tests/integration/test_emission_factors_live.py` échoue si l'ADEME modifie
ses facteurs : on relance alors la commande, on relit ce document, puis on commite le CSV.

## Sources

- API Impact CO2 (ADEME) : `https://impactco2.fr/api/v1/transport`, documentation sur
  impactco2.fr/doc/api, clé gratuite sur demande.
- Code source d'Impact CO2 : github.com/incubateur-ademe/impactco2 (licence MIT).
- Base Empreinte de l'ADEME : base-empreinte.ademe.fr.
- GTFS TCL : SYTRAL Mobilités, Licence Mobilités.
