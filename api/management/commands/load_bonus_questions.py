import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.db import transaction

from api.models import Question, QuestionAnswer, QuestionNumberCounter, Tag
from api.utils.word_filter import validate_text_fields

VALID_TAGS = {'value', 'lifestyle', 'look', 'trait', 'hobby', 'interest'}
DEFAULT_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'bonus_questions_1000.json')


class Command(BaseCommand):
    help = 'Bulk-loads new optional (non-mandatory) matchmaking questions from a JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default=DEFAULT_DATA_FILE,
            help='Path to a JSON file of {text, tags, value_label_1, value_label_5} objects',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and report without writing to the database',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']

        try:
            with open(file_path) as f:
                items = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'Data file not found: {file_path}')

        self.stdout.write(f'Loaded {len(items)} question definitions from {file_path}')

        existing_texts = set(Question.objects.values_list('text', flat=True))

        to_create = []
        skipped_existing = 0
        skipped_invalid = 0

        for item in items:
            text = (item.get('text') or '').strip()
            tags = item.get('tags') or []
            v1 = (item.get('value_label_1') or '').strip()
            v5 = (item.get('value_label_5') or '').strip()

            if text in existing_texts:
                skipped_existing += 1
                continue

            if not text or len(text) > 100:
                skipped_invalid += 1
                continue
            if not (1 <= len(tags) <= 3) or not all(t in VALID_TAGS for t in tags):
                skipped_invalid += 1
                continue
            if not v1 or not v5:
                skipped_invalid += 1
                continue

            has_restricted, _ = validate_text_fields(text=text, question_name=text[:50])
            if has_restricted:
                skipped_invalid += 1
                continue

            to_create.append({'text': text, 'tags': tags, 'value_label_1': v1, 'value_label_5': v5})
            existing_texts.add(text)

        self.stdout.write(
            f'To create: {len(to_create)} | already present: {skipped_existing} | '
            f'invalid/filtered: {skipped_invalid}'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes made'))
            for item in to_create[:10]:
                self.stdout.write(f"  - {item['text']}")
            if len(to_create) > 10:
                self.stdout.write(f'  ... and {len(to_create) - 10} more')
            return

        if not to_create:
            self.stdout.write(self.style.SUCCESS('Nothing new to create.'))
            return

        tag_cache = {}
        created_count = 0

        with transaction.atomic():
            for item in to_create:
                question = Question.objects.create(
                    text=item['text'],
                    question_name=item['text'][:50],
                    question_number=QuestionNumberCounter.allocate_next_number(),
                    question_type='basic',
                    is_mandatory=False,
                    is_required_for_match=False,
                    is_approved=True,
                    skip_me=False,
                    skip_looking_for=False,
                    open_to_all_me=False,
                    open_to_all_looking_for=False,
                    is_group=False,
                )
                for tag_name in item['tags']:
                    tag = tag_cache.get(tag_name)
                    if tag is None:
                        tag, _ = Tag.objects.get_or_create(name=tag_name)
                        tag_cache[tag_name] = tag
                    question.tags.add(tag)

                answer_values = [
                    ('1', item['value_label_1'], 0),
                    ('2', '', 1),
                    ('3', '', 2),
                    ('4', '', 3),
                    ('5', item['value_label_5'], 4),
                ]
                for value, answer_text, order in answer_values:
                    QuestionAnswer.objects.create(
                        question=question, value=value, answer_text=answer_text, order=order
                    )
                created_count += 1

        cache.delete('questions_metadata_v2')

        self.stdout.write(self.style.SUCCESS(f'Created {created_count} new questions (cache invalidated).'))
