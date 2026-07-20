from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    CompatibilityJob,
    Controls,
    FeedActivity,
    Notification,
    Post,
    PostImage,
    Question,
    QuestionAnswer,
    User,
    UserAnswer,
    UserPicture,
    UserRequiredQuestion,
    UserResult,
)
from api.services.dummy_activity import (
    DUMMY_EMAIL_DOMAIN,
    fill_due_dummy_required_question_answers,
)


class DummyActivityCommandTests(TestCase):
    def setUp(self):
        self.now_noon = timezone.make_aware(datetime(2026, 7, 6, 12, 0, 0))
        self.now_end_of_day = timezone.make_aware(datetime(2026, 7, 6, 23, 59, 0))
        self.question = Question.objects.create(
            question_number=20,
            question_name="Weekend",
            text="What kind of weekend do you prefer?",
            is_approved=True,
            is_mandatory=False,
        )
        for value in range(1, 6):
            QuestionAnswer.objects.create(
                question=self.question,
                value=str(value),
                answer_text=f"Answer {value}",
                order=value,
            )

        for username in ["dummyone", "dummytwo", "dummythree", "oliviastacey", "jackperez"]:
            user = User.objects.create_user(
                username=username,
                email=f"{username}@{DUMMY_EMAIL_DOMAIN}",
                password="pass123",
                first_name=username.title(),
                bio="Original bio",
            )
            UserPicture.objects.create(
                user=user,
                image_url=f"https://example.com/{username}.jpg",
                order=0,
            )
            user.profile_photo = f"https://example.com/{username}.jpg"
            user.save(update_fields=["profile_photo"])

    def _feed_item_count(self):
        return Post.objects.count() + FeedActivity.objects.count()

    def test_command_creates_due_portion_and_is_idempotent_for_same_hour(self):
        with patch("api.services.dummy_activity.timezone.now", return_value=self.now_noon):
            call_command("simulate_dummy_activity", daily_minimum=20, stdout=StringIO())

        first_count = self._feed_item_count()
        self.assertGreaterEqual(first_count, 10)

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now_noon):
            call_command("simulate_dummy_activity", daily_minimum=20, stdout=StringIO())

        self.assertEqual(self._feed_item_count(), first_count)

    def test_command_creates_mixed_full_day_activity(self):
        with patch("api.services.dummy_activity.timezone.now", return_value=self.now_end_of_day):
            call_command("simulate_dummy_activity", daily_minimum=20, stdout=StringIO())

        self.assertGreaterEqual(self._feed_item_count(), 20)
        self.assertTrue(Post.objects.exists())
        self.assertTrue(PostImage.objects.exists())
        activity_kinds = set(FeedActivity.objects.values_list("kind", flat=True))
        self.assertIn("bio_updated", activity_kinds)
        self.assertIn("photo_added", activity_kinds)
        self.assertIn("question_answered", activity_kinds)

    def test_question_activity_never_uses_protected_dummy_users(self):
        with patch("api.services.dummy_activity.timezone.now", return_value=self.now_end_of_day):
            call_command("simulate_dummy_activity", daily_minimum=20, stdout=StringIO())

        question_usernames = set(
            FeedActivity.objects.filter(kind="question_answered").values_list("user__username", flat=True)
        )
        self.assertTrue(question_usernames)
        self.assertFalse({"oliviastacey", "jackperez"} & question_usernames)


