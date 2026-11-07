import json
import os
import re

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from api.models import Question, Tag

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
    help = 'Fill empty question tag sets from the bonus catalog, then from keywords. Existing tags are left alone.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=DEFAULT_DATA_FILE)
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

        # Empty tag sets, plus rows whose only tags sit outside the six filters
        # (family, career) and so never match a tag pill.
        untagged = (
            Question.objects.annotate(tag_count=Count('tags'))
            .filter(tag_count=0)
            .order_by('question_number', 'id')
        )
        standard = set(VALID_TAGS)
        outside = [
            question for question in Question.objects.prefetch_related('tags').order_by('question_number', 'id')
            if question.tags.exists() and not {tag.name for tag in question.tags.all()} & standard
        ]

        from_catalog = 0
        from_keywords = 0
        still_open = 0
        dry_run = options['dry_run']

        def choose_tags(question):
            return catalog.get((question.text or '').strip()) or _keyword_tags(
                ' '.join(part for part in (question.text, question.question_name, question.group_name) if part)
            )

        for question in untagged.iterator():
            names = choose_tags(question)
            if not names:
                still_open += 1
                continue
            if names == catalog.get((question.text or '').strip()):
                from_catalog += 1
            else:
                from_keywords += 1
            if not dry_run:
                question.tags.set([tag_rows[name] for name in names])

        # Keep family/career. Add a standard tag so the question also matches a filter pill.
        for question in outside:
            names = choose_tags(question)
            if not names:
                still_open += 1
                continue
            from_keywords += 1
            if not dry_run:
                question.tags.add(*[tag_rows[name] for name in names])

        if not dry_run and (from_catalog or from_keywords):
            cache.delete('questions_metadata_v2')

        self.stdout.write(
            f'catalog={from_catalog} keywords={from_keywords} still_untagged={still_open} dry_run={dry_run}'
        )
