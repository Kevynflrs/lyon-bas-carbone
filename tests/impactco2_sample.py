from __future__ import annotations

# identifiant : (nom renvoyé par l'API, usage kg/km, construction kg/km)
ECV = {
    4: ("Voiture thermique", 0.1105577600556303, 0.03169565217391306),
    5: ("Voiture électrique", 0.01208836005563031, 0.05527690217391306),
    9: ("Bus thermique", 0.1135, 0.00892),
    16: ("Bus électrique", 0.0095, 0.0122),
    10: ("Tramway", 0.0038, 0.00048),
    11: ("Métro", 0.0042, 0.00024),
    7: ("Vélo mécanique", 0.0, 0.00017),
    8: ("Vélo à assistance électrique", 0.00223, 0.00872),
    30: ("Marche", 0.0, 0.0),
}


def api_response(include_construction: bool, km: float = 1, drop: int | None = None) -> dict:
    data = []
    for impactco2_id, (name, usage, construction) in ECV.items():
        if impactco2_id != drop:
            value = (usage + (construction if include_construction else 0)) * km
            data.append({"id": impactco2_id, "name": name, "value": value})
    return {
        "data": data,
        "warning": "La requete n'est pas authentifiée. Nous nous reservons le droit de couper cette API.",
    }
