#!/usr/bin/env python3
"""
Test script to verify the compatibility algorithm matches the mathematical specification
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.services.compatibility_service import CompatibilityService
from api.models import Controls

def test_importance_mapping():
    """Test importance factor mapping"""
    print("🧪 Testing Importance Factor Mapping")
    print("Expected: 1→0, 2→0.5, 3→1, 4→2, 5→5 (with exponent=2)")

    for importance in range(1, 6):
        factor = CompatibilityService.map_importance_to_factor(importance)
        print(f"  Importance {importance} → Factor {factor}")

    # Verify exact values
    assert CompatibilityService.map_importance_to_factor(1) == 0.0
    assert CompatibilityService.map_importance_to_factor(2) == 0.5
    assert CompatibilityService.map_importance_to_factor(3) == 1.0
    assert CompatibilityService.map_importance_to_factor(4) == 2.0  # 1 + (4-3)^2
    assert CompatibilityService.map_importance_to_factor(5) == 5.0  # 1 + (5-3)^2
    print("✅ Importance mapping correct!\n")

def test_worked_example():
    """Test the worked micro-example from specification"""
    print("🧪 Testing Worked Example")
    print("Constants: ADJUST_VALUE=5, Exponent=2, OTA=0.5")
    print("One question, ImpRaw=5 → ImpFactor=5")
    print()

    # Get current controls
    controls = Controls.get_current()
    print(f"Current controls: adjust={controls.adjust}, exponent={controls.exponent}, ota={controls.ota}")

    # Test case from specification:
    # Direction A: My_Them=6 (open), Their_Me=2, ImpRaw=5
    # Direction B: My_Me=4, Their_Them=5, ImpRaw=5

    M_A, MAX_A, M_B, MAX_B = CompatibilityService.calculate_question_score(
        my_them=6,           # I'm open to all
        my_importance=5,     # Importance 5
        their_me=2,          # They say they are "2"
        my_me=4,             # I say I am "4"
        their_them=5,        # They want "5"
        their_importance=5,  # Their importance 5
        my_open_to_all=False,
        their_open_to_all=False
    )

    print(f"Direction A (Compatible with Me):")
    print(f"  M_A = {M_A}, MAX_A = {MAX_A}")
    print(f"  C_A = {M_A}/{MAX_A} = {M_A/MAX_A:.4f} = {(M_A/MAX_A)*100:.1f}%")
    print(f"  Expected: M_A=2.5, MAX_A=5, C_A=50%")

    print(f"Direction B (I'm Compatible with):")
    print(f"  M_B = {M_B}, MAX_B = {MAX_B}")
    print(f"  C_B = {M_B}/{MAX_B} = {M_B/MAX_B:.4f} = {(M_B/MAX_B)*100:.1f}%")
    print(f"  Expected: M_B=20, MAX_B=25, C_B=80%")

    C_A = M_A / MAX_A
    C_B = M_B / MAX_B
    overall = (C_A * C_B) ** 0.5

    print(f"Overall Compatibility:")
    print(f"  √(C_A × C_B) = √({C_A:.4f} × {C_B:.4f}) = √{C_A * C_B:.4f} = {overall:.4f} = {overall*100:.2f}%")
    print(f"  Expected: 63.25%")

    # Verify results match specification
    assert abs(M_A - 2.5) < 0.01, f"M_A should be 2.5, got {M_A}"
    assert abs(MAX_A - 5.0) < 0.01, f"MAX_A should be 5.0, got {MAX_A}"
    assert abs(M_B - 20.0) < 0.01, f"M_B should be 20.0, got {M_B}"
    assert abs(MAX_B - 25.0) < 0.01, f"MAX_B should be 25.0, got {MAX_B}"
    assert abs(C_A - 0.5) < 0.01, f"C_A should be 0.5, got {C_A}"
    assert abs(C_B - 0.8) < 0.01, f"C_B should be 0.8, got {C_B}"
    assert abs(overall - 0.6325) < 0.01, f"Overall should be 0.6325, got {overall}"

    print("✅ Worked example matches specification!\n")

def test_delta_scoring():
    """Test delta-based scoring vs binary matching"""
    print("🧪 Testing Delta-Based Scoring")
    print("Testing gradual scoring with different deltas")

    # Test different answer combinations with importance=3 (factor=1)
    test_cases = [
        (3, 3, "Perfect match"),      # Delta=0, should get full score
        (3, 4, "Close match"),        # Delta=1, should get reduced score
        (3, 5, "Far match"),          # Delta=2, should get low score
        (3, 1, "Very far match"),     # Delta=2, should get low score
    ]

    for my_answer, their_answer, description in test_cases:
        M_A, MAX_A, M_B, MAX_B = CompatibilityService.calculate_question_score(
            my_them=my_answer,
            my_importance=3,  # Factor = 1
            their_me=their_answer,
            my_me=3,
            their_them=3,
            their_importance=3,
            my_open_to_all=False,
            their_open_to_all=False
        )

        delta = abs(my_answer - their_answer)
        expected_adj = 5 - delta
        expected_M_A = max(0, expected_adj * 1)  # importance factor = 1

        print(f"  {description}: answers {my_answer}→{their_answer}, delta={delta}")
        print(f"    M_A={M_A}, expected={expected_M_A}, MAX_A={MAX_A}")
        print(f"    Score: {(M_A/MAX_A)*100:.1f}%")

        assert abs(M_A - expected_M_A) < 0.01, f"M_A should be {expected_M_A}, got {M_A}"

    print("✅ Delta-based scoring working correctly!\n")

if __name__ == "__main__":
    print("🚀 Testing Corrected Compatibility Algorithm")
    print("=" * 50)

    test_importance_mapping()
    test_worked_example()
    test_delta_scoring()

    print("🎉 All tests passed! Algorithm matches specification exactly.")