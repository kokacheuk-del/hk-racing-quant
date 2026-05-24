# Models package — import schema lazily to avoid DB crash on startup
# Only import when DB is actually needed (v1 routes)

def _import_models():
    """Lazy import all ORM models. Call only when DB is available."""
    from app.models.schema import (
        Horse, HorseWeightHistory, Jockey, Trainer, JockeyTrainerCombo,
        RaceMeeting, Race, Runner, SectionalTime, OddsSnapshot,
        ValueBetSignal, FeatureWeightProfile
    )
    return {
        "Horse": Horse, "HorseWeightHistory": HorseWeightHistory,
        "Jockey": Jockey, "Trainer": Trainer,
        "JockeyTrainerCombo": JockeyTrainerCombo,
        "RaceMeeting": RaceMeeting, "Race": Race, "Runner": Runner,
        "SectionalTime": SectionalTime, "OddsSnapshot": OddsSnapshot,
        "ValueBetSignal": ValueBetSignal, "FeatureWeightProfile": FeatureWeightProfile,
    }
