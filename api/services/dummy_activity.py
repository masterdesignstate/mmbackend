import hashlib
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from api.analytics import capture as posthog_capture
from api.models import (
    Controls,
    FeedActivity,
    Notification,
    Post,
    PostImage,
    Question,
    User,
    UserAnswer,
    UserPicture,
    UserRequiredQuestion,
    UserResult,
)
from api.services.compatibility_queue import (
    MIN_MATCHABLE_ANSWERS,
    enqueue_user_for_recalculation,
    process_user_compatibility_async,
)
from api.utils.hashtags import extract_hashtags


DUMMY_EMAIL_DOMAIN = "dummy.matchmatical.local"
PROTECTED_QUESTION_USERNAMES = {"oliviastacey", "jackperez"}

POST_BODIES = [
    "Trying a new coffee spot before work today. #coffee",
    "Long walk, good playlist, better mood. #wellness",
    "Found a quiet corner of the city I had never noticed before. #local",
    "Cooking something new tonight and hoping it turns out as good as it smells. #food",
    "Weekend plans are starting to come together. #weekend",
    "Resetting the week with a clean apartment and fresh groceries. #life",
    "A small change of scenery made the whole day better. #travel",
    "Keeping things simple today: movement, food, and a little sun. #wellness",
]

IMAGE_POST_BODIES = [
    "A favorite photo from recently.",
    "Keeping this one in the rotation.",
    "New angle, same me.",
    "A little update for the feed.",
]

BIO_SNIPPETS = [
    "Currently into slow mornings, good conversation, and trying one new place every week.",
    "Looking for someone kind, curious, and easy to laugh with.",
    "Big fan of coffee walks, thoughtful questions, and low-pressure plans.",
    "Trying to say yes to more live music, weekend trips, and dinner with friends.",
    "Here for genuine connection, shared humor, and people who follow through.",
]


def _stable_int(*parts):
    value = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _stable_percent(*parts):
    return _stable_int(*parts) % 100


def is_dummy_user(user):
    """User.is_dummy is the source of truth. The email-domain check is kept only
    as a fallback for accounts created before the flag existed and never
    backfilled (e.g. a fixture loaded from an old dump).
    """
    if not user:
        return False
    if user.is_dummy:
        return True
    return (user.email or "").lower().endswith(f"@{DUMMY_EMAIL_DOMAIN}")


def dummy_users_queryset():
    """Simulated accounts, which the feed-activity simulator may post as."""
    return User.objects.filter(
        Q(is_dummy=True) | Q(email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}"),
        is_active=True,
        is_banned=False,
    )


def non_dummy_users_queryset():
    """Real signups. The required-question catch-up acts only on these, so the
    simulator never fabricates answers on a simulated profile.

    Note this is deliberately NOT the complement of dummy_users_queryset() over
    all rows -- it applies the same is_active/is_banned gating, so a banned real
    user is in neither set.
    """
    return User.objects.filter(
        is_dummy=False,
        is_active=True,
        is_banned=False,
    ).exclude(email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}")


def _local_day_bounds(now):
    local_now = timezone.localtime(now)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _slot_time(day_start, daily_minimum, slot_index):
    seconds = int(((slot_index + Decimal("0.5")) / Decimal(daily_minimum)) * Decimal(24 * 60 * 60))
    return day_start + timedelta(seconds=seconds)


def due_dummy_feed_count(now=None, daily_minimum=20):
    now = now or timezone.now()
    day_start, _ = _local_day_bounds(now)
    return sum(
        1
        for index in range(max(0, daily_minimum))
        if _slot_time(day_start, daily_minimum, index) <= now
    )


def count_existing_dummy_feed_items(now=None):
    now = now or timezone.now()
    day_start, day_end = _local_day_bounds(now)
    dummy_ids = dummy_users_queryset().values("id")
    posts = Post.objects.filter(
        author_id__in=dummy_ids,
        created_at__gte=day_start,
        created_at__lt=day_end,
        is_deleted=False,
    ).count()
    activities = FeedActivity.objects.filter(
        user_id__in=dummy_ids,
        created_at__gte=day_start,
        created_at__lt=day_end,
    ).count()
    return posts + activities


