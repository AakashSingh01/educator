"""Learning-session configuration shared by the UI and backend."""

TIMER_PRESETS = {
    "Slow": {"mcq": 120, "subjective": 240, "theory": None},
    "Normal": {"mcq": 60, "subjective": 120, "theory": None},
    "Fast": {"mcq": 30, "subjective": 60, "theory": None},
    "Infinite": {"mcq": None, "subjective": None, "theory": None},
}

QUESTION_MODE_TYPES = {
    "Objective": ("mcq",),
    "Subjective": ("subjective",),
    "Both": ("mcq", "subjective"),
}

LEARNING_MODE_TYPES = ("mcq", "subjective", "theory")


def get_time_limit(timer_preset, item_type):
    """Return seconds for an item type, or None when its time is unlimited."""
    return TIMER_PRESETS.get(timer_preset, TIMER_PRESETS["Normal"]).get(item_type)
