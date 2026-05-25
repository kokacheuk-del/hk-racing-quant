"""
Models package — SQLAlchemy ORM models.

Direct import to avoid DB initialization errors when running in live-only mode.
All models are exported directly for router imports.
"""

# Direct import from schema - removed the lazy import wrapper
# because routers do `from app.models import RaceMeeting` directly
from app.models.schema import (
    Horse, HorseWeightHistory, Jockey, Trainer, JockeyTrainerCombo,
    RaceMeeting, Race, Runner, SectionalTime, OddsSnapshot,
    ValueBetSignal, FeatureWeightProfile
)

# Also export for compatibility
__all__ = [
    "Horse", "HorseWeightHistory", "Jockey", "Trainer",
    "JockeyTrainerCombo", "RaceMeeting", "Race", "Runner",
    "SectionalTime", "OddsSnapshot", "ValueBetSignal",
    "FeatureWeightProfile",
]