class DummyRequiredQuestionCatchupTests(TestCase):
    def setUp(self):
        self.day_start = timezone.make_aware(datetime(2026, 7, 6, 0, 0, 0))
        self.now = timezone.make_aware(datetime(2026, 7, 6, 12, 0, 0))
        self.yesterday = self.day_start - timedelta(days=1)

        self.required_questions = []
        for i in range(3):
            question = Question.objects.create(
                question_number=50 + i,
                question_name=f"Required{i}",
                text=f"Required catch-up question number {i}?",
                is_approved=True,
                is_mandatory=False,
            )
            for value in range(1, 6):
                QuestionAnswer.objects.create(
                    question=question, value=str(value), answer_text=f"Answer {value}", order=value
                )
            self.required_questions.append(question)

        # The required-question catch-up acts on REAL users only, so the
        # candidate pool here is non-dummy. The protected usernames are created
        # as real users too -- as dummies they would be excluded by the dummy
        # filter and the protection check would never actually be exercised.
        self.real_users = {
            username: User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="pass123",
                is_dummy=False,
            )
            for username in [
                "realone", "realtwo", "realthree", "realfour", "realfive", "realsix",
                "oliviastacey", "jackperez",
            ]
        }
        self.dummy_user = User.objects.create_user(
            username="dummyone",
            email=f"dummyone@{DUMMY_EMAIL_DOMAIN}",
            password="pass123",
            is_dummy=True,
        )

    def _require(self, user, question, backdated=True):
        req = UserRequiredQuestion.objects.create(user=user, question=question)
        if backdated:
            UserRequiredQuestion.objects.filter(id=req.id).update(created_at=self.yesterday)
        return req

    def _answered_question_ids(self, user):
        return set(UserAnswer.objects.filter(user=user).values_list("question_id", flat=True))

    def test_answers_all_pending_required_questions_for_selected_user(self):
        user = self.real_users["realone"]
        for question in self.required_questions:
            self._require(user, question)

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            result = fill_due_dummy_required_question_answers(daily_count=6)

        self.assertEqual(self._answered_question_ids(user), {q.id for q in self.required_questions})
        self.assertEqual(
            FeedActivity.objects.filter(user=user, kind="question_answered").count(),
            len(self.required_questions),
        )
        self.assertEqual(result["questions_answered"], len(self.required_questions))
        self.assertEqual(result["users_touched"], 1)

    def test_idempotent_on_rerun_same_day(self):
        user = self.real_users["realone"]
        for question in self.required_questions:
            self._require(user, question)

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=6)
            first_answer_count = UserAnswer.objects.count()
            first_activity_count = FeedActivity.objects.filter(kind="question_answered").count()

            fill_due_dummy_required_question_answers(daily_count=6)

        self.assertEqual(UserAnswer.objects.count(), first_answer_count)
        self.assertEqual(FeedActivity.objects.filter(kind="question_answered").count(), first_activity_count)

    def test_prioritizes_users_with_pending_gap(self):
        gapped = [self.real_users["realone"], self.real_users["realtwo"]]
        for user in gapped:
            self._require(user, self.required_questions[0])

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=2)

        answered_usernames = set(
            UserAnswer.objects.filter(question=self.required_questions[0]).values_list("user__username", flat=True)
        )
        self.assertEqual(answered_usernames, {"realone", "realtwo"})

    def test_never_touches_protected_users(self):
        for username in ("oliviastacey", "jackperez"):
            self._require(self.real_users[username], self.required_questions[0])

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=8)

        self.assertEqual(self._answered_question_ids(self.real_users["oliviastacey"]), set())
        self.assertEqual(self._answered_question_ids(self.real_users["jackperez"]), set())

    def test_ignores_dummy_users(self):
        """The simulator must never fabricate required answers on a seeded profile."""
        self._require(self.dummy_user, self.required_questions[0])

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=8)

        self.assertEqual(self._answered_question_ids(self.dummy_user), set())

    def test_ignores_dummy_user_flagged_only_by_email_domain(self):
        """Fallback path: a legacy row whose is_dummy was never backfilled is
        still recognised as dummy via its email domain."""
        legacy = User.objects.create_user(
            username="legacydummy",
            email=f"legacydummy@{DUMMY_EMAIL_DOMAIN}",
            password="pass123",
            is_dummy=False,
        )
        self._require(legacy, self.required_questions[0])

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=8)

        self.assertEqual(self._answered_question_ids(legacy), set())

    def test_skips_when_required_toggle_disabled(self):
        user = self.real_users["realone"]
        self._require(user, self.required_questions[0])
        controls = Controls.get_current()
        controls.auto_answer_required_enabled = False
        controls.save()

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            result = fill_due_dummy_required_question_answers(daily_count=6)

        self.assertEqual(result["skipped"], "disabled")
        self.assertEqual(self._answered_question_ids(user), set())

    def test_master_toggle_disables_required_catchup(self):
        user = self.real_users["realone"]
        self._require(user, self.required_questions[0])
        controls = Controls.get_current()
        controls.auto_updater_enabled = False
        controls.save()

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            result = fill_due_dummy_required_question_answers(daily_count=6)

        self.assertEqual(result["skipped"], "disabled")
        self.assertEqual(self._answered_question_ids(user), set())

    def test_triggers_compatibility_job_once_threshold_crossed(self):
        user = self.real_users["realone"]

        # Nine pre-existing (non-required) answers so this user is one answer
        # away from MIN_MATCHABLE_ANSWERS = 10.
        for i in range(9):
            filler_question = Question.objects.create(
                question_number=100 + i,
                question_name=f"Filler{i}",
                text=f"Filler question {i}?",
                is_approved=True,
                is_mandatory=False,
            )
            QuestionAnswer.objects.create(question=filler_question, value="1", answer_text="A", order=1)
            QuestionAnswer.objects.create(question=filler_question, value="5", answer_text="B", order=5)
            UserAnswer.objects.create(user=user, question=filler_question, me_answer=3, looking_for_answer=3)

        self._require(user, self.required_questions[0])

        self.assertFalse(CompatibilityJob.objects.filter(user=user).exists())

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            fill_due_dummy_required_question_answers(daily_count=6)

        self.assertTrue(CompatibilityJob.objects.filter(user=user).exists())

    def test_dry_run_reports_without_writing(self):
        user = self.real_users["realone"]
        for question in self.required_questions:
            self._require(user, question)

        with patch("api.services.dummy_activity.timezone.now", return_value=self.now):
            result = fill_due_dummy_required_question_answers(daily_count=6, dry_run=True)

        self.assertEqual(result["questions_answered"], len(self.required_questions))
        self.assertEqual(UserAnswer.objects.count(), 0)
        self.assertEqual(FeedActivity.objects.filter(kind="question_answered").count(), 0)


class DummyReciprocationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.real = User.objects.create_user(username="realuser", email="real@example.com", password="pass123")
        self.target = User.objects.create_user(username="targetuser", email="target@example.com", password="pass123")
        self.dummy_a = User.objects.create_user(
            username="dummya",
            email=f"dummya@{DUMMY_EMAIL_DOMAIN}",
            password="pass123",
        )
        self.dummy_b = User.objects.create_user(
            username="dummyb",
            email=f"dummyb@{DUMMY_EMAIL_DOMAIN}",
            password="pass123",
        )
        self.question = Question.objects.create(
            question_number=30,
            question_name="Required",
            text="Required question?",
            is_approved=True,
        )
        QuestionAnswer.objects.create(question=self.question, value="1", answer_text="No", order=1)
        QuestionAnswer.objects.create(question=self.question, value="5", answer_text="Yes", order=5)

    def _toggle(self, actor, target, tag):
        return self.client.post(
            "/api/results/toggle_tag/",
            {
                "user_id": str(actor.id),
                "result_user_id": str(target.id),
                "tag": tag,
            },
            format="json",
        )

    def test_real_action_can_create_dummy_approve(self):
        def percent(*parts):
            return 0 if parts[-1] == "approve" else 100

        with patch("api.services.dummy_activity._stable_percent", side_effect=percent):
            response = self._toggle(self.real, self.target, "Approve")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            UserResult.objects.filter(result_user=self.real, tag="approve", user__email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}").exists()
        )
        self.assertEqual(Notification.objects.filter(recipient=self.real, notification_type="approve").count(), 1)

    def test_real_action_can_create_dummy_like(self):
        def percent(*parts):
            return 0 if parts[-1] == "like" else 100

        with patch("api.services.dummy_activity._stable_percent", side_effect=percent):
            response = self._toggle(self.real, self.target, "Approve")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            UserResult.objects.filter(result_user=self.real, tag="like", user__email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}").exists()
        )
        self.assertEqual(Notification.objects.filter(recipient=self.real, notification_type="like").count(), 1)

    def test_real_action_can_create_dummy_matchback(self):
        UserResult.objects.create(user=self.real, result_user=self.dummy_a, tag="like")

        def percent(*parts):
            return 0 if parts[-1] == "match" else 100

        with patch("api.services.dummy_activity._stable_percent", side_effect=percent):
            response = self._toggle(self.real, self.target, "Approve")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(UserResult.objects.filter(user=self.dummy_a, result_user=self.real, tag="like").exists())
        self.assertEqual(Notification.objects.filter(notification_type="match").count(), 2)

    def test_dummy_actor_does_not_trigger_recursive_dummy_responses(self):
        with patch("api.services.dummy_activity._stable_percent", return_value=0):
            response = self._toggle(self.dummy_a, self.real, "Approve")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(UserResult.objects.filter(result_user=self.dummy_a).count(), 0)
        self.assertEqual(UserResult.objects.exclude(user=self.dummy_a, result_user=self.real).count(), 0)

    def test_required_question_like_gate_still_blocks_manual_real_like(self):
        self.target.require_answers_for_likes = True
        self.target.save(update_fields=["require_answers_for_likes"])
        UserRequiredQuestion.objects.create(user=self.target, question=self.question)

        with patch("api.services.dummy_activity._stable_percent", return_value=0):
            response = self._toggle(self.real, self.target, "Like")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserResult.objects.filter(user=self.real, result_user=self.target, tag="like").exists())
        self.assertFalse(UserResult.objects.filter(result_user=self.real, user__email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}").exists())

        UserAnswer.objects.create(
            user=self.real,
            question=self.question,
            me_answer=5,
            looking_for_answer=5,
        )
        with patch("api.services.dummy_activity._stable_percent", return_value=100):
            response = self._toggle(self.real, self.target, "Like")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(UserResult.objects.filter(user=self.real, result_user=self.target, tag="like").exists())
