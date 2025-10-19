from django.core.management.base import BaseCommand
from django.db.models import Q
from api.models import User, Compatibility
from api.services.compatibility_service import CompatibilityService
import time


class Command(BaseCommand):
    help = 'Calculate missing compatibility scores incrementally (for scheduled jobs with time limits)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-pairs',
            type=int,
            default=100,
            help='Maximum number of pairs to process in this run',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=50,
            help='Maximum time in seconds to run (default 50s for Heroku 60s limit)',
        )

    def handle(self, *args, **options):
        start_time = time.time()
        max_pairs = options['max_pairs']
        timeout = options['timeout']

        self.stdout.write(self.style.SUCCESS(f'🚀 Starting incremental compatibility calculation...'))
        self.stdout.write(f'⏱️  Max time: {timeout}s, Max pairs: {max_pairs}')

        # Get all users with answers
        users = list(User.objects.exclude(is_banned=True).filter(
            answers__isnull=False
        ).distinct().order_by('id'))

        total_users = len(users)
        processed_pairs = 0
        created_pairs = 0
        skipped_pairs = 0

        self.stdout.write(f'📊 Found {total_users} users')

        # Get all existing compatibility user pairs to avoid checking them
        existing_pairs = set()
        for comp in Compatibility.objects.only('user1_id', 'user2_id').iterator(chunk_size=1000):
            # Store both directions
            pair = tuple(sorted([str(comp.user1_id), str(comp.user2_id)]))
            existing_pairs.add(pair)

        self.stdout.write(f'📊 Found {len(existing_pairs)} existing compatibility pairs')

        # Find missing compatibilities
        for i, user1 in enumerate(users):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                self.stdout.write(self.style.WARNING(f'⏰ Timeout reached ({elapsed:.1f}s), stopping...'))
                break

            # Check max pairs limit
            if created_pairs >= max_pairs:
                self.stdout.write(self.style.WARNING(f'📦 Max pairs limit reached ({max_pairs}), stopping...'))
                break

            for user2 in users[i+1:]:
                # Check timeout again (inner loop)
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    break

                if created_pairs >= max_pairs:
                    break

                # Check if this pair already exists (using our pre-loaded set)
                pair = tuple(sorted([str(user1.id), str(user2.id)]))
                if pair in existing_pairs:
                    skipped_pairs += 1
                    continue

                # Calculate compatibility for missing pair
                try:
                    compatibility_data = CompatibilityService.calculate_compatibility_between_users(
                        user1, user2
                    )

                    Compatibility.objects.create(
                        user1=user1,
                        user2=user2,
                        **compatibility_data
                    )
                    # Add to existing pairs so we don't recalculate
                    existing_pairs.add(pair)
                    created_pairs += 1

                    # Progress update every 10 pairs
                    if created_pairs % 10 == 0:
                        elapsed = time.time() - start_time
                        rate = created_pairs / elapsed if elapsed > 0 else 0
                        self.stdout.write(
                            f'✅ Created {created_pairs} pairs ({rate:.1f} pairs/sec, {elapsed:.1f}s elapsed)'
                        )

                except Exception as e:
                    self.stderr.write(
                        f'❌ Error calculating compatibility for {user1.username} <-> {user2.username}: {e}'
                    )

        # Final statistics
        end_time = time.time()
        duration = end_time - start_time

        self.stdout.write('─' * 50)
        self.stdout.write(self.style.SUCCESS('🎉 Incremental calculation completed!'))
        self.stdout.write(f'✅ New compatibilities created: {created_pairs}')
        self.stdout.write(f'⏭️  Existing compatibilities skipped: {skipped_pairs}')
        self.stdout.write(f'⏱️  Total time: {duration:.2f} seconds')

        # Check remaining work
        total_expected = (total_users * (total_users - 1)) // 2
        total_actual = Compatibility.objects.count()
        remaining = total_expected - total_actual

        self.stdout.write(f'📊 Database status:')
        self.stdout.write(f'   Total compatibility records: {total_actual}/{total_expected}')
        self.stdout.write(f'   Coverage: {(total_actual/total_expected*100) if total_expected > 0 else 0:.1f}%')
        if remaining > 0:
            self.stdout.write(f'   ⚠️  Still missing: {remaining} pairs (run again to continue)')
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ All compatibilities calculated!'))