def _choose_dummy_user(seed, *, exclude_question_protected=False):
    users = list(dummy_users_queryset().order_by("username", "id"))
    if exclude_question_protected:
        users = [user for user in users if user.username.lower() not in PROTECTED_QUESTION_USERNAMES]
    if not users:
        return None
    return users[_stable_int(seed, "dummy-user") % len(users)]


def _choose_photo_url(user):
    picture = UserPicture.objects.filter(user=user).order_by("order", "created_at").first()
    return (picture.image_url if picture else None) or user.profile_photo


def _set_created_at(obj, created_at):
    obj.__class__.objects.filter(id=obj.id).update(created_at=created_at)
    obj.created_at = created_at


def _sync_post_hashtags(post):
    tags = set(extract_hashtags(post.body or ""))
    if tags:
        from api.models import PostHashtag

        PostHashtag.objects.bulk_create([
            PostHashtag(post=post, tag=tag)
            for tag in tags
        ], ignore_conflicts=True)


def _create_text_post(user, seed, created_at):
    body = POST_BODIES[_stable_int(seed, "body") % len(POST_BODIES)]
    post = Post.objects.create(author=user, body=body, visibility="all")
    _sync_post_hashtags(post)
    _set_created_at(post, created_at)
    Post.objects.filter(id=post.id).update(updated_at=created_at)
    return post


def _create_image_post(user, seed, created_at):
    image_url = _choose_photo_url(user)
    if not image_url:
        return _create_text_post(user, seed, created_at)
    body = IMAGE_POST_BODIES[_stable_int(seed, "image-body") % len(IMAGE_POST_BODIES)]
    post = Post.objects.create(author=user, body=body, visibility="all")
    PostImage.objects.create(post=post, image_url=image_url, order=0)
    _set_created_at(post, created_at)
    Post.objects.filter(id=post.id).update(updated_at=created_at)
    return post


def _create_bio_update(user, seed, created_at):
    snippet = BIO_SNIPPETS[_stable_int(seed, "bio") % len(BIO_SNIPPETS)]
    user.bio = snippet
    user.save(update_fields=["bio"])
    activity = FeedActivity.objects.create(
        user=user,
        kind="bio_updated",
        payload={"snippet": snippet[:160]},
    )
    _set_created_at(activity, created_at)
    return activity


def _create_photo_activity(user, seed, created_at):
    image_url = _choose_photo_url(user)
    if not image_url:
        return _create_text_post(user, seed, created_at)
    activity = FeedActivity.objects.create(
        user=user,
        kind="photo_added",
        payload={"image_url": image_url, "simulated": True},
    )
    _set_created_at(activity, created_at)
    return activity


def _answer_values_for_question(question):
    values = []
    for raw_value in question.answers.values_list("value", flat=True):
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 5:
            values.append(value)
    return values or [1, 2, 3, 4, 5]


def _choose_question(seed):
    questions = list(
        Question.objects.filter(is_approved=True, is_mandatory=False)
        .prefetch_related("answers")
        .order_by("question_number", "group_number", "question_name", "id")
    )
    if not questions:
        questions = list(
            Question.objects.filter(is_approved=True)
            .prefetch_related("answers")
            .order_by("question_number", "group_number", "question_name", "id")
        )
    if not questions:
        return None
    return questions[_stable_int(seed, "question") % len(questions)]


def _create_question_answer(user, seed, created_at):
    question = _choose_question(seed)
    if not question:
        return _create_text_post(user, seed, created_at)

    values = _answer_values_for_question(question)
    me_answer = values[_stable_int(seed, "me") % len(values)]
    looking_for_answer = values[_stable_int(seed, "them") % len(values)]

    answer, _ = UserAnswer.objects.update_or_create(
        user=user,
        question=question,
        defaults={
            "me_answer": me_answer,
            "me_open_to_all": False,
            "me_importance": 3,
            "me_share": True,
            "looking_for_answer": looking_for_answer,
            "looking_for_open_to_all": False,
            "looking_for_importance": 3,
            "looking_for_share": True,
            "excluded_answer_values": [],
        },
    )
    User.objects.filter(id=user.id).update(questions_answered_count=UserAnswer.objects.filter(user=user).count())
    _set_created_at(answer, created_at)

    activity = FeedActivity.objects.create(
        user=user,
        kind="question_answered",
        payload={"question_id": str(question.id), "question_text": question.text or ""},
    )
    _set_created_at(activity, created_at)
    return activity


