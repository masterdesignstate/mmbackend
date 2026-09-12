"""
Canonical numbering for the mandatory onboarding questions.

The three "multi" questions — Gender, Habits and Kids — used to pack two or three
sub-questions behind a single ``question_number``, which forced the onboarding page to
label every slider row. They are now standalone questions. Faith and Ideology were optional
until September 2026, when they joined the mandatory block (``backfill_faith_ideology``
filled them in for existing accounts), so it runs 1..16 and every optional question starts
at 17.

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
FAITH = 15
IDEOLOGY = 16

LAST_MANDATORY_QUESTION_NUMBER = IDEOLOGY
FIRST_OPTIONAL_QUESTION_NUMBER = LAST_MANDATORY_QUESTION_NUMBER + 1

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
