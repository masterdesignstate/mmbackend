import csv
import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.management.commands.import_dummy_users import EXPECTED_USER_COUNT, read_dummy_csv
from api.models import User
from api.tagline_rewrites import MAX_TAGLINE_LENGTH, rewrite_tagline


DEFAULT_BATCH_DATE = date(2026, 6, 14)


def username_matches(source_username, database_username):
    return database_username == source_username or bool(
        re.fullmatch(rf"{re.escape(source_username)}_\d+", database_username)
    )


def validate_pair(source, user, position):
    expected = {
        "first_name": source["first_name"],
        "last_name": source["last_name"],
        "date_of_birth": source["date_of_birth"],
    }
    mismatches = [
        field for field, value in expected.items()
        if getattr(user, field) != value
    ]
    if not username_matches(source["username"], user.username):
        mismatches.append("username")
    if mismatches:
        raise CommandError(
            f"CSV/database alignment failed at row {position}: "
            f"{user.username} differs on {', '.join(mismatches)}."
        )


class Command(BaseCommand):
    help = "Safely repair taglines truncated by the June 2026 dummy-user import."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Original dummy-user CSV.")
        parser.add_argument(
            "--batch-date",
            type=date.fromisoformat,
            default=DEFAULT_BATCH_DATE,
            help="UTC date on which the 1,000-user batch was imported.",
        )
        parser.add_argument("--commit", action="store_true", help="Write the validated changes.")
        parser.add_argument(
            "--backup",
            help="CSV backup path; required with --commit.",
        )

    def handle(self, *args, **options):
        source_rows = read_dummy_csv(options["csv"])
        if len(source_rows) != EXPECTED_USER_COUNT:
            raise CommandError(
                f"Expected {EXPECTED_USER_COUNT} source rows, found {len(source_rows)}."
            )

        users = list(
            User.objects.filter(
                is_dummy=True,
                date_joined__date=options["batch_date"],
            ).order_by("date_joined", "id")
        )
        if len(users) != EXPECTED_USER_COUNT:
            raise CommandError(
                f"Expected {EXPECTED_USER_COUNT} database users for {options['batch_date']}, "
                f"found {len(users)}."
            )

        changes = []
        already_repaired = 0
        user_edited = 0
        complete_at_40 = 0

        for position, (source, user) in enumerate(zip(source_rows, users), start=1):
            validate_pair(source, user, position)
            original = source["tagline"].strip()
            if len(original) <= MAX_TAGLINE_LENGTH:
                if len(original) == MAX_TAGLINE_LENGTH:
                    complete_at_40 += 1
                continue

            replacement = rewrite_tagline(original)
            truncated = original[:MAX_TAGLINE_LENGTH]
            if user.tagline == replacement:
                already_repaired += 1
            elif user.tagline == truncated:
                changes.append((user, original, replacement))
            else:
                user_edited += 1

        self.stdout.write("Dummy tagline repair plan")
        self.stdout.write(f"  Source/database rows aligned: {len(users)}")
        self.stdout.write(f"  Truncated taglines to update: {len(changes)}")
        self.stdout.write(f"  Complete taglines exactly 40 chars: {complete_at_40}")
        self.stdout.write(f"  Already repaired: {already_repaired}")
        self.stdout.write(f"  User-edited taglines preserved: {user_edited}")
        for user, original, replacement in changes[:20]:
            self.stdout.write(f"  {user.username}: {original!r} -> {replacement!r}")
        if len(changes) > 20:
            self.stdout.write(f"  ... and {len(changes) - 20} more")

        if not options["commit"]:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --commit and --backup."))
            return
        if not options["backup"]:
            raise CommandError("--backup is required with --commit.")

        backup_path = Path(options["backup"]).expanduser().resolve()
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        with transaction.atomic():
            locked = {
                user.id: user
                for user in User.objects.select_for_update().filter(
                    id__in=[user.id for user, _, _ in changes]
                )
            }
            for user, original, replacement in changes:
                current = locked[user.id]
                if current.tagline != original[:MAX_TAGLINE_LENGTH]:
                    raise CommandError(
                        f"{current.username}'s tagline changed after validation; no updates written."
                    )

            with backup_path.open("w", newline="", encoding="utf-8") as backup_file:
                writer = csv.writer(backup_file)
                writer.writerow([
                    "user_id",
                    "username",
                    "source_tagline",
                    "previous_tagline",
                    "replacement_tagline",
                ])
                for user, original, replacement in changes:
                    current = locked[user.id]
                    writer.writerow([
                        current.id,
                        current.username,
                        original,
                        current.tagline,
                        replacement,
                    ])

            to_update = []
            for user, _, replacement in changes:
                current = locked[user.id]
                current.tagline = replacement
                to_update.append(current)
            User.objects.bulk_update(to_update, ["tagline"])

        self.stdout.write(self.style.SUCCESS(
            f"Updated {len(changes)} taglines. Backup: {backup_path}"
        ))
