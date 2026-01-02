import math
from functools import lru_cache
from typing import Dict, List, Tuple, Optional
from django.db.models import Q
from django.core.cache import cache
from django.db import IntegrityError
from ..models import User, UserAnswer, Compatibility, Controls, Question


class CompatibilityService:
    """Service for calculating compatibility between users using the mathematical algorithm"""

    @staticmethod
    @lru_cache(maxsize=1)
    def get_constants() -> Dict[str, float]:
        """Get current control constants from database"""
        controls = Controls.get_current()
        return {
            'ADJUST_VALUE': controls.adjust,
            'EXPONENT': controls.exponent,
            'OTA': controls.ota
        }

    @staticmethod
    def clear_constants_cache() -> None:
        """Clear cached constants (useful if controls are updated)"""
        CompatibilityService.get_constants.cache_clear()

    @staticmethod
    def map_importance_to_factor(importance: int, exponent: Optional[float] = None) -> float:
        """Map importance level (1-5) to importance factor per specification"""
        if exponent is None:
            exponent = CompatibilityService.get_constants()['EXPONENT']

        if importance == 1:
            return 0.0
        elif importance == 2:
            return 0.5
        elif importance == 3:
            return 1.0
        elif importance in [4, 5]:
            # 1 + (importance - 3)^exponent
            return 1.0 + (importance - 3) ** exponent
        else:
            return 1.0  # fallback

    @staticmethod
    def calculate_question_score(
        my_them: int,           # What I want from them (my_answer in Direction A)
        my_importance: int,     # My importance for this preference
        their_me: int,          # What they say about themselves (their_answer in Direction A)
        my_me: int,             # What I say about myself (my_answer in Direction B)
        their_them: int,        # What they want from a partner (their_answer in Direction B)
        their_importance: int,  # Their importance for this preference
        my_open_to_all: bool = False,
        their_open_to_all: bool = False,
        constants: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float, float, float]:
        """
        Calculate question score per your mathematical specification
        Returns (M_A, MAX_A, M_B, MAX_B) for proper weighted averaging
        """
        if constants is None:
            constants = CompatibilityService.get_constants()
        adjust_value = constants['ADJUST_VALUE']
        ota = constants['OTA']

        exponent = constants['EXPONENT']
        my_importance_factor = CompatibilityService.map_importance_to_factor(my_importance, exponent)
        their_importance_factor = CompatibilityService.map_importance_to_factor(their_importance, exponent)

        # Direction A: "Compatible with Me" - How well they fit what I want
        # Compare: My_Them[i] vs Their_Me[i]
        if my_open_to_all or my_them == 6 or their_me == 6:
            # Open-to-All rule triggers
            M_A = adjust_value * ota
            MAX_A = adjust_value
        else:
            # Standard delta-based calculation
            delta_A = abs(my_them - their_me)
            adj_A = adjust_value - delta_A
            M_A = max(0.0, adj_A * my_importance_factor)  # Ensure non-negative
            MAX_A = adjust_value * my_importance_factor

        # Direction B: "I'm Compatible with" - How well I fit what they want
        # Compare: My_Me[i] vs Their_Them[i]
        if their_open_to_all or their_them == 6 or my_me == 6:
            # Open-to-All rule triggers
            M_B = adjust_value * ota
            MAX_B = adjust_value
        else:
            # Standard delta-based calculation
            delta_B = abs(my_me - their_them)
            adj_B = adjust_value - delta_B
            M_B = max(0.0, adj_B * their_importance_factor)  # Ensure non-negative
            MAX_B = adjust_value * their_importance_factor

        return M_A, MAX_A, M_B, MAX_B

    @staticmethod
    def _compute_scores_from_answer_maps(
        a1_map: Dict,
        a2_map: Dict,
        constants: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float, float, int]:
        """
        Core helper: compute compatibility scores from two answer dictionaries keyed by question_id.
        
        Returns:
            (compatible_with_me, im_compatible_with, overall_compatibility, mutual_count)
        """
        if constants is None:
            constants = CompatibilityService.get_constants()

        # Find mutual questions
        mutual_question_ids = set(a1_map.keys()) & set(a2_map.keys())

        if not mutual_question_ids:
            return 0.0, 0.0, 0.0, 0

        total_M_A = 0.0
        total_MAX_A = 0.0
        total_M_B = 0.0
        total_MAX_B = 0.0

        # Calculate scores for each mutual question
        for question_id in mutual_question_ids:
            user1_answer = a1_map[question_id]
            user2_answer = a2_map[question_id]

            M_A, MAX_A, M_B, MAX_B = CompatibilityService.calculate_question_score(
                my_them=user1_answer.looking_for_answer,
                my_importance=user1_answer.looking_for_importance,
                their_me=user2_answer.me_answer,
                my_me=user1_answer.me_answer,
                their_them=user2_answer.looking_for_answer,
                their_importance=user2_answer.looking_for_importance,
                my_open_to_all=user1_answer.looking_for_open_to_all,
                their_open_to_all=user2_answer.me_open_to_all,
                constants=constants,
            )

            total_M_A += M_A
            total_MAX_A += MAX_A
            total_M_B += M_B
            total_MAX_B += MAX_B

        # Calculate directional percentages
        direction_a_percentage = (total_M_A / total_MAX_A) if total_MAX_A > 0 else 0.0
        direction_b_percentage = (total_M_B / total_MAX_B) if total_MAX_B > 0 else 0.0

        # Convert to percentages (0-100)
        direction_a_percentage *= 100
        direction_b_percentage *= 100

        # Calculate overall compatibility as geometric mean
        if direction_a_percentage > 0 and direction_b_percentage > 0:
            overall_compatibility = math.sqrt(direction_a_percentage * direction_b_percentage)
        else:
            overall_compatibility = 0.0

        return (
            round(direction_a_percentage, 2),
            round(direction_b_percentage, 2),
            round(overall_compatibility, 2),
            len(mutual_question_ids)
        )

    @staticmethod
    def calculate_compatibility_between_users(
        user1: User,
        user2: User,
        required_only: bool = False,
        exclude_required: bool = False,
        user1_answers: Optional[List[UserAnswer]] = None,
        user2_answers: Optional[List[UserAnswer]] = None,
        total_required_count: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate full compatibility between two users with caching.
        Now also computes required compatibility scores.
        
        Returns dictionary with compatibility scores and metadata including:
        - overall_compatibility, compatible_with_me, im_compatible_with, mutual_questions_count
        - required_overall_compatibility, required_compatible_with_me, required_im_compatible_with
        - required_mutual_questions_count, required_completeness_ratio

        Args:
            user1: First user
            user2: Second user
            required_only: If True, only use questions marked as required for matching (legacy param)
            exclude_required: If True, caller is expected to supply answers with required questions removed
            user1_answers: Optional pre-fetched answers for user1 (with select_related('question'))
            user2_answers: Optional pre-fetched answers for user2 (with select_related('question'))
            total_required_count: Optional pre-computed count of total required questions (for optimization)
        """
        if required_only and exclude_required:
            raise ValueError("required_only and exclude_required cannot both be True")

        # Check cache first (different cache key for required_only/exclude_required)
        cache_suffix = "_required" if required_only else "_exclude_required" if exclude_required else ""
        cache_key = f"compatibility_{min(user1.id, user2.id)}_{max(user1.id, user2.id)}{cache_suffix}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        # Fetch answers if not provided
        if user1_answers is None:
            user1_answers_query = UserAnswer.objects.filter(user=user1).select_related('question')
            if required_only:
                user1_answers_query = user1_answers_query.filter(question__is_required_for_match=True)
            user1_answers = list(user1_answers_query.only(
                'question_id',
                'me_answer',
                'me_open_to_all',
                'me_importance',
                'looking_for_answer',
                'looking_for_open_to_all',
                'looking_for_importance',
            ))
        else:
            user1_answers = list(user1_answers)

        if user2_answers is None:
            user2_answers_query = UserAnswer.objects.filter(user=user2).select_related('question')
            if required_only:
                user2_answers_query = user2_answers_query.filter(question__is_required_for_match=True)
            user2_answers = list(user2_answers_query.only(
                'question_id',
                'me_answer',
                'me_open_to_all',
                'me_importance',
                'looking_for_answer',
                'looking_for_open_to_all',
                'looking_for_importance',
            ))
        else:
            user2_answers = list(user2_answers)

        constants = CompatibilityService.get_constants()

        # Build answer dictionaries (all answers)
        a1_all = {answer.question_id: answer for answer in user1_answers}
        a2_all = {answer.question_id: answer for answer in user2_answers}

        # Calculate regular compatibility using helper
        compatible_with_me, im_compatible_with, overall_compatibility, mutual_count = \
            CompatibilityService._compute_scores_from_answer_maps(a1_all, a2_all, constants)

        result = {
            'overall_compatibility': overall_compatibility,
            'compatible_with_me': compatible_with_me,
            'im_compatible_with': im_compatible_with,
            'mutual_questions_count': mutual_count,
        }

        # Calculate required compatibility
        if total_required_count is None:
            total_required_count = Question.objects.filter(is_required_for_match=True).count()

        if total_required_count == 0:
            # No required questions: required scores equal overall scores
            result.update({
                'required_overall_compatibility': overall_compatibility,
                'required_compatible_with_me': compatible_with_me,
                'required_im_compatible_with': im_compatible_with,
                'required_mutual_questions_count': mutual_count,
                'required_completeness_ratio': 1.0,
            })
        else:
            # Build required-only answer dictionaries
            # Fetch question IDs that are required (optimize: cache this if called multiple times)
            required_question_ids = set(
                Question.objects.filter(is_required_for_match=True).values_list('id', flat=True)
            )
            
            # Filter answers to only those for required questions
            a1_req = {
                qid: answer for qid, answer in a1_all.items()
                if qid in required_question_ids
            }
            a2_req = {
                qid: answer for qid, answer in a2_all.items()
                if qid in required_question_ids
            }

            # Compute completeness ratio (penalty multiplier)
            user1_required_answered = len(a1_req)
            user2_required_answered = len(a2_req)
            combined_completeness = min(user1_required_answered, user2_required_answered) / total_required_count
            combined_completeness = max(0.0, min(1.0, combined_completeness))  # Clamp 0-1

            # Find mutual required questions
            mutual_req_ids = set(a1_req.keys()) & set(a2_req.keys())
            required_mutual_count = len(mutual_req_ids)

            if required_mutual_count == 0:
                # No mutual required questions
                result.update({
                    'required_overall_compatibility': 0.0,
                    'required_compatible_with_me': 0.0,
                    'required_im_compatible_with': 0.0,
                    'required_mutual_questions_count': 0,
                    'required_completeness_ratio': round(combined_completeness, 3),
                })
            else:
                # Calculate base required compatibility on mutual required questions
                base_req_compatible_with_me, base_req_im_compatible_with, base_req_overall, _ = \
                    CompatibilityService._compute_scores_from_answer_maps(a1_req, a2_req, constants)

                # Apply completeness penalty multiplier
                required_compatible_with_me = round(base_req_compatible_with_me * combined_completeness, 2)
                required_im_compatible_with = round(base_req_im_compatible_with * combined_completeness, 2)
                required_overall = round(base_req_overall * combined_completeness, 2)

                result.update({
                    'required_overall_compatibility': required_overall,
                    'required_compatible_with_me': required_compatible_with_me,
                    'required_im_compatible_with': required_im_compatible_with,
                    'required_mutual_questions_count': required_mutual_count,
                    'required_completeness_ratio': round(combined_completeness, 3),
                })

        # Cache the result for 1 hour
        cache.set(cache_key, result, 3600)
        return result

    @staticmethod
    def get_compatible_users(
        user: User,
        compatibility_type: str = 'overall',
        min_compatibility: float = 0.0,
        max_compatibility: float = 100.0,
        limit: int = 15,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get users compatible with the given user, sorted by compatibility
        """
        # Get all other users (excluding self) - limit to 50 for performance
        other_users = User.objects.exclude(id=user.id).exclude(is_banned=True).filter(
            answers__isnull=False  # Only users with answers
        ).distinct()[:50]  # Limit to 50 users for performance

        compatible_users = []

        for other_user in other_users:
            # Check if compatibility already exists in database
            compatibility_obj = Compatibility.objects.filter(
                Q(user1=user, user2=other_user) | Q(user1=other_user, user2=user)
            ).first()

            if compatibility_obj:
                # Use existing compatibility data
                if compatibility_obj.user1 == user:
                    compatibility_data = {
                        'overall_compatibility': float(compatibility_obj.overall_compatibility or 0),
                        'compatible_with_me': float(compatibility_obj.compatible_with_me or 0),
                        'im_compatible_with': float(compatibility_obj.im_compatible_with or 0),
                        'mutual_questions_count': compatibility_obj.mutual_questions_count
                    }
                else:
                    # Swap directions if the compatibility record has users in reverse order
                    compatibility_data = {
                        'overall_compatibility': float(compatibility_obj.overall_compatibility or 0),
                        'compatible_with_me': float(compatibility_obj.im_compatible_with or 0),
                        'im_compatible_with': float(compatibility_obj.compatible_with_me or 0),
                        'mutual_questions_count': compatibility_obj.mutual_questions_count
                    }
            else:
                # Calculate new compatibility
                compatibility_data = CompatibilityService.calculate_compatibility_between_users(user, other_user)

                # Save to database for future use (using get_or_create to avoid duplicates)
                Compatibility.objects.get_or_create(
                    user1=user,
                    user2=other_user,
                    defaults={
                        'overall_compatibility': compatibility_data['overall_compatibility'],
                        'compatible_with_me': compatibility_data['compatible_with_me'],
                        'im_compatible_with': compatibility_data['im_compatible_with'],
                        'mutual_questions_count': compatibility_data['mutual_questions_count']
                    }
                )

            # Apply compatibility filter based on type
            compatibility_score = compatibility_data.get(compatibility_type, 0.0)

            if min_compatibility <= compatibility_score <= max_compatibility:
                compatible_users.append({
                    'user': other_user,
                    'compatibility': compatibility_data
                })

        # Sort by the selected compatibility type (descending)
        compatible_users.sort(key=lambda x: x['compatibility'].get(compatibility_type, 0.0), reverse=True)

        # Apply pagination
        return compatible_users[offset:offset + limit]

    @staticmethod
    def recalculate_all_compatibilities(user: User, use_full_reset: bool = True) -> int:
        """
        Recalculate all compatibilities for a user (useful when their answers change)
        Now also computes required compatibility scores.
        Returns the number of compatibilities updated
        """
        if use_full_reset:
            Compatibility.objects.filter(
                Q(user1=user) | Q(user2=user)
            ).delete()

        # Get all other users
        other_users = list(User.objects.exclude(id=user.id).exclude(is_banned=True))
        if not other_users:
            return 0

        # Compute total_required_count once for optimization
        total_required_count = Question.objects.filter(is_required_for_match=True).count()

        # Fetch user answers with question relationship for required filtering
        user_answers = list(
            user.answers.select_related('question').only(
                'question_id',
                'me_answer',
                'me_open_to_all',
                'me_importance',
                'looking_for_answer',
                'looking_for_open_to_all',
                'looking_for_importance',
            )
        )

        other_answers = UserAnswer.objects.filter(user__in=other_users).select_related('question').only(
            'user_id',
            'question_id',
            'me_answer',
            'me_open_to_all',
            'me_importance',
            'looking_for_answer',
            'looking_for_open_to_all',
            'looking_for_importance',
        )

        answers_by_user: dict[str, list[UserAnswer]] = {}
        for answer in other_answers:
            answers_by_user.setdefault(str(answer.user_id), []).append(answer)

        existing_comps = Compatibility.objects.filter(
            Q(user1=user) | Q(user2=user)
        )
        existing_map: dict[tuple[str, str], Compatibility] = {}
        for comp in existing_comps:
            existing_map[(str(comp.user1_id), str(comp.user2_id))] = comp

        created_count = 0
        updates: list[Compatibility] = []
        reverse_updates: list[Compatibility] = []
        to_create: list[Compatibility] = []

        for other_user in other_users:
            other_answers_list = answers_by_user.get(str(other_user.id), [])
            compatibility_data = CompatibilityService.calculate_compatibility_between_users(
                user,
                other_user,
                user1_answers=user_answers,
                user2_answers=other_answers_list,
                total_required_count=total_required_count,
            )

            key_direct = (str(user.id), str(other_user.id))
            key_reverse = (str(other_user.id), str(user.id))

            if key_direct in existing_map:
                comp = existing_map[key_direct]
                comp.overall_compatibility = compatibility_data['overall_compatibility']
                comp.compatible_with_me = compatibility_data['compatible_with_me']
                comp.im_compatible_with = compatibility_data['im_compatible_with']
                comp.mutual_questions_count = compatibility_data['mutual_questions_count']
                comp.required_overall_compatibility = compatibility_data['required_overall_compatibility']
                comp.required_compatible_with_me = compatibility_data['required_compatible_with_me']
                comp.required_im_compatible_with = compatibility_data['required_im_compatible_with']
                comp.required_mutual_questions_count = compatibility_data['required_mutual_questions_count']
                comp.required_completeness_ratio = compatibility_data['required_completeness_ratio']
                updates.append(comp)
            elif key_reverse in existing_map:
                comp = existing_map[key_reverse]
                # Swap directional fields because orientation is reversed
                comp.overall_compatibility = compatibility_data['overall_compatibility']
                comp.compatible_with_me = compatibility_data['im_compatible_with']
                comp.im_compatible_with = compatibility_data['compatible_with_me']
                comp.mutual_questions_count = compatibility_data['mutual_questions_count']
                # Required scores also need direction swap
                comp.required_overall_compatibility = compatibility_data['required_overall_compatibility']
                comp.required_compatible_with_me = compatibility_data['required_im_compatible_with']
                comp.required_im_compatible_with = compatibility_data['required_compatible_with_me']
                comp.required_mutual_questions_count = compatibility_data['required_mutual_questions_count']
                comp.required_completeness_ratio = compatibility_data['required_completeness_ratio']
                reverse_updates.append(comp)
            else:
                to_create.append(
                    Compatibility(
                        user1=user,
                        user2=other_user,
                        overall_compatibility=compatibility_data['overall_compatibility'],
                        compatible_with_me=compatibility_data['compatible_with_me'],
                        im_compatible_with=compatibility_data['im_compatible_with'],
                        mutual_questions_count=compatibility_data['mutual_questions_count'],
                        required_overall_compatibility=compatibility_data['required_overall_compatibility'],
                        required_compatible_with_me=compatibility_data['required_compatible_with_me'],
                        required_im_compatible_with=compatibility_data['required_im_compatible_with'],
                        required_mutual_questions_count=compatibility_data['required_mutual_questions_count'],
                        required_completeness_ratio=compatibility_data['required_completeness_ratio'],
                    )
                )
                created_count += 1

        update_fields = [
            'overall_compatibility',
            'compatible_with_me',
            'im_compatible_with',
            'mutual_questions_count',
            'required_overall_compatibility',
            'required_compatible_with_me',
            'required_im_compatible_with',
            'required_mutual_questions_count',
            'required_completeness_ratio',
        ]

        if updates:
            Compatibility.objects.bulk_update(updates, update_fields)
        if reverse_updates:
            Compatibility.objects.bulk_update(reverse_updates, update_fields)
        if to_create:
            Compatibility.objects.bulk_create(to_create, ignore_conflicts=True)

        return created_count
