#!/usr/bin/env python
"""
Clear the compatibility calculation cache.

Run this BEFORE running calculate_all_compatibilities --force to ensure
fresh calculations without cached data.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.core.cache import cache
from api.models import Compatibility

def clear_compatibility_cache():
    """Clear all compatibility-related cache entries"""

    print("🧹 Clearing compatibility calculation cache...\n")

    # Get all compatibility records to build cache keys
    compatibilities = Compatibility.objects.all().values('user1_id', 'user2_id')

    cleared_count = 0

    for comp in compatibilities:
        user1_id = comp['user1_id']
        user2_id = comp['user2_id']

        # Build cache keys (same logic as in CompatibilityService)
        min_id = min(user1_id, user2_id)
        max_id = max(user1_id, user2_id)

        # Clear all variants of the cache key
        cache_keys = [
            f"compatibility_{min_id}_{max_id}",
            f"compatibility_{min_id}_{max_id}_required",
            f"compatibility_{min_id}_{max_id}_exclude_required",
        ]

        for key in cache_keys:
            if cache.delete(key):
                cleared_count += 1

    print(f"✅ Cleared {cleared_count} cache entries\n")
    print("📝 You can now run: python manage.py calculate_all_compatibilities --force")
    print("   to ensure all calculations use the latest code.\n")


if __name__ == '__main__':
    clear_compatibility_cache()
