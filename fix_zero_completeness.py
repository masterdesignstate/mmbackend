#!/usr/bin/env python
"""
Efficiently fix compatibility records that have 0 completeness values.
Uses optimized queries with prefetch_related to avoid N+1 queries.
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from api.models import Compatibility, UserAnswer, UserRequiredQuestion
from django.db.models import Q


def fix_zero_completeness():
    """Fix records with 0 completeness using per-user UserRequiredQuestion."""

    # Find records with 0 completeness
    records_to_fix = Compatibility.objects.filter(
        Q(user1_required_completeness=0) | Q(user2_required_completeness=0)
    ).select_related('user1', 'user2')

    count = records_to_fix.count()
    print(f"📦 Records to fix: {count}\n")

    if count == 0:
        print("✅ All records already have completeness calculated!")
        return

    # Build caches: per-user required question IDs (from UserRequiredQuestion) and answered question IDs
    print("🔄 Building cache of user required and answered questions...")
    user_required_answers = {}
    user_answered_qids = {}

    user_ids = set()
    for comp in records_to_fix:
        user_ids.add(comp.user1_id)
        user_ids.add(comp.user2_id)

    print(f"   Caching for {len(user_ids)} unique users...")

    # Per-user required: from UserRequiredQuestion
    for row in UserRequiredQuestion.objects.filter(user_id__in=user_ids).values('user_id', 'question_id'):
        user_required_answers.setdefault(row['user_id'], set()).add(row['question_id'])

    # All answered question IDs per user
    for row in UserAnswer.objects.filter(user_id__in=user_ids).values('user_id', 'question_id'):
        user_answered_qids.setdefault(row['user_id'], set()).add(row['question_id'])

    print(f"   ✅ Cache built\n")

    batch_size = 500
    updated = 0

    print(f"🔄 Processing {count} records in batches of {batch_size}...\n")

    for i in range(0, count, batch_size):
        batch = list(records_to_fix[i:i+batch_size])
        updates = []

        for comp in batch:
            try:
                # Per-user required: user1_required_completeness = % of user2's required that user1 answered
                user1_req = user_required_answers.get(comp.user1_id, set())
                user2_req = user_required_answers.get(comp.user2_id, set())
                user1_answered = user_answered_qids.get(comp.user1_id, set())
                user2_answered = user_answered_qids.get(comp.user2_id, set())

                user2_required_count = len(user2_req)
                user1_completeness = (len(user1_answered & user2_req) / user2_required_count) if user2_required_count > 0 else 0.0
                user1_required_count = len(user1_req)
                user2_completeness = (len(user2_answered & user1_req) / user1_required_count) if user1_required_count > 0 else 0.0

                user1_completeness = max(0.0, min(1.0, user1_completeness))
                user2_completeness = max(0.0, min(1.0, user2_completeness))

                # Update fields
                comp.user1_required_completeness = Decimal(str(round(user1_completeness, 3)))
                comp.user2_required_completeness = Decimal(str(round(user2_completeness, 3)))

                updates.append(comp)
                updated += 1

            except Exception as e:
                print(f"   ❌ Error: {comp.user1.username} <-> {comp.user2.username}: {e}")

        # Bulk update
        if updates:
            Compatibility.objects.bulk_update(
                updates,
                fields=['user1_required_completeness', 'user2_required_completeness']
            )
            print(f"   ✅ Batch {i//batch_size + 1}/{(count + batch_size - 1)//batch_size}: Updated {len(updates)} records")

    print(f"\n✅ Update complete! Fixed {updated} records")

    # Verify
    remaining = Compatibility.objects.filter(
        Q(user1_required_completeness=0) | Q(user2_required_completeness=0)
    ).count()

    print(f"\n📊 Final status:")
    print(f"   Records still with 0 completeness: {remaining}")
    print(f"   Records fixed: {count - remaining}")


if __name__ == '__main__':
    fix_zero_completeness()
