from django.core.management.base import BaseCommand
from django.db.models import Q
from api.models import User, Compatibility
from api.services.compatibility_service import CompatibilityService
import time


class Command(BaseCommand):
    help = 'Pre-calculate compatibility scores for all user pairs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recalculate all compatibilities even if they already exist',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of users to process at a time',
        )

    def handle(self, *args, **options):
        start_time = time.time()
        force_recalculate = options['force']
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS('🚀 Starting compatibility pre-calculation...'))

        # Get all active users with answers
        users = User.objects.exclude(is_banned=True).filter(
            answers__isnull=False
        ).distinct()

        total_users = users.count()
        total_pairs = (total_users * (total_users - 1)) // 2  # Unique pairs
        processed_pairs = 0
        created_pairs = 0
        updated_pairs = 0
        skipped_pairs = 0

        self.stdout.write(f'📊 Found {total_users} users')
        self.stdout.write(f'🔢 Total possible pairs: {total_pairs}')
        self.stdout.write(f'⚡ Batch size: {batch_size}')
        self.stdout.write('─' * 50)

        # Process users in batches
        for i in range(0, total_users, batch_size):
            batch_users = list(users[i:i + batch_size])
            self.stdout.write(f'📦 Processing batch {i // batch_size + 1}: users {i + 1}-{min(i + batch_size, total_users)}')

            for j, user1 in enumerate(batch_users):
                # Calculate with all users that come after this user in the entire list
                user1_position = i + j
                remaining_users = users[user1_position + 1:]

                for user2 in remaining_users:
                    if user1.id == user2.id:
                        continue

                    processed_pairs += 1

                    # Check if compatibility already exists
                    existing = Compatibility.objects.filter(
                        Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1)
                    ).first()

                    if existing and not force_recalculate:
                        skipped_pairs += 1
                        continue

                    # Calculate compatibility
                    try:
                        compatibility_data = CompatibilityService.calculate_compatibility_between_users(
                            user1, user2
                        )

                        if existing:
                            # Update existing record
                            for key, value in compatibility_data.items():
                                setattr(existing, key, value)
                            existing.save()
                            updated_pairs += 1
                        else:
                            # Create new record
                            Compatibility.objects.create(
                                user1=user1,
                                user2=user2,
                                **compatibility_data
                            )
                            created_pairs += 1

                        # Progress update every 100 pairs
                        if processed_pairs % 100 == 0:
                            progress = (processed_pairs / total_pairs) * 100
                            self.stdout.write(
                                f'📈 Progress: {processed_pairs}/{total_pairs} ({progress:.1f}%)'
                            )

                    except Exception as e:
                        self.stderr.write(
                            f'❌ Error calculating compatibility for {user1.username} <-> {user2.username}: {e}'
                        )

        # Final statistics
        end_time = time.time()
        duration = end_time - start_time
        pairs_per_second = processed_pairs / duration if duration > 0 else 0

        self.stdout.write('─' * 50)
        self.stdout.write(self.style.SUCCESS('🎉 Compatibility pre-calculation completed!'))
        self.stdout.write(f'📊 Total pairs processed: {processed_pairs}')
        self.stdout.write(f'✅ New compatibilities created: {created_pairs}')
        self.stdout.write(f'🔄 Existing compatibilities updated: {updated_pairs}')
        self.stdout.write(f'⏭️  Compatibilities skipped: {skipped_pairs}')
        self.stdout.write(f'⏱️  Total time: {duration:.2f} seconds')
        self.stdout.write(f'🚀 Processing speed: {pairs_per_second:.2f} pairs/second')

        # Verification
        total_stored = Compatibility.objects.count()
        self.stdout.write(f'💾 Total compatibilities in database: {total_stored}')

        if total_stored >= total_pairs * 0.9:  # Allow for some variance
            self.stdout.write(self.style.SUCCESS('✅ Pre-calculation successful!'))
        else:
            self.stdout.write(self.style.WARNING(f'⚠️  Expected ~{total_pairs} but got {total_stored}'))