"""
Generated Faith and Ideology answers, for accounts that never answered them.

Faith (15) and Ideology (16) were optional until September 2026, so almost no account had
answered them. Making them mandatory would have hidden every such account from Results, so
``backfill_faith_ideology`` fills them in first, and ``import_dummy_users`` uses the same plan
for new seed accounts.

Each account gets one primary option at strength 3-5, drawn from a weighted mix and stable per
account, and every other option at 1 — the shape the Questions editor saves for a grouped pick.
"Looking for" is open to all, so the partner side stays neutral and existing compatibility
barely moves.
"""

import hashlib
from dataclasses import dataclass

from api import mandatory_questions as mq

GENERATED_QUESTION_NUMBERS = (mq.FAITH, mq.IDEOLOGY)

OPEN_TO_ALL_ANSWER = 6
NON_PRIMARY_ANSWER = 1

# A rough US adult mix. An option missing here (renamed or added later) gets weight 1.
FAITH_WEIGHTS = {
    'Christian': 45,
    'Spiritual': 12,
    'Agnostic': 9,
    'Nonspiritual': 9,
    'Atheist': 7,
    'Other': 5,
    'Jewish': 3,
    'Muslim': 2,
    'Hindu': 2,
    'Buddhist': 2,
    'Pagan': 1,
}
IDEOLOGY_WEIGHTS = {
    'Moderate': 34,
    'Left': 28,
    'Right': 26,
    'Apolitical': 8,
    'Non-binary': 2,
    'Anarchist': 2,
}
WEIGHTS_BY_NUMBER = {mq.FAITH: FAITH_WEIGHTS, mq.IDEOLOGY: IDEOLOGY_WEIGHTS}

# How strongly the account identifies with its primary pick: mostly strong.
PRIMARY_STRENGTH_WEIGHTS = {5: 5, 4: 3, 3: 2}


@dataclass(frozen=True)
class GeneratedAnswer:
    question: object
    me_answer: int
    is_primary: bool
    looking_for_answer: int = OPEN_TO_ALL_ANSWER
    looking_for_open_to_all: bool = True


def stable_int(*parts):
    digest = hashlib.sha256(':'.join(str(part) for part in parts).encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def _weighted_pick(options, weight_of, *key):
    total = sum(weight_of(option) for option in options)
    roll = stable_int(*key) % total
    for option in options:
        roll -= weight_of(option)
        if roll < 0:
            return option
    return options[-1]


def plan_generated_answers(account_key, question_number, questions, seed):
    """One answer per option row of a grouped question, for one account.

    ``account_key`` only has to be stable for the account (its id, or a username before the
    account exists); the same key and seed always produce the same answers.
    """
    rows = sorted(questions, key=lambda question: (question.group_number or 0, question.question_name or ''))
    if not rows:
        return []

    weights = WEIGHTS_BY_NUMBER.get(question_number, {})
    primary = _weighted_pick(
        rows, lambda question: weights.get(question.question_name, 1),
        seed, account_key, question_number, 'primary',
    )
    strength = _weighted_pick(
        sorted(PRIMARY_STRENGTH_WEIGHTS), PRIMARY_STRENGTH_WEIGHTS.get,
        seed, account_key, question_number, 'strength',
    )
    return [
        GeneratedAnswer(
            question=question,
            me_answer=strength if question.pk == primary.pk else NON_PRIMARY_ANSWER,
            is_primary=question.pk == primary.pk,
        )
        for question in rows
    ]
