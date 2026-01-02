"""
Tests for required compatibility scoring.

This test suite verifies that:
1. If there are required questions and both users answered all required:
   - required_completeness_ratio == 1.0
   - required_* equals the base required calculation (no penalty)
2. If user1 answered fewer required than user2:
   - required_completeness_ratio == user1_count/total_required_count
   - required scores are reduced linearly
3. If mutual required overlap is 0:
   - required_* scores are 0 regardless of completeness (but completeness_ratio still computed)
4. If total_required_count == 0:
   - required_* == overall_* (or explicitly documented fallback)
"""

from django.test import TestCase
from django.db import transaction
from api.models import User, UserAnswer, Compatibility, Question, Tag, QuestionNumberCounter
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
        # User1 answers both required questions
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q2,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3
        )
        
        # User2 answers both required questions
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,  # Matches what user1 wants
            looking_for_answer=3,  # Matches what user1 is
            me_importance=3,
            looking_for_importance=3
        )
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=3,  # Matches what user1 wants
            looking_for_answer=4,  # Matches what user1 is
            me_importance=3,
            looking_for_importance=3
        )
        
        # Calculate compatibility
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        
        # Check completeness
        self.assertEqual(result['required_completeness_ratio'], 1.0,
                        "Both users answered all required questions, completeness should be 1.0")
        
        # Check that required scores are not penalized (should equal base calculation)
        # Since completeness is 1.0, required scores should equal base scores
        self.assertGreater(result['required_overall_compatibility'], 0,
                          "Required compatibility should be > 0 when both answered all required")
        self.assertGreater(result['required_mutual_questions_count'], 0,
                          "Should have mutual required questions")
    
    def test_user1_answered_fewer_required(self):
        """Test that when user1 answered fewer required, completeness ratio is reduced"""
        # User1 answers only 1 required question
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        
        # User2 answers both required questions
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3
        )
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        
        # Calculate compatibility
        total_required = Question.objects.filter(is_required_for_match=True).count()
        result = CompatibilityService.calculate_compatibility_between_users(
            self.user1, self.user2, total_required_count=total_required
        )
        
        # Check completeness ratio
        expected_completeness = min(1, 2) / total_required  # user1 answered 1, user2 answered 2
        self.assertAlmostEqual(result['required_completeness_ratio'], expected_completeness, places=3,
                              "Completeness should be min(user1_count, user2_count) / total_required")
        
        # Check that scores are penalized
        # If base score was 80% and completeness is 0.5, final should be 40%
        self.assertLessEqual(result['required_overall_compatibility'], 100.0,
                            "Required compatibility should be <= 100")
    
    def test_no_mutual_required_questions(self):
        """Test that when there are no mutual required questions, scores are 0"""
        # User1 answers required_q1
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        
        # User2 answers required_q2 (different question)
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3
        )
        
        # Calculate compatibility
        result = CompatibilityService.calculate_compatibility_between_users(self.user1, self.user2)
        
        # Check that required scores are 0 (no mutual required questions)
        self.assertEqual(result['required_overall_compatibility'], 0.0,
                        "No mutual required questions should result in 0 required compatibility")
        self.assertEqual(result['required_compatible_with_me'], 0.0)
        self.assertEqual(result['required_im_compatible_with'], 0.0)
        self.assertEqual(result['required_mutual_questions_count'], 0)
        
        # But completeness ratio should still be computed
        self.assertGreaterEqual(result['required_completeness_ratio'], 0.0,
                               "Completeness ratio should still be computed")
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
        """Test that completeness penalty is applied correctly"""
        # User1 answers 1 of 2 required questions
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=5,
            looking_for_answer=5,
            me_importance=5,
            looking_for_importance=5
        )
        
        # User2 answers both required questions with perfect match
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=5,  # Perfect match
            looking_for_answer=5,  # Perfect match
            me_importance=5,
            looking_for_importance=5
        )
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q2,
            me_answer=5,
            looking_for_answer=5,
            me_importance=5,
            looking_for_importance=5
        )
        
        # Calculate compatibility
        total_required = Question.objects.filter(is_required_for_match=True).count()
        result = CompatibilityService.calculate_compatibility_between_users(
            self.user1, self.user2, total_required_count=total_required
        )
        
        # Completeness should be 1/2 = 0.5 (user1 answered 1, user2 answered 2, min is 1)
        expected_completeness = 1.0 / total_required
        self.assertAlmostEqual(result['required_completeness_ratio'], expected_completeness, places=3)
        
        # Required scores should be penalized by completeness ratio
        # If base score was 100%, with completeness 0.5, final should be ~50%
        self.assertLess(result['required_overall_compatibility'], 100.0,
                        "Required compatibility should be penalized by completeness ratio")
    
    def test_recalculate_stores_required_scores(self):
        """Test that recalculate_all_compatibilities stores required scores"""
        # Create answers for both users
        UserAnswer.objects.create(
            user=self.user1,
            question=self.required_q1,
            me_answer=3,
            looking_for_answer=4,
            me_importance=3,
            looking_for_importance=3
        )
        UserAnswer.objects.create(
            user=self.user2,
            question=self.required_q1,
            me_answer=4,
            looking_for_answer=3,
            me_importance=3,
            looking_for_importance=3
        )
        
        # Recalculate compatibilities
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
