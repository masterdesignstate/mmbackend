import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api import mandatory_questions as mq
from api.management.commands.import_dummy_users import (
    ALLOWED_PHOTO_SUFFIXES,
    EXPECTED_USER_COUNT,
    FIRST_NAME_GENDERS,
    AzureUploader,
    calculate_age,
    make_blob_name,
    stable_int,
)
from api.management.commands.repair_dummy_taglines import DEFAULT_BATCH_DATE
from api.models import FeedActivity, User, UserAnswer, UserPicture


AGE_BANDS = (
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-54", 45, 54),
    ("55-64", 55, 64),
    ("65+", 65, None),
)
BAND_LABELS = tuple(label for label, _, _ in AGE_BANDS)
MANIFEST_GENDERS = {"man": "male", "woman": "female"}
# make_blob_name ends a blob with "-<first 12 hex of the file's sha256>.<ext>".
BLOB_DIGEST_LENGTH = 12
BLOB_DIGEST_RE = re.compile(rf"-([0-9a-f]{{{BLOB_DIGEST_LENGTH}}})\.[A-Za-z0-9]+(?:\?|$)")


@dataclass(frozen=True)
class PhotoChange:
    user: User
    gender: str
    age: int
    band: str
    photo: Path
    blob_name: str


def age_band(age):
    for label, low, high in AGE_BANDS:
        if age >= low and (high is None or age <= high):
            return label
    return None


def read_exclusions(paths):
    excluded = set()
    for path in paths:
        with Path(path).expanduser().open(encoding="utf-8") as exclude_file:
            for line in exclude_file:
                entry = line.split("#", 1)[0].strip()
                if entry:
                    excluded.add(entry)
    return excluded


def read_previous_runs(paths):
    """Map user id to the photo URL an earlier run of this command gave them."""
    previous = {}
    for path in paths:
        with Path(path).expanduser().open(newline="", encoding="utf-8") as backup_file:
            for row in csv.DictReader(backup_file):
                previous[row["user_id"]] = row["new_url"]
    return previous


def used_digests(urls):
    """The stock-file digests those URLs were built from, so no photo is handed out twice."""
    matches = (BLOB_DIGEST_RE.search(url) for url in urls)
    return {match.group(1) for match in matches if match}


def read_manifest(manifest_path, excluded=frozenset(), consumed_digests=frozenset()):
    """Return usable stock photos keyed by (gender, age band), skipping excluded and used photos."""
    manifest_path = Path(manifest_path).expanduser()
    if not manifest_path.is_file():
        raise CommandError(f"Manifest not found: {manifest_path}")

    photos = defaultdict(list)
    seen_paths = set()
    digests = {}
    with manifest_path.open(newline="", encoding="utf-8-sig") as manifest_file:
        for line_number, row in enumerate(csv.DictReader(manifest_file), start=2):
            relative = (row.get("path") or "").strip()
            gender = MANIFEST_GENDERS.get((row.get("gender") or "").strip())
            band = (row.get("ageband") or "").strip()
            if not relative or not gender or band not in BAND_LABELS:
                raise CommandError(f"Manifest line {line_number} has an invalid path, gender or ageband.")
            if relative in seen_paths:
                raise CommandError(f"Manifest line {line_number} repeats {relative}.")
            seen_paths.add(relative)
            if relative in excluded:
                continue

            photo = manifest_path.parent / relative
            if photo.suffix.lower() not in ALLOWED_PHOTO_SUFFIXES or not photo.is_file() or photo.stat().st_size == 0:
                raise CommandError(f"Manifest line {line_number}: {relative} is missing, empty or not an image.")
            digest = sha256(photo.read_bytes()).hexdigest()
            if digest[:BLOB_DIGEST_LENGTH] in consumed_digests:
                continue
            if digest in digests:
                raise CommandError(f"{relative} is byte-identical to {digests[digest]}; exclude one of them.")
            digests[digest] = relative
            photos[(gender, band)].append(photo)

    unknown = excluded - seen_paths
    if unknown:
        raise CommandError("Excluded paths missing from the manifest: " + ", ".join(sorted(unknown)[:10]))
    for band_photos in photos.values():
        band_photos.sort()
    return photos


