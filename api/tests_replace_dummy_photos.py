import csv
import hashlib
import os
import tempfile
from datetime import date, datetime, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api import mandatory_questions as mq
from api.management.commands import import_dummy_users as importer
from api.management.commands import replace_dummy_photos as replacer
from api.models import FeedActivity, Question, User, UserAnswer, UserPicture


BATCH_JOINED = datetime(2026, 6, 14, 12, tzinfo=dt_timezone.utc)


def dob_for_age(age):
    return date(date.today().year - age, 1, 1)


class FakeUploader:
    container_name = "photos"

    def __init__(self):
        self.uploaded = []

    def validate(self):
        pass

    def upload(self, file_path, blob_name):
        self.uploaded.append(blob_name)
        return f"https://blob.test/photos/{blob_name}?sas"


class ReplaceDummyPhotosTests(TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.manifest = self.root / "manifest.csv"

    def write_manifest(self, photos):
        with self.manifest.open("w", newline="") as manifest_file:
            writer = csv.writer(manifest_file)
            writer.writerow(["path", "gender", "ageband", "source_url", "license", "source", "id"])
            for relative, content in photos:
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                gender, band = relative.split("/")[:2]
                writer.writerow([relative, "man" if gender == "men" else "woman", band, "", "CC0", "", ""])

    def make_url(self, username):
        return f"https://blobmm.blob.core.windows.net/photos/profile-photos/dummy-users/{username}-old.jpg?sig=x"

    def make_user(self, username, first_name, age):
        url = self.make_url(username)
        user = User.objects.create(
            username=username,
            first_name=first_name,
            date_of_birth=dob_for_age(age),
            is_dummy=True,
            profile_photo=url,
        )
        User.objects.filter(id=user.id).update(date_joined=BATCH_JOINED)
        UserPicture.objects.create(user=user, image_url=url, order=0)
        return User.objects.get(id=user.id)

    def run_command(self, *args, uploader=None, expected_users=4):
        out = StringIO()
        with patch.object(replacer, "EXPECTED_USER_COUNT", expected_users), patch.object(
            replacer.AzureUploader, "from_environment", return_value=uploader or FakeUploader()
        ):
            call_command("replace_dummy_photos", "--manifest", str(self.manifest), *args, stdout=out)
        return out.getvalue()

    def test_age_band_boundaries(self):
        self.assertIsNone(replacer.age_band(17))
        self.assertEqual(replacer.age_band(18), "18-24")
        self.assertEqual(replacer.age_band(24), "18-24")
        self.assertEqual(replacer.age_band(25), "25-34")
        self.assertEqual(replacer.age_band(64), "55-64")
        self.assertEqual(replacer.age_band(65), "65+")
        self.assertEqual(replacer.age_band(99), "65+")

    def test_read_manifest_skips_exclusions_and_rejects_identical_files(self):
        self.write_manifest([
            ("men/25-34/man_25-34_0001.jpg", b"a"),
            ("men/25-34/man_25-34_0002.jpg", b"b"),
            ("men/35-44/man_35-44_0001.jpg", b"a"),
        ])
        with self.assertRaisesMessage(CommandError, "byte-identical"):
            replacer.read_manifest(self.manifest)

        photos = replacer.read_manifest(self.manifest, {"men/35-44/man_35-44_0001.jpg"})
        self.assertEqual(
            [path.name for path in photos[("male", "25-34")]],
            ["man_25-34_0001.jpg", "man_25-34_0002.jpg"],
        )
        self.assertNotIn(("male", "35-44"), photos)

    def test_read_manifest_rejects_exclusions_it_does_not_contain(self):
        self.write_manifest([("men/25-34/man_25-34_0001.jpg", b"a")])
        with self.assertRaisesMessage(CommandError, "missing from the manifest"):
            replacer.read_manifest(self.manifest, {"men/25-34/typo.jpg"})

    def test_commit_replaces_matched_photos_and_repoints_feed_items(self):
        self.write_manifest([
            ("men/25-34/man_25-34_0001.jpg", b"man"),
            ("women/65+/woman_65+_0001.jpg", b"older woman"),
            ("women/45-54/woman_45-54_0001.jpg", b"unused"),
        ])
        gage_30 = self.make_user("gage30", "Gage", 30)
        gage_31 = self.make_user("gage31", "Gage", 31)
        regina = self.make_user("regina70", "Regina", 70)
        rita = self.make_user("rita50", "Rita", 50)
        UserPicture.objects.create(user=rita, image_url="https://blob.test/second.jpg", order=1)
        matching_activity = FeedActivity.objects.create(
            user=regina, kind="photo_added", payload={"image_url": regina.profile_photo, "simulated": True}
        )
        other_activity = FeedActivity.objects.create(
            user=regina, kind="photo_added", payload={"image_url": "https://blob.test/other.jpg"}
        )

        dry_run = self.run_command()
        self.assertIn("Photos to replace: 2", dry_run)
        self.assertIn("Users with edited photos preserved: 1", dry_run)
        self.assertEqual(User.objects.get(id=regina.id).profile_photo, regina.profile_photo)

        uploader = FakeUploader()
        backup = self.root / "backup.csv"
        self.run_command("--commit", "--backup", str(backup), uploader=uploader)

        self.assertEqual(len(uploader.uploaded), 2)
        regina.refresh_from_db()
        self.assertTrue(regina.profile_photo.startswith("https://blob.test/photos/profile-photos/dummy-users/regina70-"))
        self.assertEqual(regina.pictures.get(order=0).image_url, regina.profile_photo)
        matching_activity.refresh_from_db()
        other_activity.refresh_from_db()
        self.assertEqual(matching_activity.payload, {"image_url": regina.profile_photo, "simulated": True})
        self.assertEqual(other_activity.payload, {"image_url": "https://blob.test/other.jpg"})

        men_changed = [
            user.username for user in User.objects.filter(id__in=[gage_30.id, gage_31.id])
            if user.profile_photo.startswith("https://blob.test/")
        ]
        self.assertEqual(len(men_changed), 1)
        self.assertEqual(User.objects.get(id=rita.id).profile_photo, rita.profile_photo)

        with backup.open(newline="") as backup_file:
            rows = list(csv.DictReader(backup_file))
        self.assertEqual({row["username"] for row in rows}, {"regina70", *men_changed})
        regina_row = next(row for row in rows if row["username"] == "regina70")
        self.assertEqual(regina_row["previous_url"], self.make_url("regina70"))
        self.assertEqual(regina_row["new_url"], regina.profile_photo)
        self.assertEqual(regina_row["feed_activity_ids"], str(matching_activity.id))

        rerun = self.run_command("--commit", "--backup", str(self.root / "backup-2.csv"))
        self.assertIn("Already replaced: 2", rerun)
        self.assertIn("Nothing to replace.", rerun)
        self.assertFalse((self.root / "backup-2.csv").exists())

    def test_previous_run_users_and_photos_are_left_alone(self):
        self.write_manifest([("women/65+/woman_65+_0001.jpg", b"older woman")])
        self.make_user("regina70", "Regina", 70)
        self.make_user("rita70", "Rita", 70)
        first_backup = self.root / "first.csv"
        self.run_command("--commit", "--backup", str(first_backup), expected_users=2)
        with first_backup.open(newline="") as backup_file:
            first_rows = list(csv.DictReader(backup_file))
        self.assertEqual(len(first_rows), 1)
        done = User.objects.get(id=first_rows[0]["user_id"])
        waiting = User.objects.exclude(id=done.id).get(is_dummy=True)

        self.write_manifest([
            ("women/65+/woman_65+_0001.jpg", b"older woman"),
            ("women/65+/woman_65+_0002.jpg", b"second older woman"),
        ])
        output = self.run_command(
            "--commit", "--backup", str(self.root / "second.csv"),
            "--previous", str(first_backup), expected_users=2,
        )

        self.assertIn("Finished in an earlier run: 1", output)
        done.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual(done.profile_photo, first_rows[0]["new_url"])
        second_digest = hashlib.sha256(b"second older woman").hexdigest()[:12]
        self.assertIn(f"-{second_digest}.jpg", waiting.profile_photo)

    def test_commit_refuses_to_overwrite_backup(self):
        self.write_manifest([("men/25-34/man_25-34_0001.jpg", b"man")])
        self.make_user("gage30", "Gage", 30)
        backup = self.root / "backup.csv"
        backup.write_text("keep me")
        with self.assertRaisesMessage(CommandError, "refusing to overwrite"):
            self.run_command("--commit", "--backup", str(backup), expected_users=1)

    def test_gender_answers_must_agree_with_first_name(self):
        self.write_manifest([("men/25-34/man_25-34_0001.jpg", b"man")])
        user = self.make_user("gage30", "Gage", 30)
        for number, me_answer in ((mq.FEMALE, 5), (mq.MALE, 1)):
            question = Question.objects.create(
                question_number=number, question_name=str(number), text=str(number),
                is_mandatory=True, is_approved=True,
            )
            UserAnswer.objects.create(user=user, question=question, me_answer=me_answer, looking_for_answer=3)
        with self.assertRaisesMessage(CommandError, "disagrees"):
            self.run_command(expected_users=1)

    def test_uploader_accepts_sas_token_without_account_key(self):
        env = {
            "NEXT_PUBLIC_STORAGE_NAME": "acct",
            "NEXT_PUBLIC_CONTAINER": "photos",
            "NEXT_PUBLIC_SAS_TOKEN": "?sv=2024-11-04&sp=rw&sig=abc",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(importer.settings, "AZURE_ACCOUNT_KEY", "", create=True):
            uploader = importer.AzureUploader.from_environment()
        blob = uploader.blob_service_client.get_container_client("photos").get_blob_client("x.jpg")
        self.assertEqual(uploader.container_name, "photos")
        self.assertIn("sig=abc", blob.url)
        self.assertTrue(blob.url.startswith("https://acct.blob.core.windows.net/photos/x.jpg?"))
