from django.core.management.base import BaseCommand

from api.services.dummy_activity import (
    fill_due_dummy_feed_activity,
    fill_due_dummy_required_question_answers,
)


class Command(BaseCommand):
    help = "Create due dummy feed activity for the current day. Intended for hourly scheduler runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--daily-minimum",
            type=int,
            default=20,
            help="Minimum number of dummy feed items to create across a full day.",
        )
        parser.add_argument(
            "--required-daily-count",
            type=int,
            default=5,
            help="Number of dummy users per day who should have all pending required questions answered.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report which users/questions the required-question catch-up would touch, without writing anything.",
        )
        parser.add_argument(
            "--ignore-controls",
            action="store_true",
            help="Run even if the dashboard toggles are off. For manual/debug runs only -- the scheduler should never pass this.",
        )

    def handle(self, *args, **options):
        ignore_controls = options["ignore_controls"]

        result = fill_due_dummy_feed_activity(
            daily_minimum=options["daily_minimum"],
            ignore_controls=ignore_controls,
        )
        if result.get("skipped") == "disabled":
            self.stdout.write(self.style.WARNING(
                "Dummy activity: skipped (auto_updater_enabled is off in Controls)"
            ))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dummy activity: "
                    f"due={result['due']} existing={result['existing']} "
                    f"created={result['created']} daily_minimum={result['daily_minimum']}"
                )
            )

        required_result = fill_due_dummy_required_question_answers(
            daily_count=options["required_daily_count"],
            dry_run=options["dry_run"],
            ignore_controls=ignore_controls,
        )
        if required_result.get("skipped") == "disabled":
            self.stdout.write(self.style.WARNING(
                "Required-question catch-up: skipped (disabled in Controls)"
            ))
            return

        label = "Required-question catch-up (dry-run)" if options["dry_run"] else "Required-question catch-up"
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: "
                f"daily_count={required_result['daily_count']} "
                f"selected_users={required_result['selected_users']} "
                f"users_touched={required_result['users_touched']} "
                f"questions_answered={required_result['questions_answered']}"
            )
        )
        if required_result["selected_users"] == 0:
            self.stdout.write(self.style.WARNING(
                "  No eligible users: the catch-up only runs for real (non-dummy) "
                "accounts, and none exist yet."
            ))
