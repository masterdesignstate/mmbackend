"""
The Results filter payload, as stored in User.results_filters and SavedResultFilter.filters.

Mirrors `DEFAULT_RESULTS_FILTERS` in mmfrontend/src/app/results/page.tsx.
"""

COMPATIBILITY_TYPES = ('overall', 'compatible_with_me', 'im_compatible_with')
REQUIRED_SCOPES = ('my', 'their')
KNOWN_TAGS = frozenset({
    'Approved', 'Approved Me', 'Not Approved', 'Liked', 'Liked Me',
    'Matched', 'Hot', 'Maybe', 'Saved', 'Hide',
    'Required', 'Pending', 'Their Required', 'Their Pending',
})
RANGE_BOUNDS = {
    'compatibility': (0, 100),
    'distance': (1, 100),
    'age': (18, 80),
}


def _clean_range(name, value):
    low, high = RANGE_BOUNDS[name]
    if not isinstance(value, dict):
        raise ValueError(f'{name} must be an object with min and max')
    try:
        lo = int(value.get('min', low))
        hi = int(value.get('max', high))
    except (TypeError, ValueError):
        raise ValueError(f'{name} min and max must be numbers')
    if not (low <= lo <= hi <= high):
        raise ValueError(f'{name} must satisfy {low} <= min <= max <= {high}')
    return {'min': lo, 'max': hi}


def clean_results_filters(value):
    """Return a normalised copy of a filter payload, or raise ValueError.

    An empty object means "defaults" and is kept as-is.
    """
    if value in (None, ''):
        return {}
    if not isinstance(value, dict):
        raise ValueError('filters must be an object')
    if not value:
        return {}

    cleaned = {}
    compatibility_type = value.get('compatibilityType', 'overall')
    if compatibility_type not in COMPATIBILITY_TYPES:
        raise ValueError(f'compatibilityType must be one of {", ".join(COMPATIBILITY_TYPES)}')
    cleaned['compatibilityType'] = compatibility_type

    for name in RANGE_BOUNDS:
        if name in value:
            cleaned[name] = _clean_range(name, value[name])
        else:
            low, high = RANGE_BOUNDS[name]
            cleaned[name] = {'min': low, 'max': high}

    tags = value.get('tags', [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError('tags must be a list of strings')
    unknown = [tag for tag in tags if tag not in KNOWN_TAGS]
    if unknown:
        raise ValueError(f'Unknown tags: {", ".join(unknown)}')
    cleaned['tags'] = list(dict.fromkeys(tags))

    required_only = value.get('requiredOnly', False)
    if not isinstance(required_only, bool):
        raise ValueError('requiredOnly must be true or false')
    cleaned['requiredOnly'] = required_only

    required_scope = value.get('requiredScope', 'my')
    if required_scope not in REQUIRED_SCOPES:
        raise ValueError('requiredScope must be "my" or "their"')
    cleaned['requiredScope'] = required_scope

    return cleaned