ACTIVITY_CREATORS = [
    ("text_post", _create_text_post, False),
    ("image_post", _create_image_post, False),
    ("bio_update", _create_bio_update, False),
    ("photo_added", _create_photo_activity, False),
    ("question_answered", _create_question_answer, True),
]


@transaction.atomic
def fill_due_dummy_feed_activity(now=None, daily_minimum=20, ignore_controls=False):
    now = now or timezone.now()
    daily_minimum = max(1, int(daily_minimum))
    day_start, _ = _local_day_bounds(now)

    if not ignore_controls and not Controls.get_current().auto_updater_enabled:
        return {
            "due": 0,
            "existing": 0,
            "created": 0,
            "daily_minimum": daily_minimum,
            "skipped": "disabled",
        }

    due = due_dummy_feed_count(now=now, daily_minimum=daily_minimum)
    existing = count_existing_dummy_feed_items(now=now)
    missing = max(0, due - existing)
    created = []

    for item_index in range(existing, existing + missing):
        kind, creator, exclude_question_protected = ACTIVITY_CREATORS[item_index % len(ACTIVITY_CREATORS)]
        seed = f"{day_start.date()}:{item_index}:{kind}"
        user = _choose_dummy_user(seed, exclude_question_protected=exclude_question_protected)
        if not user:
            break
        created_at = min(_slot_time(day_start, daily_minimum, item_index), now)
        created.append(creator(user, seed, created_at))

    return {
        "due": due,
        "existing": existing,
        "created": len(created),
        "daily_minimum": daily_minimum,
        "skipped": None,
    }


def _required_question_gaps(users, *, before=None):
    """Return {user_id: set(question_id)} of required-but-unanswered questions
    for the given users, in two bulk queries (not one query per user).

    If `before` is given, only UserRequiredQuestion/UserAnswer rows created
    before that cutoff are considered -- used to compute a day-stable
    prioritization snapshot that ignores writes made by this job today.
    """
    user_ids = [user.id for user in users]
    required_qs = UserRequiredQuestion.objects.filter(user_id__in=user_ids)
    answered_qs = UserAnswer.objects.filter(user_id__in=user_ids)
    if before is not None:
        required_qs = required_qs.filter(created_at__lt=before)
        answered_qs = answered_qs.filter(created_at__lt=before)

    required_map = defaultdict(set)
    for user_id, question_id in required_qs.values_list("user_id", "question_id"):
        required_map[user_id].add(question_id)

    answered_map = defaultdict(set)
    for user_id, question_id in answered_qs.values_list("user_id", "question_id"):
        answered_map[user_id].add(question_id)

    return {
        user_id: required_map[user_id] - answered_map[user_id]
        for user_id in required_map
    }


def _select_required_catchup_users(day_start, daily_count):
    """Deterministically pick up to `daily_count` non-protected REAL (non-dummy)
    users for today's required-question catch-up. Users who had a required-but-
    unanswered question as of the start of today are prioritized; the rest
    are used as harmless filler if not enough users have a gap. The ranking
    is a pure function of (day_start.date(), user.id), so it is identical
    across every invocation within the same day.

    Dummy accounts are deliberately excluded: the simulator must not fabricate
    required-question answers on seeded profiles. Until real signups exist this
    returns an empty list, which is expected and not an error.
    """
    if daily_count <= 0:
        return []

    candidates = [
        user for user in non_dummy_users_queryset().order_by("username", "id")
        if user.username.lower() not in PROTECTED_QUESTION_USERNAMES
    ]
    if not candidates:
        return []

    gaps_at_day_start = _required_question_gaps(candidates, before=day_start)

    def rank_key(user):
        return _stable_int(day_start.date(), user.id, "required-catchup-order")

    with_gap, without_gap = [], []
    for user in candidates:
        (with_gap if gaps_at_day_start.get(user.id) else without_gap).append(user)

    with_gap.sort(key=rank_key)
    without_gap.sort(key=rank_key)

    return (with_gap + without_gap)[:daily_count]


