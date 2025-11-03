from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..models import CompatibilityJob, User

MIN_MATCHABLE_ANSWERS = 10

# Hardcoded onboarding flow triggers (final step Kids questions)
ONBOARDING_TRIGGER_QUESTION_IDS = {
    # Want kids
    'b3d3b8c8-f1ef-43ce-8e36-1b78b75848c6',
    # Have kids
    '4be86e73-87be-4c81-a66a-5490255f3e3b',
}


@dataclass(frozen=True)
class EnqueueResult:
    created: bool
    updated: bool
    skipped: bool
    reason: Optional[str] = None


def enqueue_user_for_recalculation(user: User, force: bool = False) -> EnqueueResult:
    """
    Ensure the given user has a pending compatibility job when they are match-ready.
    Returns metadata about whether a new job was created, updated, or skipped.
    """
    answer_count = user.answers.count()

    if not force and answer_count < MIN_MATCHABLE_ANSWERS:
        return EnqueueResult(created=False, updated=False, skipped=True, reason="insufficient_answers")

    with transaction.atomic():
        job, created = CompatibilityJob.objects.select_for_update().get_or_create(
            user=user,
            defaults={'status': CompatibilityJob.STATUS_PENDING}
        )

        if created:
            return EnqueueResult(created=True, updated=False, skipped=False)

        if job.status != CompatibilityJob.STATUS_PENDING or force:
            job.status = CompatibilityJob.STATUS_PENDING
            job.error_message = ''
            job.updated_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'updated_at'])
            return EnqueueResult(created=False, updated=True, skipped=False)

        # Already pending; touch updated_at to reflect the new request
        job.updated_at = timezone.now()
        job.save(update_fields=['updated_at'])
        return EnqueueResult(created=False, updated=False, skipped=False)


def should_enqueue_after_answer(
    *,
    question_id: str,
    user: User,
    created: bool,
) -> tuple[bool, bool]:
    """
    Determine whether an answer submission should enqueue a compatibility job.

    Returns:
        should_enqueue (bool): Whether to call enqueue_user_for_recalculation
        force_enqueue (bool): Whether the enqueue should bypass pending status
    """
    match_ready = (user.questions_answered_count or 0) >= MIN_MATCHABLE_ANSWERS
    is_onboarding_trigger = question_id in ONBOARDING_TRIGGER_QUESTION_IDS

    if not created:
        # Updates to existing answers should immediately trigger a recalculation once the user is match-ready
        return (match_ready, match_ready)

    if not match_ready:
        return (False, False)

    if is_onboarding_trigger:
        # First time finishing onboarding: force ensures job resets to pending
        return (True, True)

    # Post-onboarding new answers (beyond initial 10) should enqueue normally
    if user.questions_answered_count > MIN_MATCHABLE_ANSWERS:
        return (True, False)

    return (False, False)
