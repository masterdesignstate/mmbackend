import csv
from pathlib import Path

from django.test import SimpleTestCase

from api.tagline_rewrites import MAX_TAGLINE_LENGTH, rewrite_tagline


class TaglineRewriteTests(SimpleTestCase):
    def test_short_tagline_is_unchanged(self):
        tagline = "Finding magic in the little things."
        self.assertEqual(rewrite_tagline(tagline), tagline)

    def test_known_cutoff_is_rewritten_as_complete_copy(self):
        self.assertEqual(
            rewrite_tagline("Chasing love, laughter, and unforgettable moments."),
            "Chasing love, laughs & great memories.",
        )

    def test_all_import_source_taglines_have_safe_rewrites(self):
        source_path = Path("/Users/dimi/Downloads/Notes_Dimi - Dummy.csv")
        if not source_path.exists():
            self.skipTest("Local dummy-user source CSV is unavailable.")

        with source_path.open(newline="", encoding="utf-8-sig") as source_file:
            rows = list(csv.reader(source_file))
        headers = {value.strip(): index for index, value in enumerate(rows[2])}
        taglines = [
            row[headers["Tag Line"]].strip()
            for row in rows[3:]
            if any(cell.strip() for cell in row)
        ]

        rewritten = [rewrite_tagline(tagline) for tagline in taglines]
        self.assertTrue(all(value for value in rewritten))
        self.assertTrue(all(len(value) <= MAX_TAGLINE_LENGTH for value in rewritten))
        self.assertEqual(len([value for value in taglines if len(value) > 40]), 273)
