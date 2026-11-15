from django.core.management.base import BaseCommand

from api.services import active_limits


class Command(BaseCommand):
    help = (
        'Keep the youngest N dummy accounts and the first N questions enabled, '
        'disable the rest, then rescore compatibility between enabled users.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dummies', type=int, help='Dummy accounts to keep enabled')
        parser.add_argument('--questions', type=int, help='Distinct question numbers to keep enabled')
        parser.add_argument('--dry-run', action='store_true', help='Print the plan without writing')
        parser.add_argument(
            '--skip-recalculate', action='store_true',
            help='Queue compatibility jobs instead of rescoring synchronously',
        )

    def handle(self, *args, **options):
        dummies = options['dummies']
        questions = options['questions']
        if dummies is None and questions is None:
            self.stderr.write('Pass --dummies and/or --questions.')
            return

        self.stdout.write(f'Before: {active_limits.active_limit_counts()}')

        if options['dry_run']:
            if dummies is not None:
                keep, drop = active_limits.plan_dummy_limit(dummies)
                self.stdout.write(f'Dummies: keep {len(keep)}, disable {len(drop)}')
            if questions is not None:
                keep, drop = active_limits.plan_question_limit(questions)
                self.stdout.write(
                    f'Questions: keep {len(keep)} numbers (up to {max(keep) if keep else "-"}), '
                    f'disable {len(drop)}'
                )
            self.stdout.write(self.style.WARNING('Dry run, nothing written.'))
            return

        if dummies is not None:
            self.stdout.write(f'Dummies: {active_limits.apply_dummy_limit(dummies)}')
        if questions is not None:
            self.stdout.write(f'Questions: {active_limits.apply_question_limit(questions)}')
        active_limits.invalidate_question_state()

        self.stdout.write(f'After: {active_limits.active_limit_counts()}')

        if options['skip_recalculate']:
            queued = active_limits.enqueue_full_recalculation()
            self.stdout.write(f'Queued {queued} compatibility jobs.')
        else:
            rescored = active_limits.recalculate_enabled_users(log=self.stdout.write)
            self.stdout.write(self.style.SUCCESS(f'Rescored {rescored} enabled users.'))