def _required_answer_defaults(question, seed):
    """Build a UserAnswer defaults dict for a required-question catch-up
    answer, mirroring _create_question_answer's answer-building logic.
    """
    values = _answer_values_for_question(question)
    me_answer = 1 if question.skip_me else values[_stable_int(seed, "me") % len(values)]
    looking_for_answer = 1 if question.skip_looking_for else values[_stable_int(seed, "them") % len(values)]
    me_open_to_all = False
    looking_for_open_to_all = False

    if not question.skip_me and question.open_to_all_me and _stable_percent(seed, "open-to-all-me") < 10:
        me_answer, me_open_to_all = 6, True
    if not question.skip_looking_for and question.open_to_all_looking_for and _stable_percent(seed, "open-to-all-looking-for") < 20:
        looking_for_answer, looking_for_open_to_all = 6, True

    return {
        "me_answer": me_answer,
        "me_open_to_all": me_open_to_all,
        "me_importance": 1 if question.skip_me else 3,
        "me_share": True,
        "looking_for_answer": looking_for_answer,
        "looking_for_open_to_all": looking_for_open_to_all,
        "looking_for_importance": 1 if question.skip_looking_for else 3,
        "looking_for_share": True,
        "excluded_answer_values": [],
    }


def _create_required_catchup_activity(user, question, created_at):
    activity = FeedActivity.objects.create(
        user=user,
        kind="question_answered",
        payload={"question_id": str(question.id), "question_text": question.text or ""},
    )
    _set_created_at(activity, created_at)
    return activity


def _answer_all_required_questions_for_user(user, *, day_start, now, dry_run=False):
    """Create a UserAnswer for every currently-required-but-unanswered question
    for `user` (live state, not the day-start snapshot), emitting one
    question_answered FeedActivity per question and triggering compatibility
    recalculation the same way UserAnswerViewSet.create does. Returns the list
    of question ids answered (empty if nothing was pending).
    """
    required_qids = set(UserRequiredQuestion.objects.filter(user=user).values_list("question_id", flat=True))
    answered_qids = set(UserAnswer.objects.filter(user=user).values_list("question_id", flat=True))
    pending_qids = required_qids - answered_qids
    if not pending_qids:
        return []

    questions = list(
        Question.objects.filter(id__in=pending_qids)
        .prefetch_related("answers")
        .order_by("question_number", "group_number", "question_name", "id")
    )
    if dry_run:
        return [question.id for question in questions]

    answered_ids = []
    for offset, question in enumerate(questions):
        seed = f"{day_start.date()}:required-catchup:{user.id}:{question.id}"
        defaults = _required_answer_defaults(question, seed)
        answer, _ = UserAnswer.objects.update_or_create(user=user, question=question, defaults=defaults)
        created_at = min(now, day_start + timedelta(seconds=offset))
        _set_created_at(answer, created_at)
        _create_required_catchup_activity(user, question, created_at)
        answered_ids.append(question.id)

    User.objects.filter(id=user.id).update(questions_answered_count=UserAnswer.objects.filter(user=user).count())
    user.refresh_from_db(fields=["questions_answered_count"])

    if (user.questions_answered_count or 0) >= MIN_MATCHABLE_ANSWERS:
        enqueue_user_for_recalculation(user, force=True)
        process_user_compatibility_async(str(user.id))

    return answered_ids


