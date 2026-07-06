from django.core.management.base import BaseCommand

from api.services.dummy_activity import fill_due_dummy_feed_activity


class Command(BaseCommand):
    help = "Create due dummy feed activity for the current day. Intended for hourly scheduler runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--daily-minimum",
            type=int,
            default=20,
            help="Minimum number of dummy feed items to create across a full day.",
        )

    def handle(self, *args, **options):
        result = fill_due_dummy_feed_activity(daily_minimum=options["daily_minimum"])
        self.stdout.write(
            self.style.SUCCESS(
                "Dummy activity: "
                f"due={result['due']} existing={result['existing']} "
                f"created={result['created']} daily_minimum={result['daily_minimum']}"
            )
        )
