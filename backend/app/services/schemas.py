"""
Pydantic Schemas for API request/response validation.
"""
from datetime import datetime, date, time
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════
#  Horse Schemas
# ═══════════════════════════════════════════════

class HorseBase(BaseModel):
    brand_number: str
    name_en: str
    name_ch: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    sire: Optional[str] = None
    dam: Optional[str] = None
    rating: Optional[int] = None


class HorseResponse(HorseBase):
    id: int
    total_starts: int
    total_wins: int
    win_strike_rate: Optional[float] = None
    place_strike_rate: Optional[float] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════
#  Jockey / Trainer Schemas
# ═══════════════════════════════════════════════

class JockeyResponse(BaseModel):
    id: int
    name_en: str
    name_ch: Optional[str] = None
    total_starts: int
    total_wins: int
    win_strike_rate: Optional[float] = None
    stv_win_rate: Optional[float] = None
    hv_win_rate: Optional[float] = None

    model_config = {"from_attributes": True}


class TrainerResponse(BaseModel):
    id: int
    name_en: str
    name_ch: Optional[str] = None
    total_starts: int
    total_wins: int
    win_strike_rate: Optional[float] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════
#  Race Schemas
# ═══════════════════════════════════════════════

class RaceMeetingResponse(BaseModel):
    id: int
    meeting_date: date
    venue: str
    course: Optional[str] = None
    going: Optional[str] = None
    weather: Optional[str] = None
    total_races: Optional[int] = None

    model_config = {"from_attributes": True}


class RunnerInRace(BaseModel):
    """賽事中的馬匹摘要"""
    runner_id: int
    runner_number: int
    horse_name_en: str
    horse_name_ch: Optional[str] = None
    barrier: int
    declared_weight: Optional[float] = None
    jockey_name: Optional[str] = None
    trainer_name: Optional[str] = None
    win_odds: Optional[float] = None
    true_probability: Optional[float] = None
    market_probability: Optional[float] = None
    expected_value: Optional[float] = None
    is_value_bet: bool = False
    kelly_fraction: Optional[float] = None


class RaceDetailResponse(BaseModel):
    id: int
    race_number: int
    race_class: Optional[str] = None
    distance: Optional[int] = None
    race_name_en: Optional[str] = None
    going: Optional[str] = None
    pace_scenario: Optional[str] = None
    is_completed: bool = False
    runners: List[RunnerInRace] = []

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════
#  Quant Analysis Schemas
# ═══════════════════════════════════════════════

class QuantAnalysisRequest(BaseModel):
    """量化分析請求"""
    race_id: int
    feature_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="自訂特徵權重，如 {'w_barrier': 1.5, 'w_jockey': 2.0}"
    )


class ValueBetSignalResponse(BaseModel):
    runner_id: int
    runner_number: int
    horse_name: str
    true_probability: float
    market_probability: float
    win_odds: float
    expected_value: float
    is_value_bet: bool
    kelly_fraction: float
    edge_percentage: float
    confidence_level: str


class RaceAnalysisResponse(BaseModel):
    """完整賽事分析結果"""
    race_id: int
    race_number: int
    distance: int
    venue: str
    going: Optional[str] = None
    pace_scenario: str
    pace_detail: Dict
    value_bets: List[ValueBetSignalResponse]
    all_runners: List[ValueBetSignalResponse]


# ═══════════════════════════════════════════════
#  Odds / Smart Money Schemas
# ═══════════════════════════════════════════════

class OddsSnapshotResponse(BaseModel):
    runner_id: int
    timestamp: datetime
    win_odds: float
    win_pool: Optional[int] = None
    odds_delta: Optional[float] = None
    is_smart_money: bool = False


class SmartMoneyAlertResponse(BaseModel):
    """聰明錢警報"""
    runner_id: int
    runner_number: int
    horse_name: str
    odds_before: float
    odds_current: float
    odds_drop_percentage: float
    pool_surge_percentage: float
    alert_time: datetime


# ═══════════════════════════════════════════════
#  CSV Import Schema
# ═══════════════════════════════════════════════

class CSVImportResult(BaseModel):
    total_rows: int
    imported: int
    skipped: int
    errors: List[str] = []


# ═══════════════════════════════════════════════
#  Feature Weight Profile
# ═══════════════════════════════════════════════

class FeatureWeightProfileCreate(BaseModel):
    profile_name: str
    w_barrier: float = 1.0
    w_jockey: float = 1.0
    w_trainer: float = 1.0
    w_jt_combo: float = 1.0
    w_recent_form: float = 1.0
    w_class_drop: float = 1.0
    w_class_rise: float = 1.0
    w_distance_suitability: float = 1.0
    w_going_preference: float = 1.0
    w_weight_change: float = 1.0
    w_speed_figure: float = 1.0
    w_pace_scenario: float = 1.0
    w_smart_money: float = 1.5


class FeatureWeightProfileResponse(FeatureWeightProfileCreate):
    id: int
    is_default: bool = False

    model_config = {"from_attributes": True}
