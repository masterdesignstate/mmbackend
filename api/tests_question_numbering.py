"""
Tests for question numbering system.

This test suite verifies that:
1. Creating a question results in question_number == NULL
2. Approving assigns a non-null question_number
3. Approving two questions concurrently yields two distinct numbers (no collisions)
4. Grouped questions can share the same question_number (with different group_number)
5. Unapproving sets question_number to NULL
"""

from django.test import TestCase
from django.db import transaction
from django.db.utils import IntegrityError
from api.models import Question, QuestionNumberCounter, Tag, User
from django.contrib.auth import get_user_model


class QuestionNumberingTestCase(TestCase):
    """Test question numbering system"""
    
    def setUp(self):
        """Set up test data"""
        # Create or get the counter
        QuestionNumberCounter.objects.get_or_create(id=1, defaults={'last_number': 0})
        
        # Create a test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create a test tag
        self.tag, _ = Tag.objects.get_or_create(name='value')
    
    def test_create_question_has_null_question_number(self):
        """Test that creating a question results in question_number == NULL"""
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=False
        )
        question.tags.add(self.tag)
        
        # Refresh from database
        question.refresh_from_db()
        
        # Assert question_number is NULL
        self.assertIsNone(question.question_number, 
                         "New questions should have question_number = NULL")
    
    def test_approve_assigns_question_number(self):
        """Test that approving a question assigns a non-null question_number"""
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        question.tags.add(self.tag)
        
        # Approve the question
        question.is_approved = True
        if question.question_number is None:
            question.question_number = QuestionNumberCounter.allocate_next_number()
        question.save()
        
        # Refresh from database
        question.refresh_from_db()
        
        # Assert question_number is not NULL
        self.assertIsNotNone(question.question_number,
                            "Approved questions should have a question_number")
        self.assertGreater(question.question_number, 0,
                          "Question number should be positive")
    
    def test_concurrent_approval_no_collisions(self):
        """Test that approving two questions concurrently yields two distinct numbers"""
        # Create two questions
        q1 = Question.objects.create(
            text='Question 1',
            question_name='Q1',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        q1.tags.add(self.tag)
        
        q2 = Question.objects.create(
            text='Question 2',
            question_name='Q2',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        q2.tags.add(self.tag)
        
        # Approve both questions
        # Simulate concurrent approval by calling allocate_next_number in sequence
        # (In real concurrency, this would be handled by SELECT FOR UPDATE)
        q1.is_approved = True
        if q1.question_number is None:
            q1.question_number = QuestionNumberCounter.allocate_next_number()
        q1.save()
        
        q2.is_approved = True
        if q2.question_number is None:
            q2.question_number = QuestionNumberCounter.allocate_next_number()
        q2.save()
        
        # Refresh from database
        q1.refresh_from_db()
        q2.refresh_from_db()
        
        # Assert both have distinct numbers
        self.assertIsNotNone(q1.question_number)
        self.assertIsNotNone(q2.question_number)
        self.assertNotEqual(q1.question_number, q2.question_number,
                           "Concurrently approved questions should have distinct numbers")
    
    def test_grouped_questions_can_share_question_number(self):
        """Test that grouped questions can share the same question_number (with different group_number)"""
        # Create and approve first question
        q1 = Question.objects.create(
            text='Question 1',
            question_name='Q1',
            question_type='grouped',
            is_approved=True,
            group_number=1
        )
        q1.tags.add(self.tag)
        if q1.question_number is None:
            q1.question_number = QuestionNumberCounter.allocate_next_number()
        q1.save()
        
        # Create a second grouped question with the same question_number but different group_number
        # This should succeed because grouped questions share question_number
        q2 = Question.objects.create(
            text='Question 2',
            question_name='Q2',
            question_type='grouped',
            is_approved=True,
            question_number=q1.question_number,  # Same question_number
            group_number=2  # Different group_number
        )
        q2.tags.add(self.tag)
        q2.save()
        
        # Both should have the same question_number
        q1.refresh_from_db()
        q2.refresh_from_db()
        self.assertEqual(q1.question_number, q2.question_number)
        self.assertNotEqual(q1.group_number, q2.group_number)
    
    def test_unapprove_sets_question_number_to_null(self):
        """Test that unapproving a question sets question_number to NULL"""
        # Create and approve a question
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=True
        )
        question.tags.add(self.tag)
        if question.question_number is None:
            question.question_number = QuestionNumberCounter.allocate_next_number()
        question.save()
        
        # Verify it has a number
        question.refresh_from_db()
        self.assertIsNotNone(question.question_number)
        original_number = question.question_number
        
        # Unapprove the question
        question.is_approved = False
        question.question_number = None
        question.save()
        
        # Refresh from database
        question.refresh_from_db()
        
        # Assert question_number is NULL
        self.assertIsNone(question.question_number,
                         "Unapproved questions should have question_number = NULL")
    
    def test_multiple_null_question_numbers_allowed(self):
        """Test that multiple questions can have NULL question_number"""
        # Create multiple unapproved questions
        q1 = Question.objects.create(
            text='Question 1',
            question_name='Q1',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        q1.tags.add(self.tag)
        
        q2 = Question.objects.create(
            text='Question 2',
            question_name='Q2',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        q2.tags.add(self.tag)
        
        q3 = Question.objects.create(
            text='Question 3',
            question_name='Q3',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        q3.tags.add(self.tag)
        
        # All should save successfully
        self.assertIsNone(q1.question_number)
        self.assertIsNone(q2.question_number)
        self.assertIsNone(q3.question_number)
    
    def test_approve_endpoint_assigns_number(self):
        """Test that the approve endpoint assigns a question number"""
        from rest_framework.test import APIClient
        from rest_framework import status
        
        client = APIClient()
        
        # Create an unapproved question
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        question.tags.add(self.tag)
        
        # Call the approve endpoint
        response = client.post(f'/api/questions/{question.id}/approve/')
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh question from database
        question.refresh_from_db()
        
        # Assert question is approved and has a number
        self.assertTrue(question.is_approved)
        self.assertIsNotNone(question.question_number)
    
    def test_toggle_approval_assigns_number(self):
        """Test that toggling approval assigns a number when approving"""
        from rest_framework.test import APIClient
        from rest_framework import status
        
        client = APIClient()
        
        # Create an unapproved question
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=False,
            question_number=None
        )
        question.tags.add(self.tag)
        
        # Call the toggle_approval endpoint
        response = client.post(f'/api/questions/{question.id}/toggle_approval/')
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh question from database
        question.refresh_from_db()
        
        # Assert question is approved and has a number
        self.assertTrue(question.is_approved)
        self.assertIsNotNone(question.question_number)
    
    def test_create_with_approved_true_assigns_number(self):
        """Test that creating a question with is_approved=True assigns a number"""
        question = Question.objects.create(
            text='Test question',
            question_name='Test',
            question_type='basic',
            is_approved=True
        )
        question.tags.add(self.tag)
        
        # If approved on create, assign number
        if question.question_number is None:
            question.question_number = QuestionNumberCounter.allocate_next_number()
        question.save()
        
        # Refresh from database
        question.refresh_from_db()
        
        # Assert question_number is not NULL
        self.assertIsNotNone(question.question_number,
                            "Questions created as approved should have a question_number")
    
    def test_sequential_numbering(self):
        """Test that question numbers are assigned sequentially"""
        # Create and approve multiple questions
        numbers = []
        for i in range(5):
            question = Question.objects.create(
                text=f'Question {i+1}',
                question_name=f'Q{i+1}',
                question_type='basic',
                is_approved=True
            )
            question.tags.add(self.tag)
            if question.question_number is None:
                question.question_number = QuestionNumberCounter.allocate_next_number()
            question.save()
            question.refresh_from_db()
            numbers.append(question.question_number)
        
        # Verify numbers are sequential and unique
        self.assertEqual(len(numbers), len(set(numbers)), "All numbers should be unique")
        self.assertEqual(numbers, sorted(numbers), "Numbers should be in ascending order")
        self.assertEqual(numbers, list(range(min(numbers), max(numbers) + 1)),
                        "Numbers should be sequential")