def fill_due_dummy_required_question_answers(now=None, daily_count=5, dry_run=False, ignore_controls=False):
    now = now or timezone.now()
    daily_count = max(0, int(daily_count))
    day_start, _ = _local_day_bounds(now)

    if not ignore_controls:
        controls = Controls.get_current()
        if not controls.auto_updater_enabled or not controls.auto_answer_required_enabled:
            return {
                "daily_count": daily_count,
                "selected_users": 0,
                "users_touched": 0,
                "questions_answered": 0,
                "dry_run": dry_run,
                "skipped": "disabled",
            }

    selected_users = _select_required_catchup_users(day_start, daily_count)

    users_touched = 0
    questions_answered = 0
    for user in selected_users:
        if dry_run:
            answered_qids = _answer_all_required_questions_for_user(
                user, day_start=day_start, now=now, dry_run=True
            )
        else:
            with transaction.atomic():
                answered_qids = _answer_all_required_questions_for_user(
                    user, day_start=day_start, now=now
                )
        if answered_qids:
            users_touched += 1
            questions_answered += len(answered_qids)

    return {
        "daily_count": daily_count,
        "selected_users": len(selected_users),
        "users_touched": users_touched,
        "questions_answered": questions_answered,
        "dry_run": dry_run,
        "skipped": None,
    }


def create_user_result_with_notifications(user, result_user, tag):
    user_result, created = UserResult.objects.get_or_create(
        user=user,
        result_user=result_user,
        tag=tag,
    )
    if not created:
        return user_result, False

    notification_type = None
    if tag == "approve":
        notification_type = "approve"
    elif tag == "like":
        notification_type = "like"
        mutual_like = UserResult.objects.filter(
            user=result_user,
            result_user=user,
            tag="like",
        ).exists()
        if mutual_like:
            Notification.objects.create(
                recipient=user,
                sender=result_user,
                notification_type="match",
                related_user_result=user_result,
            )
            Notification.objects.create(
                recipient=result_user,
                sender=user,
                notification_type="match",
                related_user_result=user_result,
            )
            posthog_capture(str(user.id), "match_created_server", {"matched_user_id": str(result_user.id)})
            posthog_capture(str(result_user.id), "match_created_server", {"matched_user_id": str(user.id)})

    if notification_type:
        Notification.objects.create(
            recipient=result_user,
            sender=user,
            notification_type=notification_type,
            related_user_result=user_result,
        )

    return user_result, True


def _select_dummy_for_relation(seed, target_user, tag):
    existing = UserResult.objects.filter(
        user=OuterRef("pk"),
        result_user=target_user,
        tag=tag,
    )
    users = list(
        dummy_users_queryset()
        .exclude(id=target_user.id)
        .annotate(has_relation=Exists(existing))
        .filter(has_relation=False)
        .order_by("username", "id")
    )
    if not users:
        return None
    return users[_stable_int(seed, "relation", tag) % len(users)]


def _select_dummy_for_matchback(seed, real_user):
    dummy_ids = dummy_users_queryset().values("id")
    already_liked_back = UserResult.objects.filter(
        user=OuterRef("result_user_id"),
        result_user=real_user,
        tag="like",
    )
    candidates = list(
        UserResult.objects.filter(
            user=real_user,
            result_user_id__in=dummy_ids,
            tag="like",
        )
        .annotate(already_liked_back=Exists(already_liked_back))
        .filter(already_liked_back=False)
        .select_related("result_user")
        .order_by("created_at", "id")
    )
    if not candidates:
        return None
    return candidates[_stable_int(seed, "matchback") % len(candidates)].result_user


def simulate_dummy_reciprocation(trigger_result):
    if trigger_result.tag not in {"approve", "like"}:
        return {"approve": False, "like": False, "match": False}

    actor = trigger_result.user
    if is_dummy_user(actor):
        return {"approve": False, "like": False, "match": False}

    seed = str(trigger_result.id)
    outcomes = {"approve": False, "like": False, "match": False}

    if _stable_percent(seed, "approve") < 50:
        dummy = _select_dummy_for_relation(seed, actor, "approve")
        if dummy:
            _, created = create_user_result_with_notifications(dummy, actor, "approve")
            outcomes["approve"] = created

    if _stable_percent(seed, "like") < 25:
        dummy = _select_dummy_for_relation(seed, actor, "like")
        if dummy:
            _, created = create_user_result_with_notifications(dummy, actor, "like")
            outcomes["like"] = created

    if _stable_percent(seed, "match") < 15:
        dummy = _select_dummy_for_matchback(seed, actor)
        if dummy:
            _, created = create_user_result_with_notifications(dummy, actor, "like")
            outcomes["match"] = created

    return outcomes
