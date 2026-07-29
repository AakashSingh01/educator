"""Settings and file names for reusable learning-item preparation."""

# Every topic receives three difficulty files for each item type: nine files in total.
QUESTION_BANK_DIFFICULTIES = ("easy", "medium", "hard")
# Try 15 items first (5 per difficulty). Small topics fall back to 12, 9, then 6.
QUESTION_BANK_ITEMS_PER_DIFFICULTY = (5, 4, 3, 2)
QUESTION_BANK_VERSION = 1

QUESTION_BANK_FILES = {
    "subjective": {
        difficulty: f"subjective_{difficulty}.json"
        for difficulty in QUESTION_BANK_DIFFICULTIES
    },
    "mcq": {
        difficulty: f"objective_{difficulty}.json"
        for difficulty in QUESTION_BANK_DIFFICULTIES
    },
    "theory": {
        difficulty: f"theory_{difficulty}.json"
        for difficulty in QUESTION_BANK_DIFFICULTIES
    },
}

# Used automatically for independent topic folders; this is intentionally not a UI setting.
PREPARATION_WORKERS = 4
# A malformed response is handled by tolerant parsing. Do not pay for the same
# request twice before moving to the existing 15/12/9/6 fallback.
PREPARATION_OUTPUT_ATTEMPTS = 1

# Repeatedly sending very long notes is the largest input-token cost during a
# preparation run. These limits keep each of the four calls per item type small.
QUESTION_BANK_NOTES_CHAR_LIMIT = 6000
QUESTION_BANK_OUTLINE_MAX_OUTPUT_TOKENS = 1800
QUESTION_BANK_SUBJECTIVE_MAX_OUTPUT_TOKENS = 2000
QUESTION_BANK_OBJECTIVE_MAX_OUTPUT_TOKENS = 3600
QUESTION_BANK_THEORY_MAX_OUTPUT_TOKENS = 2600


def normalise_difficulties(difficulties=None):
    """Return validated difficulty names in the application's stable order."""

    if difficulties is None:
        return QUESTION_BANK_DIFFICULTIES
    if isinstance(difficulties, str):
        difficulties = (difficulties,)
    try:
        requested = {
            difficulty.strip().casefold()
            for difficulty in difficulties
            if isinstance(difficulty, str) and difficulty.strip()
        }
    except TypeError as error:
        raise ValueError("Choose at least one valid difficulty.") from error
    if not requested or not requested.issubset(QUESTION_BANK_DIFFICULTIES):
        raise ValueError("Choose at least one valid difficulty.")
    return tuple(
        difficulty
        for difficulty in QUESTION_BANK_DIFFICULTIES
        if difficulty in requested
    )
