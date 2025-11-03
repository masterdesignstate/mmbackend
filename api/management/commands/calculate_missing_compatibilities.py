import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import CompatibilityJob
from api.services.compatibility_queue import MIN_MATCHABLE_ANSWERS
from api.services.compatibility_service import CompatibilityService


class Command(BaseCommand):
    help = 'Process pending compatibility jobs incrementally (designed for short scheduled runs)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-pairs',
            type=int,
            default=100,
            help='Maximum number of compatibility jobs to process in this run',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=50,
            help='Maximum time in seconds to run (default 50s for Heroku 60s limit)',
        )

    def handle(self, *args, **options):
        start_time = time.time()
        max_jobs = max(1, options['max_pairs'])
        timeout = options['timeout']

        self.stdout.write(self.style.SUCCESS('🚀 Starting compatibility job processor...'))
        self.stdout.write(f'⏱️  Max time: {timeout}s, Max jobs: {max_jobs}')

        processed_jobs = 0
        successful_jobs = 0
        skipped_jobs = 0
        failed_jobs = 0
        total_pairs_created = 0

        pending_queryset = (
            CompatibilityJob.objects
            .select_related('user')
            .filter(status=CompatibilityJob.STATUS_PENDING)
            .order_by('created_at')
        )

        for job in pending_queryset.iterator():
            if processed_jobs >= max_jobs:
                self.stdout.write(self.style.WARNING(f'📦 Max jobs limit reached ({max_jobs}), stopping...'))
                break

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                self.stdout.write(self.style.WARNING(f'⏰ Timeout reached ({elapsed:.1f}s), stopping...'))
                break

            user = job.user

            if user.is_banned:
                skipped_jobs += 1
                job.status = CompatibilityJob.STATUS_COMPLETED
                job.error_message = 'User is banned; skipping compatibility generation'
                job.save(update_fields=['status', 'error_message', 'updated_at'])
                continue

            if user.answers.count() < MIN_MATCHABLE_ANSWERS:
                skipped_jobs += 1
                job.status = CompatibilityJob.STATUS_COMPLETED
                job.error_message = 'Not enough answers to compute compatibility'
                job.save(update_fields=['status', 'error_message', 'updated_at'])
                continue

            processed_jobs += 1

            with transaction.atomic():
                job.status = CompatibilityJob.STATUS_PROCESSING
                job.attempts += 1
                job.last_attempt_at = timezone.now()
                job.error_message = ''
                job.save(update_fields=['status', 'attempts', 'last_attempt_at', 'error_message', 'updated_at'])

            try:
                pairs_created = CompatibilityService.recalculate_all_compatibilities(user)
                total_pairs_created += pairs_created
                successful_jobs += 1

                job.status = CompatibilityJob.STATUS_COMPLETED
                job.error_message = ''
                job.updated_at = timezone.now()
                job.save(update_fields=['status', 'error_message', 'updated_at'])

                self.stdout.write(
                    f'✅ Processed user {user.username} ({user.id}) - {pairs_created} pairs recalculated'
                )
            except Exception as exc:
                failed_jobs += 1
                job.status = CompatibilityJob.STATUS_FAILED
                job.error_message = str(exc)[:500]
                job.updated_at = timezone.now()
                job.save(update_fields=['status', 'error_message', 'updated_at'])

                self.stderr.write(
                    f'❌ Failed processing user {user.username} ({user.id}): {exc}'
                )

        duration = time.time() - start_time
        remaining_jobs = CompatibilityJob.objects.filter(status=CompatibilityJob.STATUS_PENDING).count()

        self.stdout.write('─' * 50)
        self.stdout.write(self.style.SUCCESS('🎉 Compatibility job processing completed!'))
        self.stdout.write(f'🧮 Jobs processed this run: {processed_jobs}')
        self.stdout.write(f'   ├─ ✅ Successful: {successful_jobs}')
        self.stdout.write(f'   ├─ ⏭️  Skipped: {skipped_jobs}')
        self.stdout.write(f'   └─ ❌ Failed: {failed_jobs}')
        self.stdout.write(f'🔢 Total pairs recalculated: {total_pairs_created}')
        self.stdout.write(f'🕒 Elapsed time: {duration:.2f}s')
        self.stdout.write(f'📬 Jobs still pending: {remaining_jobs}')

        if failed_jobs > 0:
            self.stdout.write(self.style.WARNING('⚠️  Some jobs failed. Check logs for details.'))
