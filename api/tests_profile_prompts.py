from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    Message,
    Notification,
    PromptPollVote,
    PromptTemplate,
    Question,
    UserProfilePrompt,
    UserRequiredQuestion,
    UserResult,
)


class ProfilePromptApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', email='owner@test.com', password='pass123')
        self.viewer = User.objects.create_user(username='viewer', email='viewer@test.com', password='pass123')
        self.client = APIClient()
        self.templates = [
            PromptTemplate.objects.get_or_create(text='My simple pleasures...', defaults={'category': 'about', 'order': 0})[0],
            PromptTemplate.objects.get_or_create(text="I'm looking for...", defaults={'category': 'values', 'order': 1})[0],
            PromptTemplate.objects.get_or_create(text='Two truths and a lie...', defaults={'category': 'interactive', 'order': 2})[0],
            PromptTemplate.objects.get_or_create(text='Together, we could...', defaults={'category': 'dating', 'order': 3})[0],
            PromptTemplate.objects.get_or_create(text='Green flags I look for...', defaults={'category': 'values', 'order': 4})[0],
            PromptTemplate.objects.get_or_create(text='Perfect first date...', defaults={'category': 'dating', 'order': 5})[0],
            PromptTemplate.objects.get_or_create(text="I bet you can't...", defaults={'category': 'fun', 'order': 6})[0],
        ]

    def _valid_payload(self):
        return {
            'user_id': str(self.owner.id),
            'prompts': [
                {
                    'template_id': str(self.templates[0].id),
                    'prompt_type': 'written',
                    'written_answer': 'Coffee, clean sheets, and long walks.',
                },
                {
                    'template_id': str(self.templates[1].id),
                    'prompt_type': 'voice',
                    'media_url': 'https://example.com/prompt.m4a',
                    'media_duration_seconds': 24.3,
                },
                {
                    'template_id': str(self.templates[2].id),
                    'prompt_type': 'poll',
                    'poll_options': ['Cook together', 'Go dancing', 'Try trivia'],
                },
            ],
        }

    def test_replace_set_allows_partial_sets_and_enforces_caps(self):
        payload = self._valid_payload()
        payload['prompts'] = payload['prompts'][:1]

        response = self.client.post('/api/profile-prompts/replace-set/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserProfilePrompt.objects.filter(user=self.owner).count(), 1)

        payload = self._valid_payload()
        payload['prompts'] = [
            {
                'template_id': str(template.id),
                'prompt_type': 'written',
                'written_answer': f'Answer {index}',
            }
            for index, template in enumerate(self.templates[:4])
        ]
        response = self.client.post('/api/profile-prompts/replace-set/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('3 written prompts', response.data['error'])

        payload['prompts'] = [
            {
                'template_id': str(template.id),
                'prompt_type': 'written',
                'written_answer': f'Answer {index}',
            }
            for index, template in enumerate(self.templates)
        ]
        response = self.client.post('/api/profile-prompts/replace-set/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('up to 6 prompts', response.data['error'])

    def test_replace_set_validates_written_length_media_duration_and_poll_options(self):
        payload = self._valid_payload()
        payload['prompts'][0]['written_answer'] = 'x' * 151
        self.assertEqual(self.client.post('/api/profile-prompts/replace-set/', payload, format='json').status_code, 400)

        payload = self._valid_payload()
        payload['prompts'][1]['media_duration_seconds'] = 31
        self.assertEqual(self.client.post('/api/profile-prompts/replace-set/', payload, format='json').status_code, 400)

        payload = self._valid_payload()
        payload['prompts'][2]['poll_options'] = ['One', 'Two']
        self.assertEqual(self.client.post('/api/profile-prompts/replace-set/', payload, format='json').status_code, 400)

    def test_replace_set_creates_three_profile_prompts(self):
        response = self.client.post('/api/profile-prompts/replace-set/', self._valid_payload(), format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserProfilePrompt.objects.filter(user=self.owner).count(), 3)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data[2]['poll_options'], ['Cook together', 'Go dancing', 'Try trivia'])

    def test_replace_set_rejects_non_owner_editor(self):
        payload = self._valid_payload()
        payload['editor_id'] = str(self.viewer.id)

        response = self.client.post('/api/profile-prompts/replace-set/', payload, format='json')

        self.assertEqual(response.status_code, 403)

    def test_poll_vote_creates_private_vote_like_and_notification(self):
        self.client.post('/api/profile-prompts/replace-set/', self._valid_payload(), format='json')
        poll_prompt = UserProfilePrompt.objects.get(user=self.owner, prompt_type='poll')

        response = self.client.post(
            f'/api/profile-prompts/{poll_prompt.id}/vote/',
            {
                'voter_id': str(self.viewer.id),
                'selected_option_index': 1,
                'comment': 'Trivia first.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PromptPollVote.objects.filter(prompt=poll_prompt, voter=self.viewer).count(), 1)
        self.assertTrue(UserResult.objects.filter(user=self.viewer, result_user=self.owner, tag='like').exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                sender=self.viewer,
                notification_type='prompt_poll',
                related_prompt_poll_vote__isnull=False,
            ).exists()
        )
        self.assertTrue(
            Message.objects.filter(
                sender=self.viewer,
                receiver=self.owner,
                content='Trivia first.',
            ).exists()
        )

        list_response = self.client.get(
            f'/api/profile-prompts/?user_id={self.owner.id}&viewer_id={self.viewer.id}'
        )
        self.assertEqual(list_response.status_code, 200)
        list_items = list_response.data.get('results', list_response.data)
        poll_data = [item for item in list_items if item['prompt_type'] == 'poll'][0]
        self.assertIsNotNone(poll_data['viewer_vote'])
        self.assertEqual(poll_data['poll_votes'], [])

        leak_response = self.client.get(
            f'/api/profile-prompts/?user_id={self.owner.id}&viewer_id={self.viewer.id}&owner_id={self.owner.id}&include_votes=true'
        )
        leak_items = leak_response.data.get('results', leak_response.data)
        leak_poll_data = [item for item in leak_items if item['prompt_type'] == 'poll'][0]
        self.assertEqual(leak_poll_data['poll_votes'], [])

        owner_response = self.client.get(
            f'/api/profile-prompts/?user_id={self.owner.id}&viewer_id={self.owner.id}&owner_id={self.owner.id}&include_votes=true'
        )
        owner_items = owner_response.data.get('results', owner_response.data)
        owner_poll_data = [item for item in owner_items if item['prompt_type'] == 'poll'][0]
        self.assertEqual(len(owner_poll_data['poll_votes']), 1)

    def test_poll_vote_ignores_required_question_like_gate(self):
        self.owner.require_answers_for_likes = True
        self.owner.save(update_fields=['require_answers_for_likes'])
        required_question = Question.objects.create(
            text='Required question',
            question_name='Required',
            question_number=99,
            is_approved=True,
        )
        UserRequiredQuestion.objects.create(user=self.owner, question=required_question)
        self.client.post('/api/profile-prompts/replace-set/', self._valid_payload(), format='json')
        poll_prompt = UserProfilePrompt.objects.get(user=self.owner, prompt_type='poll')

        response = self.client.post(
            f'/api/profile-prompts/{poll_prompt.id}/vote/',
            {'voter_id': str(self.viewer.id), 'selected_option_index': 0},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PromptPollVote.objects.filter(prompt=poll_prompt, voter=self.viewer).exists())

    def test_poll_owner_can_vote_on_own_poll(self):
        self.client.post('/api/profile-prompts/replace-set/', self._valid_payload(), format='json')
        poll_prompt = UserProfilePrompt.objects.get(user=self.owner, prompt_type='poll')

        response = self.client.post(
            f'/api/profile-prompts/{poll_prompt.id}/vote/',
            {'voter_id': str(self.owner.id), 'selected_option_index': 2, 'comment': 'My own pick.'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PromptPollVote.objects.filter(prompt=poll_prompt, voter=self.owner).exists())
        self.assertFalse(UserResult.objects.filter(user=self.owner, result_user=self.owner, tag='like').exists())
        self.assertFalse(Message.objects.filter(sender=self.owner, receiver=self.owner).exists())
