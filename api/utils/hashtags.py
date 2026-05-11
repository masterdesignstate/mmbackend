"""Hashtag extraction for feed posts.

Hashtags are visual-only for now; we still persist them so we can later add
hashtag landing pages without re-parsing every body.
"""
import re

# Match #word — letters (any unicode), digits, underscore, hyphen. 1–64 chars.
_HASHTAG_RE = re.compile(r'#([\w-]{1,64})', re.UNICODE)
_MAX_TAGS = 30


def extract_hashtags(body: str) -> list[str]:
    """Return a list of unique lowercase hashtag slugs (no leading '#') from body.

    De-duplicates while preserving first-seen order. Capped at _MAX_TAGS.
    """
    if not body:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _HASHTAG_RE.finditer(body):
        tag = match.group(1).lower()
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= _MAX_TAGS:
            break
    return out
