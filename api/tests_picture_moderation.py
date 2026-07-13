from django.test import TestCase
from rest_framework.test import APIClient

from api.models import PictureModeration, User


class PictureModerationAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin1", email="admin1@example.com", password="pass123", is_admin=True
        )
        self.owner = User.objects.create_user(
            username="owner1", email="owner1@example.com", password="pass123"
        )
        self.other_user = User.objects.create_user(
            username="other1", email="other1@example.com", password="pass123"
        )
        self.staff_only = User.objects.create_user(
            username="staffonly", email="staffonly@example.com", password="pass123", is_staff=True
        )
        self.moderation = PictureModeration.objects.create(
            user=self.owner,
            picture_url="https://example.com/photo.jpg",
            status="pending",
        )

    def test_approve_without_user_id_returns_403_not_crash(self):
        response = self.client.post(f"/api/picture-moderation/{self.moderation.id}/approve/")
        self.assertEqual(response.status_code, 403)

    def test_approve_with_non_admin_user_id_returns_403(self):
        response = self.client.post(
            f"/api/picture-moderation/{self.moderation.id}/approve/",
            {"user_id": str(self.other_user.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.moderation.refresh_from_db()
        self.assertEqual(self.moderation.status, "pending")

    def test_approve_with_admin_user_id_succeeds(self):
        response = self.client.post(
            f"/api/picture-moderation/{self.moderation.id}/approve/",
            {"user_id": str(self.admin.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.moderation.refresh_from_db()
        self.assertEqual(self.moderation.status, "approved")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.profile_photo, "https://example.com/photo.jpg")

    def test_approve_with_is_staff_but_not_is_admin_succeeds(self):
        """Real accounts can have is_staff=True without the custom is_admin
        flag set (e.g. Django superusers created before is_admin existed).
        Both must be honored, not just is_admin.
        """
        response = self.client.post(
            f"/api/picture-moderation/{self.moderation.id}/approve/",
            {"user_id": str(self.staff_only.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.moderation.refresh_from_db()
        self.assertEqual(self.moderation.status, "approved")

    def test_reject_without_user_id_returns_403_not_crash(self):
        response = self.client.post(f"/api/picture-moderation/{self.moderation.id}/reject/")
        self.assertEqual(response.status_code, 403)

    def test_reject_with_admin_user_id_succeeds(self):
        response = self.client.post(
            f"/api/picture-moderation/{self.moderation.id}/reject/",
            {"user_id": str(self.admin.id), "reason": "blurry"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.moderation.refresh_from_db()
        self.assertEqual(self.moderation.status, "rejected")
        self.assertEqual(self.moderation.moderator_notes, "blurry")

    def test_queue_without_user_id_returns_403_not_crash(self):
        response = self.client.get("/api/picture-moderation/queue/")
        self.assertEqual(response.status_code, 403)

    def test_queue_with_admin_user_id_succeeds(self):
        response = self.client.get(f"/api/picture-moderation/queue/?user_id={self.admin.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_pending_without_user_id_returns_403_not_crash(self):
        response = self.client.get("/api/picture-moderation/pending/")
        self.assertEqual(response.status_code, 403)

    def test_list_anonymous_returns_empty_not_all_records(self):
        other_moderation = PictureModeration.objects.create(
            user=self.other_user,
            picture_url="https://example.com/other.jpg",
            status="pending",
        )
        response = self.client.get("/api/picture-moderation/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 0)
        self.assertFalse(any(str(other_moderation.id) == r.get("id") for r in results))
