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

from api.models import Compatibility, Question, UserAnswer
from django.db.models import Q, Prefetch


def fix_zero_completeness():
    """Fix records with 0 completeness using efficient queries"""

    # Get total required question count
    total_required_count = Question.objects.filter(is_required_for_match=True).count()
    print(f"📊 Total required questions: {total_required_count}\n")

    # Find records with 0 completeness
    records_to_fix = Compatibility.objects.filter(
        Q(user1_required_completeness=0) | Q(user2_required_completeness=0)
    ).select_related('user1', 'user2')

    count = records_to_fix.count()
    print(f"📦 Records to fix: {count}\n")

    if count == 0:
        print("✅ All records already have completeness calculated!")
        return

    # Build a cache of user required answers to avoid repeated queries
    print("🔄 Building cache of user required answers...")
    user_required_answers = {}

    # Get all unique users from records to fix
    user_ids = set()
    for comp in records_to_fix:
        user_ids.add(comp.user1_id)
        user_ids.add(comp.user2_id)

    print(f"   Caching answers for {len(user_ids)} unique users...")

    # Fetch all required answers for these users in one query
    answers = UserAnswer.objects.filter(
        user_id__in=user_ids,
        question__is_required_for_match=True
    ).values('user_id', 'question_id')

    # Build the cache
    for answer in answers:
        user_id = answer['user_id']
        question_id = answer['question_id']
        if user_id not in user_required_answers:
            user_required_answers[user_id] = set()
        user_required_answers[user_id].add(question_id)

    print(f"   ✅ Cache built\n")

    # Process in batches
    batch_size = 500
    updated = 0

    print(f"🔄 Processing {count} records in batches of {batch_size}...\n")

    for i in range(0, count, batch_size):
        batch = list(records_to_fix[i:i+batch_size])
        updates = []

        for comp in batch:
            try:
                # Get answers from cache
                a1_req = user_required_answers.get(comp.user1_id, set())
                a2_req = user_required_answers.get(comp.user2_id, set())

                # Calculate mutual required questions
                required_mutual_count = len(a1_req & a2_req)

                # Calculate directional completeness
                user1_required_answered = len(a1_req)
                user2_required_answered = len(a2_req)

                user1_completeness = (required_mutual_count / user2_required_answered) if user2_required_answered > 0 else 0.0
                user2_completeness = (required_mutual_count / user1_required_answered) if user1_required_answered > 0 else 0.0

                # Clamp 0-1
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
