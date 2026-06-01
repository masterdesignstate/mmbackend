from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import FeedActivity, Post, PostComment, UserResult


class ProfileSocialApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(username='viewer_social', email='viewer_social@test.com', password='pass123')
        self.profile_user = User.objects.create_user(username='profile_social', email='profile_social@test.com', password='pass123')
        self.other = User.objects.create_user(username='other_social', email='other_social@test.com', password='pass123')
        self.client = APIClient()

    def _profile_feed(self):
        return self.client.get(f'/api/feed/?author_id={self.profile_user.id}&user_id={self.viewer.id}')

    def test_author_filtered_feed_returns_visible_posts_only_and_no_activities(self):
        visible = Post.objects.create(author=self.profile_user, body='Visible profile post', visibility='all')
        Post.objects.create(author=self.profile_user, body='Liked-only profile post', visibility='liked')
        Post.objects.create(author=self.profile_user, body='Deleted profile post', visibility='all', is_deleted=True)
        Post.objects.create(author=self.other, body='Other visible post', visibility='all')
        FeedActivity.objects.create(user=self.profile_user, kind='bio_updated', payload={'bio': 'updated'})

        response = self._profile_feed()

        self.assertEqual(response.status_code, 200)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['kind'], 'post')
        self.assertEqual(results[0]['post']['id'], str(visible.id))

    def test_author_filtered_feed_allows_restricted_posts_when_visibility_rule_matches(self):
        approved_post = Post.objects.create(author=self.profile_user, body='Approved-only profile post', visibility='approved')
        matched_post = Post.objects.create(author=self.profile_user, body='Matched-only profile post', visibility='matched')
        UserResult.objects.create(user=self.profile_user, result_user=self.viewer, tag='approve')

        response = self._profile_feed()

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['post']['id'] for item in response.data['results']}
        self.assertIn(str(approved_post.id), returned_ids)
        self.assertNotIn(str(matched_post.id), returned_ids)

        UserResult.objects.create(user=self.profile_user, result_user=self.viewer, tag='like')
        UserResult.objects.create(user=self.viewer, result_user=self.profile_user, tag='like')

        response = self._profile_feed()

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['post']['id'] for item in response.data['results']}
        self.assertIn(str(approved_post.id), returned_ids)
        self.assertIn(str(matched_post.id), returned_ids)

    def test_author_filtered_comments_include_only_authored_comments_on_visible_posts(self):
        visible_parent = Post.objects.create(author=self.other, body='A visible parent post with context', visibility='all')
        hidden_parent = Post.objects.create(author=self.other, body='A hidden parent post', visibility='approved')
        visible_comment = PostComment.objects.create(
            post=visible_parent,
            author=self.profile_user,
            body='Profile user comment on visible post',
        )
        PostComment.objects.create(
            post=hidden_parent,
            author=self.profile_user,
            body='Profile user comment on hidden post',
        )
        PostComment.objects.create(
            post=visible_parent,
            author=self.other,
            body='Other user comment on visible post',
        )

        response = self.client.get(f'/api/comments/?author_id={self.profile_user.id}&user_id={self.viewer.id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], str(visible_comment.id))
        self.assertEqual(response.data[0]['post_preview']['id'], str(visible_parent.id))
        self.assertEqual(response.data[0]['post_preview']['body'], visible_parent.body)
        self.assertEqual(response.data[0]['post_preview']['author']['id'], str(self.other.id))
