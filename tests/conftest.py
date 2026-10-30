"""Données GBFS d'exemple (versions 2.3 et 3.0) partagées par les tests."""

import pandas as pd

NOW = pd.Timestamp("2026-10-29T13:00:42Z")

GBFS_V2 = {
    "version": "2.3",
    "data": {
        "fr": {
            "feeds": [
                {"name": "station_information", "url": "https://example.test/v2/station_information.json"},
                {"name": "station_status", "url": "https://example.test/v2/station_status.json"},
            ]
        }
    },
}

GBFS_V3 = {
    "version": "3.0",
    "data": {
        "feeds": [
            {"name": "station_information", "url": "https://example.test/v3/station_information.json"},
            {"name": "station_status", "url": "https://example.test/v3/station_status.json"},
        ]
    },
}

# GBFS 2.3 : horodatages en secondes POSIX, booléens en 0/1.
STATUS_V2 = {
    "version": "2.3",
    "data": {
        "stations": [
            {
                "station_id": "2010",
                "num_bikes_available": 7,
                "num_docks_available": 13,
                "is_installed": 1,
                "is_renting": 1,
                "is_returning": 1,
                "last_reported": 1793278750,
            },
            {
                "station_id": "7024",
                "num_bikes_available": 0,
                "num_docks_available": 20,
                "is_installed": 1,
                "is_renting": 1,
                "is_returning": 1,
                "last_reported": 1793278700,
            },
            {
                "station_id": "3082",
                "num_bikes_available": 3,
                "num_docks_available": 0,
                "is_installed": 1,
                "is_renting": 0,
                "is_returning": 0,
                "last_reported": 1793276000,
            },
        ]
    },
}

# GBFS 3.0 : horodatages ISO 8601 (avec fuseau), num_vehicles_available.
STATUS_V3 = {
    "version": "3.0",
    "data": {
        "stations": [
            {
                "station_id": "2010",
                "num_vehicles_available": 7,
                "num_docks_available": 13,
                "is_installed": True,
                "is_renting": True,
                "is_returning": True,
                "last_reported": "2026-10-29T13:59:10+01:00",
                "vehicle_types_available": [
                    {"vehicle_type_id": "mechanical", "count": 5},
                    {"vehicle_type_id": "electric", "count": 2},
                ],
            },
            {
                "station_id": "7024",
                "num_vehicles_available": 0,
                "num_docks_available": 20,
                "is_installed": True,
                "is_renting": True,
                "is_returning": True,
                "last_reported": "2026-10-29T12:58:20Z",
            },
        ]
    },
}

INFORMATION_V3 = {
    "version": "3.0",
    "data": {
        "stations": [
            {
                "station_id": "2010",
                "name": [{"text": "Exemple Station A", "language": "fr"}],
                "lat": 45.7578,
                "lon": 4.8320,
                "capacity": 20,
                "address": "1 rue Exemple",
            },
            {
                "station_id": "7024",
                "name": [
                    {"text": "Example Station B", "language": "en"},
                    {"text": "Exemple Station B", "language": "fr"},
                ],
                "lat": 45.7485,
                "lon": 4.8467,
                "capacity": 20,
            },
        ]
    },
}
