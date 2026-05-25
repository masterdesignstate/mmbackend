from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from django.db import close_old_connections, transaction
from django.utils import timezone

from ..models import CompatibilityJob, User

logger = logging.getLogger(__name__)
_background_lock = threading.Lock()
_background_user_ids: set[str] = set()

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
        print(
            f"⏭️  Compatibility recalculation not queued for {user.username} ({user.id}): "
            f"{answer_count}/{MIN_MATCHABLE_ANSWERS} answers",
            flush=True,
        )
        return EnqueueResult(created=False, updated=False, skipped=True, reason="insufficient_answers")

    with transaction.atomic():
        job, created = CompatibilityJob.objects.select_for_update().get_or_create(
            user=user,
            defaults={'status': CompatibilityJob.STATUS_PENDING}
        )

        if created:
            print(f"📬 Queued compatibility recalculation for {user.username} ({user.id})", flush=True)
            return EnqueueResult(created=True, updated=False, skipped=False)

        if job.status != CompatibilityJob.STATUS_PENDING or force:
            job.status = CompatibilityJob.STATUS_PENDING
            job.error_message = ''
            job.updated_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'updated_at'])
            print(f"📬 Re-queued compatibility recalculation for {user.username} ({user.id})", flush=True)
            return EnqueueResult(created=False, updated=True, skipped=False)

        # Already pending; touch updated_at to reflect the new request
        job.updated_at = timezone.now()
        job.save(update_fields=['updated_at'])
        print(f"📬 Compatibility recalculation already pending for {user.username} ({user.id})", flush=True)
        return EnqueueResult(created=False, updated=False, skipped=False)


def process_user_compatibility_async(user_id: str) -> bool:
    """
    Start an in-process background worker for a user's pending compatibility job.

    The CompatibilityJob row remains the source of truth, so the scheduled
    management command can still pick up pending work if this process exits.
    """
    user_id = str(user_id)

    def start_thread():
        with _background_lock:
            if user_id in _background_user_ids:
                print(f"🧮 Background compatibility worker already running for user {user_id}", flush=True)
                return
            _background_user_ids.add(user_id)

        thread = threading.Thread(
            target=_process_user_compatibility_worker,
            args=(user_id,),
            daemon=True,
            name=f"compatibility-recalc-{user_id[:8]}",
        )
        thread.start()

    transaction.on_commit(start_thread)
    return True


def _process_user_compatibility_worker(user_id: str) -> None:
    from .compatibility_service import CompatibilityService

    close_old_connections()
    print(f"🧮 Background compatibility worker started for user {user_id}", flush=True)

    try:
        while True:
            with transaction.atomic():
                job = (
                    CompatibilityJob.objects
                    .select_for_update()
                    .select_related('user')
                    .filter(user_id=user_id, status=CompatibilityJob.STATUS_PENDING)
                    .first()
                )

                if not job:
                    break

                user = job.user
                answer_count = user.answers.count()

                if user.is_banned:
                    job.status = CompatibilityJob.STATUS_COMPLETED
                    job.error_message = 'User is banned; skipping compatibility generation'
                    job.save(update_fields=['status', 'error_message', 'updated_at'])
                    print(f"⏭️  Skipped compatibility recalculation for banned user {user.username} ({user.id})", flush=True)
                    break

                if answer_count < MIN_MATCHABLE_ANSWERS:
                    job.status = CompatibilityJob.STATUS_COMPLETED
                    job.error_message = 'Not enough answers to compute compatibility'
                    job.save(update_fields=['status', 'error_message', 'updated_at'])
                    print(
                        f"⏭️  Skipped compatibility recalculation for {user.username} ({user.id}): "
                        f"{answer_count}/{MIN_MATCHABLE_ANSWERS} answers",
                        flush=True,
                    )
                    break

                job.status = CompatibilityJob.STATUS_PROCESSING
                job.attempts += 1
                job.last_attempt_at = timezone.now()
                job.error_message = ''
                job.save(update_fields=['status', 'attempts', 'last_attempt_at', 'error_message', 'updated_at'])

            try:
                pairs_recalculated = CompatibilityService.recalculate_all_compatibilities(user, use_full_reset=False)
            except Exception as exc:
                logger.exception("Background compatibility recompute failed for user %s: %s", user_id, exc)
                with transaction.atomic():
                    failed_job = CompatibilityJob.objects.select_for_update().filter(user_id=user_id).first()
                    if failed_job:
                        failed_job.status = CompatibilityJob.STATUS_FAILED
                        failed_job.error_message = str(exc)[:500]
                        failed_job.updated_at = timezone.now()
                        failed_job.save(update_fields=['status', 'error_message', 'updated_at'])
                print(f"❌ Background compatibility recalculation failed for user {user_id}: {exc}", flush=True)
                break

            with transaction.atomic():
                completed_job = CompatibilityJob.objects.select_for_update().filter(user_id=user_id).first()
                if not completed_job:
                    break

                if completed_job.status == CompatibilityJob.STATUS_PENDING:
                    print(
                        f"🔁 Compatibility changed again while recalculating user {user_id}; running one more pass",
                        flush=True,
                    )
                    continue

                completed_job.status = CompatibilityJob.STATUS_COMPLETED
                completed_job.error_message = ''
                completed_job.updated_at = timezone.now()
                completed_job.save(update_fields=['status', 'error_message', 'updated_at'])

            print(
                f"✅ Background compatibility recalculation completed for user {user_id}: "
                f"{pairs_recalculated} pairs processed",
                flush=True,
            )
            break
    finally:
        with _background_lock:
            _background_user_ids.discard(user_id)
        close_old_connections()


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


def process_user_compatibility_immediately(user: User) -> dict:
    """
    Process compatibility recalculation for a single user immediately.
    This is used when a user updates their answers to provide real-time compatibility updates.

    Returns:
        dict with 'success', 'pairs_recalculated', and optionally 'error' keys
    """
    from .compatibility_service import CompatibilityService

    answer_count = user.answers.count()

    if answer_count < MIN_MATCHABLE_ANSWERS:
        return {
            'success': False,
            'pairs_recalculated': 0,
            'error': f'User needs at least {MIN_MATCHABLE_ANSWERS} answers (has {answer_count})'
        }

    if user.is_banned:
        return {
            'success': False,
            'pairs_recalculated': 0,
            'error': 'User is banned'
        }

    try:
        # Recalculate all compatibilities for this user
        pairs_recalculated = CompatibilityService.recalculate_all_compatibilities(user, use_full_reset=False)

        logger.info(f"✅ Immediately recalculated {pairs_recalculated} compatibility pairs for user {user.username} ({user.id})")

        # Mark any pending job as completed since we just processed it
        CompatibilityJob.objects.filter(
            user=user,
            status=CompatibilityJob.STATUS_PENDING
        ).update(
            status=CompatibilityJob.STATUS_COMPLETED,
            updated_at=timezone.now()
        )

        return {
            'success': True,
            'pairs_recalculated': pairs_recalculated
        }
    except Exception as e:
        logger.error(f"❌ Error recalculating compatibility for user {user.username} ({user.id}): {e}")
        return {
            'success': False,
            'pairs_recalculated': 0,
            'error': str(e)
        }
