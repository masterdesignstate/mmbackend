"""
Canonical numbering for the mandatory onboarding questions.

The three "multi" questions — Gender, Habits and Kids — used to pack two or three
sub-questions behind a single ``question_number``, which forced the onboarding page to
label every slider row. They are now standalone questions, so the mandatory block runs
1..14 and every optional question starts at 15.

Import from here instead of writing the literals; the split is easy to get subtly wrong
when the numbers are scattered across views, serializers and scripts.
"""

RELATIONSHIP = 1
FEMALE = 2
MALE = 3
ETHNICITY = 4
EDUCATION = 5
DIET = 6
EXERCISE = 7
ALCOHOL = 8
CIGARETTES = 9
VAPE = 10
RELIGION = 11
POLITICS = 12
WANT_KIDS = 13
HAVE_KIDS = 14

LAST_MANDATORY_QUESTION_NUMBER = HAVE_KIDS
FIRST_OPTIONAL_QUESTION_NUMBER = LAST_MANDATORY_QUESTION_NUMBER + 1

# Optional questions that still carry per-number behaviour.
FAITH = 15
IDEOLOGY = 16

MANDATORY_QUESTION_NUMBERS = tuple(range(RELATIONSHIP, LAST_MANDATORY_QUESTION_NUMBER + 1))

# Questions whose exclusion picker is the plain 1-5 scale, even where the answer UI is
# grouped and the stored answers only cover part of the range.
FULL_SCALE_EXCLUSION_NUMBERS = frozenset({
    FEMALE, MALE, ETHNICITY, ALCOHOL, CIGARETTES, VAPE, RELIGION, FAITH,
})

# Questions answered on a partial scale.
EDUCATION_EXCLUSION_VALUES = {1, 3, 5}
HAVE_KIDS_EXCLUSION_VALUES = {1, 5}

# Questions that make up the "who is this person" summary on the admin profile list.
PROFILE_SUMMARY_QUESTION_NUMBERS = (RELATIONSHIP, FEMALE, MALE)
