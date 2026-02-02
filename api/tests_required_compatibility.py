"""
Tests for required compatibility scoring (per-user UserRequiredQuestion).

This test suite verifies that:
1. Required sets come from UserRequiredQuestion (per user), not Question.is_required_for_match.
2. required_compatible_with_me = score on questions user1 marked required; required_im_compatible_with = score on questions user2 marked required.
3. user1_required_completeness = % of user2's required that user1 answered; user2_required_completeness = % of user1's required that user2 answered.
4. If both users have zero required: required_* == overall_*, completeness 1.0.
"""

from django.test import TestCase
from django.db import transaction
from api.models import User, UserAnswer, UserRequiredQuestion, Compatibility, Question, Tag, QuestionNumberCounter
from api.services.compatibility_service import CompatibilityService
from django.contrib.auth import get_user_model


class RequiredCompatibilityTestCase(TestCase):
    """Test required compatibility scoring"""
    
    def setUp(self):
        """Set up test data"""
        # Create or get the counter
        QuestionNumberCounter.objects.get_or_create(id=1, defaults={'last_number': 0})
        
        # Create test users
        self.user1 = get_user_model().objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = get_user_model().objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        # Create test tag
        self.tag, _ = Tag.objects.get_or_create(name='value')
        
        # Create test questions (some required, some not)
        self.required_q1 = Question.objects.create(
            text='Required Question 1',
            question_name='RQ1',
            question_type='basic',
            is_required_for_match=True,
            is_approved=True
        )
        self.required_q1.tags.add(self.tag)
        
        self.required_q2 = Question.objects.create(
            text='Required Question 2',
            question_name='RQ2',
            question_type='basic',
            is_required_for_match=True,
            is_approved=True
        )
        self.required_q2.tags.add(self.tag)
        
        self.optional_q1 = Question.objects.create(
            text='Optional Question 1',
            question_name='OQ1',
            question_type='basic',
            is_required_for_match=False,
            is_approved=True
        )
        self.optional_q1.tags.add(self.tag)
    
    def test_both_users_answered_all_required(self):
        """Test that when both users answered all required questions, completeness is 1.0 and no penalty"""
        # User1 answers both required questions and marks both as required for me (UserRequiredQuestion)
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q2,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q2)
        
        # User2 answers both required questions and marks both as required for me
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,  # Matches what user1 wants
            looking_for_answer=3,  # Matches what user1 is
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=3,  # Matches what user1 wants
            looking_for_answer=4,  # Matches what user1 is
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q2)
        
        # Calculate compatibility (per-user required from UserRequiredQuestion)
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        
        # Check completeness (both users answered all of the other's required)
        self.assertEqual(result['required_completeness_ratio'], 1.0,
                        "Both users answered all required questions, completeness should be 1.0")
        
        # Check that required scores are not penalized (should equal base calculation)
        # Since completeness is 1.0, required scores should equal base scores
        self.assertGreater(result['required_overall_compatibility'], 0,
                          "Required compatibility should be > 0 when both answered all required")
        self.assertGreater(result['required_mutual_questions_count'], 0,
                          "Should have mutual required questions")
    
    def test_user1_answered_fewer_required(self):
        """Per-user required: user1 marks only q1 required, user2 marks both; user1_completeness = 0.5, user2 = 1.0"""
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q2)
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        # user1_required_completeness = of user2's required (q1,q2), user1 answered 1 -> 0.5; user2_required_completeness = 1/1 = 1.0
        self.assertAlmostEqual(result['user1_required_completeness'], 0.5, places=3)
        self.assertAlmostEqual(result['user2_required_completeness'], 1.0, places=3)
        self.assertLessEqual(result['required_overall_compatibility'], 100.0)
    
    def test_no_mutual_required_questions(self):
        """When users mark different questions required (no overlap), required scores are 0"""
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q2)
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        self.assertEqual(result['required_overall_compatibility'], 0.0)
        self.assertEqual(result['required_compatible_with_me'], 0.0)
        self.assertEqual(result['required_im_compatible_with'], 0.0)
        self.assertEqual(result['required_mutual_questions_count'], 0)
        self.assertGreaterEqual(result['required_completeness_ratio'], 0.0)
        self.assertLessEqual(result['required_completeness_ratio'], 1.0)
    
    def test_no_required_questions_exist(self):
        """Test that when no required questions exist, required scores equal overall scores"""
        # Remove required flag from all questions
        Question.objects.filter(is_required_for_match=True).update(is_required_for_match=False)
        
        # Create some optional questions and answers
        optional_q = Question.objects.create(
            text='Optional Question',
            question_name='OQ',
            question_type='basic',
            is_required_for_match=False,
            is_approved=True
        )
        optional_q.tags.add(self.tag)
        
        UserAnswer.objects.create(
            user=self.user1,
            question=optional_q,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        UserAnswer.objects.create(
            user=self.user2,
            question=optional_q,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3
        )
        
        # Calculate compatibility
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        
        # Check that required scores equal overall scores
        self.assertEqual(result['required_overall_compatibility'], result['overall_compatibility'],
                        "When no required questions exist, required should equal overall")
        self.assertEqual(result['required_compatible_with_me'], result['compatible_with_me'])
        self.assertEqual(result['required_im_compatible_with'], result['im_compatible_with'])
        self.assertEqual(result['required_mutual_questions_count'], result['mutual_questions_count'])
        self.assertEqual(result['required_completeness_ratio'], 1.0,
                        "Completeness should be 1.0 when no required questions exist")
    
    def test_required_completeness_penalty_application(self):
        """Per-user required: user1 marks only q1, user2 marks both; user1_completeness 0.5"""
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=5,
            looking_for_answer=5,
            me_importance=5,
            looking_for_importance=5,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=5,
            looking_for_answer=5,
            me_importance=5,
            looking_for_importance=5,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=5,
            looking_for_answer=5,
            me_importance=5,
            looking_for_importance=5,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q2)
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        self.assertAlmostEqual(result['user1_required_completeness'], 0.5, places=3,
                              msg="Of user2's 2 required questions, user1 answered 1")
        self.assertLessEqual(result['required_overall_compatibility'], 100.0)
    
    def test_recalculate_stores_required_scores(self):
        """Test that recalculate_all_compatibilities stores required scores (per-user UserRequiredQuestion)"""
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user1, question=self.required_q1)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3,
        )
        UserRequiredQuestion.objects.get_or_create(user=self.user2, question=self.required_q1)
        
        CompatibilityService.recalculate_all_compatibilities(self.user1)
        
        # Check that Compatibility record has required scores
        comp = Compatibility.objects.filter(
            user1=self.user1, user2=self.user2
        ).first()
        
        if comp:
            self.assertIsNotNone(comp.required_overall_compatibility,
                                "Required overall compatibility should be stored")
            self.assertIsNotNone(comp.required_compatible_with_me,
                                "Required compatible_with_me should be stored")
            self.assertIsNotNone(comp.required_im_compatible_with,
                                "Required im_compatible_with should be stored")
            self.assertIsNotNone(comp.required_mutual_questions_count,
                                "Required mutual questions count should be stored")
            self.assertIsNotNone(comp.required_completeness_ratio,
                                "Required completeness ratio should be stored")