def answer_genders(users):
    """Gender implied by each user's Female/Male Me answers, where they split cleanly 5/1."""
    answers = defaultdict(dict)
    rows = UserAnswer.objects.filter(
        user__in=users, question__question_number__in=(mq.FEMALE, mq.MALE)
    ).values_list("user_id", "question__question_number", "me_answer")
    for user_id, number, me_answer in rows:
        answers[user_id][number] = me_answer

    genders = {}
    for user_id, by_number in answers.items():
        if by_number.get(mq.MALE) == 5 and by_number.get(mq.FEMALE) == 1:
            genders[user_id] = "male"
        elif by_number.get(mq.FEMALE) == 5 and by_number.get(mq.MALE) == 1:
            genders[user_id] = "female"
    return genders


def has_imported_photo(user):
    """True while the user still has only the single photo the dummy import gave them."""
    pictures = list(user.pictures.all())
    return (
        len(pictures) == 1
        and pictures[0].image_url == user.profile_photo
        and "/dummy-users/" in (user.profile_photo or "")
    )


def plan_assignments(users_by_slot, photos_by_slot, seed):
    """Pair each (gender, band) slot's users with its photos; users beyond the supply are left out."""
    pairs = []
    for slot, users in sorted(users_by_slot.items()):
        ordered = sorted(users, key=lambda user: (stable_int(seed, user.id, "photo"), str(user.id)))
        pairs.extend((slot, user, photo) for user, photo in zip(ordered, photos_by_slot.get(slot, [])))
    return pairs


