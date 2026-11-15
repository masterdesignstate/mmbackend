import json
import os
import re

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F

from api.models import Question, Tag

# Non-mandatory questions past this count keep no tags.
OPTIONAL_TAG_LIMIT = 600

VALID_TAGS = ('value', 'lifestyle', 'look', 'trait', 'hobby', 'interest')
DEFAULT_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    'bonus_questions_1000.json',
)

# Word-boundary keywords. A question with no curated tag gets the categories that
# actually match its wording. Nothing is tagged when none of these fit.
KEYWORD_TAGS = (
    ('value', (
        'god', 'faith', 'religion', 'religious', 'pray', 'prayer', 'church', 'spiritual',
        'soul', 'moral', 'ethics', 'political', 'politics', 'vote', 'ideology', 'tradition',
        'meaning', 'purpose', 'fate', 'fated', 'afterlife', 'heaven', 'belief', 'values',
        'marriage', 'divorce', 'abortion',
    )),
    ('lifestyle', (
        'diet', 'food', 'cook', 'cooking', 'exercise', 'workout', 'gym', 'alcohol', 'drink',
        'drinking', 'smoke', 'smoking', 'cigarette', 'vape', 'sleep', 'routine', 'morning',
        'travel', 'vacation', 'habit', 'health', 'sober', 'nightlife', 'schedule', 'kids',
        'children', 'parenting', 'parent', 'education', 'school', 'degree',
        'college', 'university', 'career', 'job',
    )),
    ('look', (
        'attractive', 'attraction', 'height', 'fashion', 'hair', 'tattoo', 'muscle',
        'handsome', 'pretty', 'appearance', 'outfit', 'clothes', 'makeup', 'beard',
    )),
    ('trait', (
        'personality', 'introvert', 'extrovert', 'honest', 'honesty', 'kindness', 'humor',
        'funny', 'emotional', 'temper', 'patience', 'confident', 'confidence', 'shy',
        'loyal', 'loyalty', 'jealous', 'jealousy', 'ambitious', 'ambition', 'anxiety',
        'anxious', 'empathy', 'stubborn', 'romantic', 'affection', 'temperament',
    )),
    ('hobby', (
        'hobby', 'sport', 'sports', 'game', 'games', 'gaming', 'music', 'movie', 'movies',
        'book', 'books', 'reading', 'dance', 'dancing', 'hike', 'hiking', 'fishing',
        'garden', 'instrument', 'guitar', 'piano', 'yoga', 'photography', 'podcast',
    )),
    ('interest', (
        'science', 'history', 'culture', 'news', 'philosophy', 'language', 'languages',
        'technology', 'nature', 'animal', 'animals', 'curious', 'curiosity', 'learning',
        'space', 'astronomy',
    )),
)


def _keyword_tags(text):
    folded = (text or '').lower()
    scores = []
    for tag, words in KEYWORD_TAGS:
        hits = 0
        for word in words:
            if re.search(rf'\b{re.escape(word)}\b', folded):
                hits += 1
        if hits:
            scores.append((hits, tag))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [tag for _, tag in scores[:2]]


class Command(BaseCommand):
    help = 'Tag the first 600 non-mandatory questions. Later optional questions have their tags cleared. Mandatory questions are not changed.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=DEFAULT_DATA_FILE)
        parser.add_argument('--limit', type=int, default=OPTIONAL_TAG_LIMIT)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        try:
            with open(options['file']) as handle:
                items = json.load(handle)
        except FileNotFoundError:
            raise CommandError(f'Data file not found: {options["file"]}')

        catalog = {}
        for item in items:
            text = (item.get('text') or '').strip()
            tags = [tag for tag in (item.get('tags') or []) if tag in VALID_TAGS]
            if text and tags:
                catalog[text] = tags

        tag_rows = {tag.name: tag for tag in Tag.objects.filter(name__in=VALID_TAGS)}
        missing = [name for name in VALID_TAGS if name not in tag_rows]
        if missing:
            raise CommandError(f'Missing tag rows: {", ".join(missing)}. Run setup_database.py first.')

        limit = options['limit']
        dry_run = options['dry_run']
        # Question number order, with unnumbered rows last, so the 600 are the earliest optional questions.
        optional = list(
            Question.objects.filter(is_mandatory=False)
            .annotate(tag_count=Count('tags'))
            .order_by(F('question_number').asc(nulls_last=True), 'id')
        )
        keep = optional[:limit]
        rest = optional[limit:]

        def choose_tags(question):
            return catalog.get((question.text or '').strip()) or _keyword_tags(
                ' '.join(part for part in (question.text, question.question_name, question.group_name) if part)
            )

        filled = 0
        already = 0
        still_open = 0
        for question in keep:
            if question.tag_count:
                already += 1
                continue
            names = choose_tags(question)
            if not names:
                still_open += 1
                continue
            filled += 1
            if not dry_run:
                question.tags.set([tag_rows[name] for name in names])

        cleared = 0
        for question in rest:
            if not question.tag_count:
                continue
            cleared += 1
            if not dry_run:
                question.tags.clear()

        if not dry_run and (filled or cleared):
            cache.delete('questions_metadata_v2')

        self.stdout.write(
            f'kept={already} filled={filled} cleared={cleared} still_open={still_open} '
            f'limit={limit} dry_run={dry_run}'
        )
