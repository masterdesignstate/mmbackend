"""
Keep only N dummy accounts and N questions switched on.

Dummies are ranked youngest first and the rest are disabled, so the oldest go first.
Accounts with no birth date or age rank as oldest. Real users and admins are never touched.

Questions keep the first N distinct approved question numbers. The mandatory block is
always inside that set, so onboarding and Results completeness keep working.

Raising either limit later re-enables rows that fall back inside it.
"""

from datetime import date

from django.core.cache import cache
from django.db.models import Q

from api import mandatory_questions as mq
from api.models import Question, User
from api.services.dummy_activity import all_dummy_users_queryset

DISABLED_QUESTION_IDS_CACHE_KEY = 'disabled_question_ids_v1'
SCORING_VERSION_CACHE_KEY = 'compatibility_scoring_version'
QUESTIONS_METADATA_CACHE_KEY = 'questions_metadata_v2'


def disabled_question_ids():
    """Ids of disabled questions, cached because scoring asks for them on every pair."""
    ids = cache.get(DISABLED_QUESTION_IDS_CACHE_KEY)
    if ids is None:
        ids = frozenset(Question.objects.filter(is_disabled=True).values_list('id', flat=True))
        cache.set(DISABLED_QUESTION_IDS_CACHE_KEY, ids, 300)
    return ids


def scoring_version():
    """Part of every cached pair-score key, so one bump retires them all.

    The cache is per process, so a bump made by the management command never reaches the
    web server. The disabled set is in the key too, so the server's pair scores turn over
    once its own copy of that set refreshes.
    """
    return f'{cache.get(SCORING_VERSION_CACHE_KEY) or 1}.{hash(disabled_question_ids())}'


def invalidate_question_state():
    cache.delete(DISABLED_QUESTION_IDS_CACHE_KEY)
    cache.delete(QUESTIONS_METADATA_CACHE_KEY)
    cache.set(SCORING_VERSION_CACHE_KEY, (cache.get(SCORING_VERSION_CACHE_KEY) or 1) + 1, None)


def _age_sort_key(user, today):
    if user.date_of_birth:
        return (0, -user.date_of_birth.toordinal())
    if user.age is not None:
        approx_birth = date(today.year - user.age, today.month, min(today.day, 28))
        return (0, -approx_birth.toordinal())
    return (1, 0)


def limited_dummies_queryset():
    """Dummies the limit applies to. Admin accounts can carry the dummy flag; they are never disabled."""
    return all_dummy_users_queryset().exclude(Q(is_admin=True) | Q(is_staff=True))


def plan_dummy_limit(limit):
    """(ids to keep enabled, ids to disable), youngest dummies kept."""
    today = date.today()
    dummies = list(limited_dummies_queryset().only('id', 'date_of_birth', 'age'))
    dummies.sort(key=lambda user: (_age_sort_key(user, today), str(user.id)))
    keep = [user.id for user in dummies[:max(limit, 0)]]
    drop = [user.id for user in dummies[max(limit, 0):]]
    return keep, drop


def plan_question_limit(limit):
    """(question numbers kept, question numbers disabled)."""
    numbers = sorted(
        number for number in Question.objects.filter(
            is_approved=True, question_number__isnull=False,
        ).values_list('question_number', flat=True).distinct()
    )
    mandatory = [n for n in numbers if n in mq.MANDATORY_QUESTION_NUMBERS]
    optional = [n for n in numbers if n not in mq.MANDATORY_QUESTION_NUMBERS]
    room = max(limit - len(mandatory), 0)
    keep = mandatory + optional[:room]
    drop = optional[room:]
    return keep, drop


def apply_dummy_limit(limit):
    keep, drop = plan_dummy_limit(limit)
    enabled = User.objects.filter(id__in=keep, is_disabled=True).update(is_disabled=False)
    disabled = User.objects.filter(id__in=drop, is_disabled=False).update(is_disabled=True)
    return {'kept': len(keep), 'disabled': len(drop), 'newly_enabled': enabled, 'newly_disabled': disabled}


def apply_question_limit(limit):
    keep, drop = plan_question_limit(limit)
    enabled = Question.objects.filter(
        Q(question_number__in=keep) | Q(question_number__isnull=True), is_disabled=True,
    ).update(is_disabled=False)
    disabled = Question.objects.filter(
        question_number__in=drop, is_disabled=False, is_mandatory=False,
    ).update(is_disabled=True)
    if enabled or disabled:
        invalidate_question_state()
    return {'kept': len(keep), 'disabled': len(drop), 'newly_enabled': enabled, 'newly_disabled': disabled}


def active_limit_counts():
    dummies = limited_dummies_queryset()
    numbers = Question.objects.filter(is_approved=True, question_number__isnull=False)
    return {
        'dummies_enabled': dummies.filter(is_disabled=False).count(),
        'dummies_disabled': dummies.filter(is_disabled=True).count(),
        'untouched_users': User.objects.count() - dummies.count(),
        'questions_enabled': numbers.filter(is_disabled=False).values('question_number').distinct().count(),
        'questions_disabled': numbers.filter(is_disabled=True).values('question_number').distinct().count(),
    }


def recalculate_enabled_users(log=print):
    """Rescore every pair between enabled users once, loading answers a single time."""
    from api.models import UserAnswer, UserRequiredQuestion
    from api.services.compatibility_service import CompatibilityService

    users = list(User.objects.filter(is_disabled=False, is_banned=False, answers__isnull=False).distinct())
    user_ids = [user.id for user in users]

    answers_by_user = {}
    answers = UserAnswer.objects.filter(
        user_id__in=user_ids, question__is_disabled=False,
    ).select_related('question').only(
        'user_id', 'question_id', 'question__question_number',
        'me_answer', 'me_open_to_all', 'me_importance',
        'looking_for_answer', 'looking_for_open_to_all', 'looking_for_importance',
    )
    for answer in answers.iterator(chunk_size=5000):
        answers_by_user.setdefault(str(answer.user_id), []).append(answer)

    required_by_user = {}
    for uid, qid in UserRequiredQuestion.objects.filter(
        user_id__in=user_ids, question__is_disabled=False,
    ).values_list('user_id', 'question_id'):
        required_by_user.setdefault(str(uid), set()).add(qid)

    # Each call scores the user against everyone after them, so every pair is scored once.
    for index, user in enumerate(users):
        later = users[index + 1:]
        if later:
            CompatibilityService.recalculate_all_compatibilities(
                user,
                use_full_reset=False,
                other_users=later,
                answers_by_user=answers_by_user,
                required_by_user=required_by_user,
            )
        log(f'Rescored {index + 1}/{len(users)}: {user.username}')
    return len(users)


def recalculate_enabled_users_in_background():
    """A full rescore takes minutes, longer than any request may wait."""
    import threading

    from django.db import close_old_connections

    def run():
        close_old_connections()
        try:
            recalculate_enabled_users()
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True, name='active-limits-rescore').start()


def enqueue_full_recalculation():
    """Queue every enabled user with answers. The background worker drains the queue."""
    from api.services.compatibility_queue import enqueue_user_for_recalculation

    users = User.objects.filter(is_disabled=False, is_banned=False, answers__isnull=False).distinct()
    count = 0
    for user in users.iterator():
        enqueue_user_for_recalculation(user, force=True)
        count += 1
    return count
