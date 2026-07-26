"""Settings and file names for reusable learning-item preparation."""

# Every topic receives three difficulty files for each item type: nine files in total.
QUESTION_BANK_DIFFICULTIES = ("easy", "medium", "hard")
ITEMS_PER_DIFFICULTY = 5
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
PREPARATION_OUTPUT_ATTEMPTS = 2
