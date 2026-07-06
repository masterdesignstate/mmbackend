import hashlib
import random
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from api.analytics import capture as posthog_capture
from api.models import (
    FeedActivity,
    Notification,
    Post,
    PostImage,
    Question,
    User,
    UserAnswer,
    UserPicture,
    UserResult,
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
    return bool(user and (user.email or "").lower().endswith(f"@{DUMMY_EMAIL_DOMAIN}"))


def dummy_users_queryset():
    return User.objects.filter(
        email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}",
        is_active=True,
        is_banned=False,
    )


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
def fill_due_dummy_feed_activity(now=None, daily_minimum=20):
    now = now or timezone.now()
    daily_minimum = max(1, int(daily_minimum))
    day_start, _ = _local_day_bounds(now)
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
