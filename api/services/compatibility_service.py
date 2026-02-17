import math
from functools import lru_cache
from typing import Dict, List, Tuple, Optional
from django.db.models import Q
from django.core.cache import cache
from django.db import IntegrityError
from ..models import User, UserAnswer, UserRequiredQuestion, Compatibility, Controls


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
    ) -> Dict[str, float]:
        """
        Calculate full compatibility between two users with caching.
        Required compatibility uses per-user UserRequiredQuestion (not UserAnswer).

        Returns dictionary with compatibility scores and metadata including:
        - overall_compatibility, compatible_with_me, im_compatible_with, mutual_questions_count
        - required_overall_compatibility, required_compatible_with_me, required_im_compatible_with
        - required_mutual_questions_count, user1_required_completeness, user2_required_completeness

        Args:
            user1: First user
            user2: Second user
            required_only: If True, only use questions marked as required for matching (legacy param)
            exclude_required: If True, caller is expected to supply answers with required questions removed
            user1_answers: Optional pre-fetched answers for user1 (required sets come from UserRequiredQuestion)
            user2_answers: Optional pre-fetched answers for user2 (required sets come from UserRequiredQuestion)
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

        # Calculate required compatibility (per-user: from UserRequiredQuestion)
        user1_required_qids = set(
            UserRequiredQuestion.objects.filter(user=user1).values_list('question_id', flat=True)
        )
        user2_required_qids = set(
            UserRequiredQuestion.objects.filter(user=user2).values_list('question_id', flat=True)
        )

        if not user1_required_qids and not user2_required_qids:
            # No per-user required: required scores equal overall, completeness 1.0
            result.update({
                'required_overall_compatibility': overall_compatibility,
                'required_compatible_with_me': compatible_with_me,
                'required_im_compatible_with': im_compatible_with,
                'their_required_compatibility': im_compatible_with,
                'required_mutual_questions_count': mutual_count,
                'user1_required_mutual_count': mutual_count,
                'user2_required_mutual_count': mutual_count,
                'user1_required_completeness': 1.0,
                'user2_required_completeness': 1.0,
                'required_completeness_ratio': 1.0,
            })
        else:
            # Per-user required: "my required" (user1's) and "their required" (user2's)
            a1_my_req = {qid: a1_all[qid] for qid in user1_required_qids if qid in a1_all}
            a2_for_my_req = {qid: a2_all[qid] for qid in user1_required_qids if qid in a2_all}
            a1_for_their_req = {qid: a1_all[qid] for qid in user2_required_qids if qid in a1_all}
            a2_their_req = {qid: a2_all[qid] for qid in user2_required_qids if qid in a2_all}

            # Score on questions I (user1) marked required -> required_compatible_with_me
            cw_me_1, im_cw_1, overall_1, n1 = CompatibilityService._compute_scores_from_answer_maps(
                a1_my_req, a2_for_my_req, constants
            )
            # Score on questions they (user2) marked required -> required_im_compatible_with
            cw_me_2, im_cw_2, overall_2, n2 = CompatibilityService._compute_scores_from_answer_maps(
                a1_for_their_req, a2_their_req, constants
            )

            required_compatible_with_me = cw_me_1
            required_im_compatible_with = im_cw_2
            # Their Required: compatibility using ONLY the other user's required questions (explicit third type)
            their_required_compatibility = im_cw_2  # score on user2's required (their required from user1's perspective)
            required_overall = (overall_1 + overall_2) / 2.0 if (user1_required_qids or user2_required_qids) else overall_compatibility
            required_mutual_count = n1 + n2

            # user1_required_completeness: of questions user2 marked required (and answered), what % did user1 answer?
            user2_required_answered = len(a2_their_req)
            user1_completeness = (len(a1_for_their_req) / user2_required_answered) if user2_required_answered > 0 else 0.0
            # user2_required_completeness: of questions user1 marked required (and answered), what % did user2 answer?
            user1_required_answered = len(a1_my_req)
            user2_completeness = (len(a2_for_my_req) / user1_required_answered) if user1_required_answered > 0 else 0.0

            user1_completeness = max(0.0, min(1.0, user1_completeness))
            user2_completeness = max(0.0, min(1.0, user2_completeness))
            combined_completeness = (user1_completeness + user2_completeness) / 2

            result.update({
                'required_overall_compatibility': round(required_overall, 2),
                'required_compatible_with_me': round(required_compatible_with_me, 2),
                'required_im_compatible_with': round(required_im_compatible_with, 2),
                'their_required_compatibility': round(their_required_compatibility, 2),
                'required_mutual_questions_count': required_mutual_count,
                'user1_required_mutual_count': n1,
                'user2_required_mutual_count': n2,
                'user1_required_completeness': round(user1_completeness, 3),
                'user2_required_completeness': round(user2_completeness, 3),
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
    def clear_user_compatibility_cache(user: User) -> int:
        """
        Clear all cached compatibility data involving this user.
        Returns the number of cache entries cleared.
        """
        # Get all other user IDs to clear caches
        other_user_ids = list(User.objects.exclude(id=user.id).values_list('id', flat=True))
        cleared = 0

        for other_id in other_user_ids:
            # Build cache keys for both orderings and all suffixes
            user_ids = sorted([str(user.id), str(other_id)])
            base_key = f"compatibility_{user_ids[0]}_{user_ids[1]}"

            for suffix in ['', '_required', '_exclude_required']:
                cache_key = f"{base_key}{suffix}"
                if cache.get(cache_key) is not None:
                    cache.delete(cache_key)
                    cleared += 1

        return cleared

    @staticmethod
    def recalculate_all_compatibilities(user: User, use_full_reset: bool = True) -> int:
        """
        Recalculate all compatibilities for a user (useful when their answers change)
        Now also computes required compatibility scores.
        Returns the number of compatibilities updated
        """
        print(f"🔄 Starting compatibility recalculation for user {user.username} ({user.id})", flush=True)

        # Clear cache first to ensure fresh calculations
        cache_cleared = CompatibilityService.clear_user_compatibility_cache(user)
        print(f"   🗑️  Cleared {cache_cleared} cached entries", flush=True)

        if use_full_reset:
            deleted_count = Compatibility.objects.filter(
                Q(user1=user) | Q(user2=user)
            ).delete()[0]
            print(f"   🗑️  Deleted {deleted_count} existing compatibility records (full reset)", flush=True)

        # Get all other users
        other_users = list(User.objects.exclude(id=user.id).exclude(is_banned=True))
        if not other_users:
            print(f"   ⚠️  No other users found to calculate compatibility with", flush=True)
            return 0

        print(f"   👥 Calculating compatibility with {len(other_users)} other users...", flush=True)

        # Fetch user answers (required sets come from UserRequiredQuestion)
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
        total_users = len(other_users)

        for idx, other_user in enumerate(other_users):
            # Print progress every 25 users or at the end
            if (idx + 1) % 25 == 0 or idx == total_users - 1:
                print(f"   📊 Progress: {idx + 1}/{total_users} users processed ({((idx + 1) / total_users * 100):.0f}%)", flush=True)
            other_answers_list = answers_by_user.get(str(other_user.id), [])
            compatibility_data = CompatibilityService.calculate_compatibility_between_users(
                user,
                other_user,
                user1_answers=user_answers,
                user2_answers=other_answers_list,
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
                comp.their_required_compatibility = compatibility_data['their_required_compatibility']
                comp.required_mutual_questions_count = compatibility_data['required_mutual_questions_count']
                comp.user1_required_completeness = compatibility_data['user1_required_completeness']
                comp.user2_required_completeness = compatibility_data['user2_required_completeness']
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
                # Their required: from user2's perspective = score on user1's required
                comp.their_required_compatibility = compatibility_data['required_compatible_with_me']
                comp.required_mutual_questions_count = compatibility_data['required_mutual_questions_count']
                # Completeness ratios also swap
                comp.user1_required_completeness = compatibility_data['user2_required_completeness']
                comp.user2_required_completeness = compatibility_data['user1_required_completeness']
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
                        their_required_compatibility=compatibility_data['their_required_compatibility'],
                        required_mutual_questions_count=compatibility_data['required_mutual_questions_count'],
                        user1_required_completeness=compatibility_data['user1_required_completeness'],
                        user2_required_completeness=compatibility_data['user2_required_completeness'],
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
            'their_required_compatibility',
            'required_mutual_questions_count',
            'user1_required_completeness',
            'user2_required_completeness',
            'required_completeness_ratio',
        ]

        if updates:
            Compatibility.objects.bulk_update(updates, update_fields)
            print(f"   ✏️  Updated {len(updates)} existing compatibility records", flush=True)
        if reverse_updates:
            Compatibility.objects.bulk_update(reverse_updates, update_fields)
            print(f"   ✏️  Updated {len(reverse_updates)} reverse compatibility records", flush=True)
        if to_create:
            Compatibility.objects.bulk_create(to_create, ignore_conflicts=True)
            print(f"   ✨ Created {len(to_create)} new compatibility records", flush=True)

        total_processed = len(updates) + len(reverse_updates) + len(to_create)
        print(f"✅ Completed compatibility recalculation for {user.username}: {total_processed} total pairs processed", flush=True)

        return created_count
