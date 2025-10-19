"""
Word filtering utility to check for restricted words in user-generated content.
"""
import re
from typing import Tuple, List
from django.core.cache import cache
from django.utils import timezone


def get_restricted_words() -> set:
    """
    Get active restricted words from database with caching.
    Cache is refreshed every 5 minutes.

    Returns:
        set: Set of lowercase restricted words
    """
    cache_key = 'restricted_words_set'
    cached_words = cache.get(cache_key)

    if cached_words is not None:
        return cached_words

    # Import here to avoid circular imports
    from api.models import RestrictedWord

    # Fetch active restricted words from database
    words = set(
        RestrictedWord.objects.filter(is_active=True)
        .values_list('word', flat=True)
    )

    # Cache for 5 minutes (300 seconds)
    cache.set(cache_key, words, 300)

    return words


def contains_restricted_words(text: str) -> Tuple[bool, List[str]]:
    """
    Check if text contains any restricted words.

    Uses word boundaries to match whole words only, preventing false positives.
    For example, "assassin" won't match the restricted word "ass".

    Args:
        text: The text to check for restricted words

    Returns:
        Tuple containing:
            - bool: True if restricted words found, False otherwise
            - List[str]: List of found restricted words
    """
    if not text:
        return False, []

    # Get restricted words
    restricted_words = get_restricted_words()

    if not restricted_words:
        return False, []

    # Convert text to lowercase for case-insensitive matching
    text_lower = text.lower()

    # Replace underscores and hyphens with spaces to catch words in usernames like "john_crypto_doe"
    # This way "john_crypto_doe" becomes "john crypto doe" for checking
    text_normalized = text_lower.replace('_', ' ').replace('-', ' ')

    # Find all restricted words in the text
    found_words = []

    for word in restricted_words:
        # Use word boundaries (\b) to match whole words only
        # This prevents "assassin" from matching "ass"
        pattern = r'\b' + re.escape(word) + r'\b'

        # Check both original and normalized text
        if re.search(pattern, text_lower) or re.search(pattern, text_normalized):
            found_words.append(word)

    return len(found_words) > 0, found_words


def validate_text_fields(**fields) -> Tuple[bool, List[str]]:
    """
    Validate multiple text fields for restricted words.

    Args:
        **fields: Keyword arguments where key is field name and value is field text

    Returns:
        Tuple containing:
            - bool: True if any field contains restricted words
            - List[str]: List of all found restricted words across all fields

    Example:
        has_restricted, words = validate_text_fields(
            username="john_doe",
            bio="I love coding",
            tagline="Software engineer"
        )
    """
    all_found_words = []

    for field_name, field_value in fields.items():
        if field_value:
            has_restricted, found_words = contains_restricted_words(str(field_value))
            if has_restricted:
                all_found_words.extend(found_words)

    # Remove duplicates while preserving order
    unique_words = list(dict.fromkeys(all_found_words))

    return len(unique_words) > 0, unique_words


def clear_restricted_words_cache():
    """
    Clear the restricted words cache.
    Useful after adding/removing/updating restricted words in the database.
    """
    cache.delete('restricted_words_set')
