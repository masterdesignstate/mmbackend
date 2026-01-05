#!/usr/bin/env python
"""
Script to recalculate required compatibility for all existing compatibility records.

This fixes old records that were created before the required compatibility feature was implemented.
Run this after the calculate_all_compatibilities command has been updated with the fix.

Usage:
    python recalculate_required_compatibility.py
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from api.models import Compatibility, Question
from api.services.compatibility_service import CompatibilityService


def recalculate_required_compatibility():
    """Recalculate required compatibility for all existing records"""

    # Get counts
    total_count = Compatibility.objects.count()
    zero_count = Compatibility.objects.filter(required_overall_compatibility=0).count()

    print(f"📊 Database statistics:")
    print(f"   Total compatibility records: {total_count}")
    print(f"   Records with required_overall = 0: {zero_count}")
    print(f"   Records with required_overall > 0: {total_count - zero_count}")
    print()

    if zero_count == 0:
        print("✅ All records already have required compatibility calculated!")
        return

    print(f"🔄 Recalculating {zero_count} records with missing required compatibility...")
    print()

    # Get required question count once (for optimization)
    total_required_count = Question.objects.filter(is_required_for_match=True).count()
    print(f"ℹ️  Total required questions: {total_required_count}")
    print()

    # Process in batches
    batch_size = 100
    updated_count = 0
    error_count = 0

    # Get all records that need updating
    records_to_update = Compatibility.objects.filter(required_overall_compatibility=0)

    for i in range(0, zero_count, batch_size):
        batch = records_to_update[i:i+batch_size]
        print(f"📦 Processing batch {i // batch_size + 1}: records {i+1}-{min(i+batch_size, zero_count)}")

        updates = []

        for comp in batch:
            try:
                # Recalculate compatibility
                result = CompatibilityService.calculate_compatibility_between_users(
                    comp.user1,
                    comp.user2,
                    total_required_count=total_required_count
                )

                # Update required fields
                comp.required_overall_compatibility = Decimal(str(result.get('required_overall_compatibility', 0)))
                comp.required_compatible_with_me = Decimal(str(result.get('required_compatible_with_me', 0)))
                comp.required_im_compatible_with = Decimal(str(result.get('required_im_compatible_with', 0)))
                comp.required_mutual_questions_count = result.get('required_mutual_questions_count', 0)
                comp.user1_required_completeness = Decimal(str(result.get('user1_required_completeness', 0)))
                comp.user2_required_completeness = Decimal(str(result.get('user2_required_completeness', 0)))
                comp.required_completeness_ratio = Decimal(str(result.get('required_completeness_ratio', 0)))

                updates.append(comp)
                updated_count += 1

            except Exception as e:
                error_count += 1
                print(f"   ❌ Error processing {comp.user1.username} <-> {comp.user2.username}: {e}")

        # Bulk update the batch
        if updates:
            Compatibility.objects.bulk_update(
                updates,
                fields=[
                    'required_overall_compatibility',
                    'required_compatible_with_me',
                    'required_im_compatible_with',
                    'required_mutual_questions_count',
                    'user1_required_completeness',
                    'user2_required_completeness',
                    'required_completeness_ratio'
                ]
            )
            print(f"   ✅ Updated {len(updates)} records")

    print()
    print("=" * 60)
    print(f"✅ Recalculation complete!")
    print(f"   Updated: {updated_count}")
    print(f"   Errors: {error_count}")
    print()

    # Verify
    remaining_zero = Compatibility.objects.filter(required_overall_compatibility=0).count()
    print(f"📊 Final statistics:")
    print(f"   Records still with required_overall = 0: {remaining_zero}")
    print(f"   Records with required_overall > 0: {total_count - remaining_zero}")

    if remaining_zero == 0:
        print()
        print("🎉 All compatibility records now have required compatibility calculated!")
    elif remaining_zero > 0:
        print()
        print(f"⚠️  {remaining_zero} records still have required_overall = 0")
        print("   These may be pairs with no mutual required questions.")


if __name__ == '__main__':
    recalculate_required_compatibility()
