from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..models import CompatibilityJob, User

MIN_MATCHABLE_ANSWERS = 10


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
