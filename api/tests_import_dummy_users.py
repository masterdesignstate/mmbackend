import csv
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.management.commands import import_dummy_users as importer
from api.models import Question, QuestionAnswer


class ImportDummyUsersTests(TestCase):
    def create_question(self, number, name, group_number=None, values=None):
        question = Question.objects.create(
            question_number=number,
            group_number=group_number,
            question_name=name,
            group_name={
                1: "Relationship",
                2: "Gender",
                3: "Ethnicity",
                4: "Education",
                5: "Diet",
                6: "Exercise",
                7: "Habits",
                10: "Kids",
            }.get(number, ""),
            text=f"{number} {name}",
            is_mandatory=True,
            is_approved=True,
        )
        for order, value in enumerate(values or [1, 2, 3, 4, 5], start=1):
            QuestionAnswer.objects.create(
                question=question,
                value=str(value),
                answer_text=str(value),
                order=order,
            )
        return question

    def create_mandatory_questions(self):
        Question.objects.all().delete()
        for group, name in enumerate(["Friend", "Hookup", "Date", "Partner"], start=1):
            self.create_question(1, name, group)
        for group, name in enumerate(["Male", "Female"], start=1):
            self.create_question(2, name, group)
        for group, name in enumerate(["White", "Black", "Native", "Hispanic", "Asian", "Other"], start=1):
            self.create_question(3, name, group)
        for group, name in enumerate(
            ["Pre High School", "High School", "Trade", "Undergraduate", "Masters", "Doctorate"],
            start=1,
        ):
            self.create_question(4, name, group, values=[1, 3, 5])
        for group, name in enumerate(["Omnivore", "Pescatarian", "Vegetarian", "Vegan"], start=1):
            self.create_question(5, name, group)
        self.create_question(6, "Exercise")
        for group, name in enumerate(["Alcohol", "Cigarettes", "Vape"], start=1):
            self.create_question(7, name, group)
        self.create_question(8, "Religion")
        self.create_question(9, "Politics")
        self.create_question(10, "Have", 1, values=[1, 5])
        self.create_question(10, "Want", 2)

    def test_resolve_genders_requires_exact_500_500_split(self):
        rows = [{"first_name": "Adam", "gender": "male"} for _ in range(500)]
        rows += [{"first_name": "Emma", "gender": "female"} for _ in range(500)]

        self.assertEqual(importer.resolve_genders(rows), {"male": 500, "female": 500})

        rows[0] = {"first_name": "Emma", "gender": "female"}
        with self.assertRaises(CommandError):
            importer.resolve_genders(rows)

    def test_build_mandatory_answers_normalizes_grouped_values(self):
        self.create_mandatory_questions()
        questions = importer.load_mandatory_questions()
        row = importer.ImportRow(
            row_number=4,
            photo_index=1,
            first_name="Adam",
            last_name="Tester",
            username="adamtester",
            tagline="tag",
            date_of_birth=date(1990, 1, 1),
            live="Austin",
            bio="bio",
            answers={
                "1b": 6,
                "2a": 3,
                "2b": 6,
                "3a": 5,
                "3b": 6,
                "4a": 2,
                "4b": 4,
                "5a": 4,
                "5b": 6,
                "6a": 4,
                "6b": 6,
                "7a": 2,
                "7b": 4,
                "8a": 3,
                "8b": 6,
                "9a": 5,
                "9b": 6,
                "10a": 2,
                "10b": 4,
            },
            gender="male",
            height=180,
            from_location="Texas",
        )

        answers = importer.build_mandatory_answers(row, questions)

        self.assertEqual(len(answers), 30)
        for answer in answers:
            valid = {int(option.value) for option in answer.question.answers.all()}
            if answer.me_open_to_all:
                self.assertEqual(answer.me_answer, 6)
            else:
                self.assertIn(answer.me_answer, valid)
            if answer.looking_for_open_to_all:
                self.assertEqual(answer.looking_for_answer, 6)
            else:
                self.assertIn(answer.looking_for_answer, valid)

        by_name = {(a.question.question_number, a.question.question_name): a for a in answers}
        self.assertEqual(by_name[(1, "Friend")].me_answer, 5)
        self.assertEqual(by_name[(1, "Hookup")].looking_for_answer, 1)
        self.assertEqual(by_name[(2, "Male")].me_answer, 5)
        self.assertEqual(by_name[(2, "Female")].me_answer, 1)
        self.assertTrue(by_name[(2, "Male")].looking_for_open_to_all)
        self.assertEqual(by_name[(4, "Masters")].me_answer, 1)
        self.assertEqual(by_name[(4, "Masters")].looking_for_answer, 5)
        self.assertEqual(by_name[(7, "Alcohol")].me_answer, 1)
        self.assertEqual(by_name[(7, "Alcohol")].looking_for_answer, 5)
        self.assertEqual(by_name[(10, "Have")].me_answer, 1)
        self.assertEqual(by_name[(10, "Have")].looking_for_answer, 5)
        self.assertEqual(by_name[(10, "Want")].me_answer, 2)
        self.assertEqual(by_name[(10, "Want")].looking_for_answer, 4)

    def write_large_csv(self, path):
        headers = [
            "Photos",
            "",
            "First",
            "Last",
            "Username",
            "Tag Line",
            "DOB",
            "Live",
            "Bio",
            "Height",
            "From",
            "",
            "",
            "1b",
        ]
        headers += [f"{number}{suffix}" for number in range(2, 11) for suffix in ("a", "b")]
        with path.open("w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow([""] * len(headers))
            writer.writerow([""] * len(headers))
            writer.writerow(headers)
            for index in range(1000):
                is_male = index < 500
                first = "Adam" if is_male else "Emma"
                username = f"{first.lower()}{index:04d}"
                row = [
                    "",
                    str(index + 1),
                    first,
                    "Tester",
                    username,
                    "short tag",
                    "1/1/90",
                    "Austin",
                    "A short bio",
                    "",
                    "",
                    "",
                    "",
                    "5",
                ]
                row += [
                    "3",
                    "6",
                    "5",
                    "6",
                    "3",
                    "6",
                    "4",
                    "6",
                    "4",
                    "6",
                    "5",
                    "6",
                    "3",
                    "6",
                    "4",
                    "6",
                    "2",
                    "4",
                ]
                writer.writerow(row)

    def create_photo_dir(self, root, name):
        directory = root / name
        directory.mkdir()
        for index in range(500):
            (directory / f"{name}_{index:04d}.jpg").write_bytes(f"photo-{name}-{index}".encode())
        return directory

    def test_command_dry_run_validates_full_import_plan(self):
        self.create_mandatory_questions()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "dummy.csv"
            self.write_large_csv(csv_path)
            men_dir = self.create_photo_dir(root, "men")
            women_dir = self.create_photo_dir(root, "women")

            class FakeUploader:
                container_name = "photos"

                def validate(self):
                    return None

            output = StringIO()
            with patch.object(importer.AzureUploader, "from_environment", return_value=FakeUploader()):
                call_command(
                    "import_dummy_users",
                    "--csv",
                    str(csv_path),
                    "--men-dir",
                    str(men_dir),
                    "--women-dir",
                    str(women_dir),
                    "--dry-run",
                    stdout=output,
                )

        rendered = output.getvalue()
        self.assertIn("CSV rows: 1000", rendered)
        self.assertIn("Gender split: 500 men, 500 women", rendered)
        self.assertIn("Mandatory answers: 30000", rendered)
