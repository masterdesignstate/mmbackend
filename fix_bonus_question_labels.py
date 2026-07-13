#!/usr/bin/env python
"""
Corrects the 1000 bonus questions' answer labels to the site's established
convention (value 1 = "Less", value 5 = "More") instead of the bespoke
per-question antonym pairs they were loaded with. Matches bonus_questions_1000.json
by question text. Idempotent: skips questions already set to Less/More.

Questions phrased as an explicit two-option choice ("Would you rather X or Y",
"X or Y?") keep their bespoke labels instead, since "Less/More" doesn't read
naturally for a named-alternative choice. Everything else (the "how much/how
often/how important" single-axis majority) converts.

Usage:
    python fix_bonus_question_labels.py --dry-run   # report only, no writes
    python fix_bonus_question_labels.py              # apply the fix
"""
import json
import os
import re
import sys

import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from django.core.cache import cache
from django.db import transaction

from api.models import Question, QuestionAnswer

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bonus_questions_1000.json')


def is_binary_choice(text):
    t = text.lower()
    if t.startswith('would you rather'):
        return True
    if re.search(r'\bor\b', t):
        return True
    return False


def main():
    dry_run = '--dry-run' in sys.argv

    with open(DATA_FILE) as f:
        bonus_texts = [item['text'] for item in json.load(f)]

    questions = Question.objects.filter(text__in=bonus_texts).prefetch_related('answers')
    print(f'Matched {questions.count()} of {len(bonus_texts)} bonus question texts in the database.')

    to_update = []
    already_correct = 0
    kept_custom = 0
    for q in questions:
        if is_binary_choice(q.text):
            kept_custom += 1
            continue
        answers = {a.value: a for a in q.answers.all()}
        a1, a5 = answers.get('1'), answers.get('5')
        if not a1 or not a5:
            continue
        if a1.answer_text == 'Less' and a5.answer_text == 'More':
            already_correct += 1
            continue
        to_update.append((q, a1, a5))

    print(f'Kept custom (binary-choice phrasing): {kept_custom}')
    print(f'Already Less/More: {already_correct}')
    print(f'To update: {len(to_update)}')

    if dry_run:
        print('\nDRY RUN — no changes made. Sample of planned changes:')
        for q, a1, a5 in to_update[:15]:
            print(f'  {q.text[:60]!r}: {a1.answer_text!r}/{a5.answer_text!r} -> Less/More')
        if len(to_update) > 15:
            print(f'  ... and {len(to_update) - 15} more')
        return

    if not to_update:
        print('Nothing to update.')
        return

    with transaction.atomic():
        for q, a1, a5 in to_update:
            a1.answer_text = 'Less'
            a1.save(update_fields=['answer_text'])
            a5.answer_text = 'More'
            a5.save(update_fields=['answer_text'])

    cache.delete('questions_metadata_v2')
    print(f'\nUpdated {len(to_update)} questions to Less/More (cache invalidated).')


if __name__ == '__main__':
    main()