class Command(BaseCommand):
    help = "Replace the dummy batch's profile photos with gender- and age-matched stock portraits."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", required=True, help="Stock manifest.csv with path, gender and ageband columns.")
        parser.add_argument(
            "--exclude",
            action="append",
            default=[],
            help="File listing manifest paths to skip, one per line. Repeatable.",
        )
        parser.add_argument(
            "--previous",
            action="append",
            default=[],
            help=(
                "Backup CSV from an earlier run. Its users keep the photo they already have, "
                "and those photos are not handed to anyone else. Repeatable."
            ),
        )
        parser.add_argument(
            "--batch-date",
            type=date.fromisoformat,
            default=DEFAULT_BATCH_DATE,
            help="UTC date on which the 1,000-user batch was imported.",
        )
        parser.add_argument("--seed", type=int, default=20260914)
        parser.add_argument("--commit", action="store_true", help="Upload photos and write the validated changes.")
        parser.add_argument("--backup", help="CSV backup path for rollback; required with --commit.")

    def handle(self, *args, **options):
        manifest_root = Path(options["manifest"]).expanduser().parent
        previous = read_previous_runs(options["previous"])

        users = list(
            User.objects.filter(is_dummy=True, date_joined__date=options["batch_date"])
            .prefetch_related("pictures")
            .order_by("date_joined", "id")
        )
        if len(users) != EXPECTED_USER_COUNT:
            raise CommandError(
                f"Expected {EXPECTED_USER_COUNT} database users for {options['batch_date']}, found {len(users)}."
            )

        finished = {
            user.id: previous[str(user.id)]
            for user in users
            if previous.get(str(user.id)) == user.profile_photo
        }
        photos_by_slot = read_manifest(
            options["manifest"],
            read_exclusions(options["exclude"]),
            used_digests(finished.values()),
        )

        genders = answer_genders(users)
        today = date.today()
        users_by_slot = defaultdict(list)
        ages = {}
        edited = 0
        for user in users:
            gender = FIRST_NAME_GENDERS.get(user.first_name)
            if not gender:
                raise CommandError(f"{user.username}: no gender mapping for first name {user.first_name!r}.")
            if genders.get(user.id, gender) != gender:
                raise CommandError(f"{user.username}: first-name gender disagrees with their Female/Male answers.")
            if not user.date_of_birth:
                raise CommandError(f"{user.username} has no date of birth.")
            if user.id in finished:
                continue
            if not has_imported_photo(user):
                edited += 1
                continue
            ages[user.id] = calculate_age(user.date_of_birth, today)
            users_by_slot[(gender, age_band(ages[user.id]))].append(user)

        changes = []
        already_replaced = 0
        for (gender, band), user, photo in plan_assignments(users_by_slot, photos_by_slot, options["seed"]):
            blob_name = make_blob_name(user.username, photo)
            if urlsplit(user.profile_photo).path.endswith(f"/{blob_name}"):
                already_replaced += 1
            else:
                changes.append(PhotoChange(user, gender, ages[user.id], band, photo, blob_name))

        self.stdout.write("Dummy photo replacement plan")
        self.stdout.write(f"  Batch users: {len(users)}")
        self.stdout.write(f"  Finished in an earlier run: {len(finished)}")
        self.stdout.write(f"  Users with edited photos preserved: {edited}")
        self.stdout.write(f"  {'gender':<7} {'band':<6} {'users':>5} {'photos':>6} {'assigned':>8} {'unchanged':>9}")
        slots = sorted(set(users_by_slot) | set(photos_by_slot), key=lambda slot: (slot[0], str(slot[1])))
        for slot in slots:
            slot_users = len(users_by_slot.get(slot, []))
            assigned = min(slot_users, len(photos_by_slot.get(slot, [])))
            self.stdout.write(
                f"  {slot[0]:<7} {str(slot[1]):<6} {slot_users:>5} {len(photos_by_slot.get(slot, [])):>6} "
                f"{assigned:>8} {slot_users - assigned:>9}"
            )
        self.stdout.write(f"  Photos to replace: {len(changes)}")
        self.stdout.write(f"  Already replaced: {already_replaced}")
        for change in changes[:10]:
            self.stdout.write(
                f"  {change.user.username} ({change.gender}, {change.age}) -> {change.photo.relative_to(manifest_root)}"
            )
        if len(changes) > 10:
            self.stdout.write(f"  ... and {len(changes) - 10} more")

        if not options["commit"]:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --commit and --backup."))
            return
        if not options["backup"]:
            raise CommandError("--backup is required with --commit.")
        backup_path = Path(options["backup"]).expanduser().resolve()
        if backup_path.exists():
            raise CommandError(f"Backup already exists; refusing to overwrite {backup_path}.")
        if not changes:
            self.stdout.write(self.style.SUCCESS("Nothing to replace."))
            return

        uploader = AzureUploader.from_environment()
        uploader.validate()
        new_urls = {}
        for index, change in enumerate(changes, start=1):
            new_urls[change.user.id] = uploader.upload(change.photo, change.blob_name)
            if index % 100 == 0 or index == len(changes):
                self.stdout.write(f"  Uploaded {index}/{len(changes)}")

        user_ids = [change.user.id for change in changes]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with transaction.atomic():
            locked = {user.id: user for user in User.objects.select_for_update().filter(id__in=user_ids)}
            pictures = defaultdict(list)
            for picture in UserPicture.objects.select_for_update().filter(user_id__in=user_ids):
                pictures[picture.user_id].append(picture)
            activities = defaultdict(list)
            for activity in FeedActivity.objects.select_for_update().filter(user_id__in=user_ids, kind="photo_added"):
                activities[activity.user_id].append(activity)

            for change in changes:
                previous = change.user.profile_photo
                current = pictures[change.user.id]
                if (
                    locked[change.user.id].profile_photo != previous
                    or len(current) != 1
                    or current[0].image_url != previous
                ):
                    raise CommandError(
                        f"{change.user.username}'s photos changed after validation; no updates written."
                    )

            users_to_update, pictures_to_update, activities_to_update = [], [], []
            with backup_path.open("w", newline="", encoding="utf-8") as backup_file:
                writer = csv.writer(backup_file)
                writer.writerow([
                    "user_id", "username", "gender", "age", "age_band", "photo",
                    "previous_url", "new_url", "feed_activity_ids",
                ])
                for change in changes:
                    previous = change.user.profile_photo
                    new_url = new_urls[change.user.id]
                    matching = [
                        activity for activity in activities[change.user.id]
                        if activity.payload.get("image_url") == previous
                    ]
                    writer.writerow([
                        change.user.id, change.user.username, change.gender, change.age, change.band,
                        change.photo.relative_to(manifest_root), previous, new_url,
                        ";".join(str(activity.id) for activity in matching),
                    ])

                    user = locked[change.user.id]
                    user.profile_photo = new_url
                    users_to_update.append(user)
                    picture = pictures[change.user.id][0]
                    picture.image_url = new_url
                    pictures_to_update.append(picture)
                    for activity in matching:
                        activity.payload = {**activity.payload, "image_url": new_url}
                        activities_to_update.append(activity)

            User.objects.bulk_update(users_to_update, ["profile_photo"], batch_size=200)
            UserPicture.objects.bulk_update(pictures_to_update, ["image_url"], batch_size=200)
            FeedActivity.objects.bulk_update(activities_to_update, ["payload"], batch_size=200)

        self.stdout.write(self.style.SUCCESS(
            f"Replaced {len(changes)} dummy photos and repointed {len(activities_to_update)} photo feed items. "
            f"Backup: {backup_path}"
        ))
