"""Miles between the cities the app offers. Mirrors mmfrontend/src/utils/distance.ts."""

_ROWS = {
    "austin": {"cedar park": 21, "georgetown": 28, "hutto": 28, "kyle": 22, "leander": 27, "manor": 15, "pflugerville": 17, "round rock": 19, "san marcos": 32},
    "cedar park": {"austin": 21, "georgetown": 22, "hutto": 24, "kyle": 41, "leander": 6, "manor": 24, "pflugerville": 15, "round rock": 15, "san marcos": 51},
    "georgetown": {"austin": 28, "cedar park": 22, "hutto": 10, "kyle": 44, "leander": 20, "manor": 27, "pflugerville": 16, "round rock": 10, "san marcos": 57},
    "hutto": {"austin": 28, "cedar park": 24, "georgetown": 10, "kyle": 46, "leander": 20, "manor": 25, "pflugerville": 10, "round rock": 9, "san marcos": 64},
    "kyle": {"austin": 22, "cedar park": 41, "georgetown": 44, "hutto": 46, "leander": 48, "manor": 28, "pflugerville": 38, "round rock": 40, "san marcos": 21},
    "leander": {"austin": 27, "cedar park": 6, "georgetown": 20, "hutto": 20, "kyle": 48, "manor": 38, "pflugerville": 22, "round rock": 18, "san marcos": 58},
    "manor": {"austin": 15, "cedar park": 24, "georgetown": 27, "hutto": 25, "kyle": 28, "leander": 38, "pflugerville": 10, "round rock": 18, "san marcos": 40},
    "pflugerville": {"austin": 17, "cedar park": 15, "georgetown": 16, "hutto": 10, "kyle": 38, "leander": 22, "manor": 10, "round rock": 7, "san marcos": 48},
    "round rock": {"austin": 19, "cedar park": 15, "georgetown": 10, "hutto": 9, "kyle": 40, "leander": 18, "manor": 18, "pflugerville": 7, "san marcos": 55},
    "san marcos": {"austin": 32, "cedar park": 51, "georgetown": 57, "hutto": 64, "kyle": 21, "leander": 58, "manor": 40, "pflugerville": 48, "round rock": 55},
}


def distance_between(city_a, city_b):
    """Miles between two cities, 1 for the same city, or None when either is unknown."""
    if not city_a or not city_b:
        return None
    left = str(city_a).strip().lower()
    right = str(city_b).strip().lower()
    if left == right:
        return 1 if left in _ROWS else None
    return _ROWS.get(left, {}).get(right)
