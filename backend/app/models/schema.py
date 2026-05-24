"""
Database Models (Schema) for HK Racing Quant System.

Core entities:
  - Horse: 馬匹基礎檔案
  - Jockey: 騎師檔案
  - Trainer: 練馬師檔案
  - RaceMeeting: 賽事日
  - Race: 單場賽事
  - Runner: 出賽馬匹（含排位、負磅等臨場數據）
  - RaceResult: 賽果
  - SectionalTime: 分段時間
  - OddsSnapshot: 即時賠率快照
  - ValueBetSignal: +EV 訊號記錄
  - FeatureWeight: 使用者自訂特徵權重
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Date, DateTime, Time,
    Boolean, Text, ForeignKey, Index, UniqueConstraint, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database import Base

# ─────────────────────────────────────────────
# 1. 基礎實體：馬匹 / 騎師 / 練馬師
# ─────────────────────────────────────────────

class Horse(Base):
    """馬匹基礎檔案"""
    __tablename__ = "horses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_number = Column(String(20), unique=True, nullable=False, comment="烙印編號，如 S123")
    name_en = Column(String(100), nullable=False, comment="英文馬名")
    name_ch = Column(String(100), comment="中文馬名")
    age = Column(Integer, comment="年齡")
    sex = Column(String(10), comment="性別：Colt/Filly/Gelding/Mare/Horse")
    colour = Column(String(20), comment="毛色")
    country_of_origin = Column(String(50), comment="出生國")
    sire = Column(String(100), comment="父系")
    dam = Column(String(100), comment="母系")
    trainer_id = Column(Integer, ForeignKey("trainers.id"), comment="現任練馬師")
    rating = Column(Integer, comment="現時評分")
    seasonal_rating = Column(Integer, comment="季內評分")

    # 統計快照（定期更新）
    total_starts = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_seconds = Column(Integer, default=0)
    total_thirds = Column(Integer, default=0)
    win_strike_rate = Column(Float, comment="勝出率 0-1")
    place_strike_rate = Column(Float, comment="入位率 0-1")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    trainer = relationship("Trainer", back_populates="horses")
    runners = relationship("Runner", back_populates="horse")
    weight_history = relationship("HorseWeightHistory", back_populates="horse")

    def __repr__(self):
        return f"<Horse {self.brand_number} {self.name_en}>"


class HorseWeightHistory(Base):
    """馬匹體重歷史（追蹤體重變幅）"""
    __tablename__ = "horse_weight_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    horse_id = Column(Integer, ForeignKey("horses.id"), nullable=False)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    weight_lbs = Column(Float, comment="體重（磅）")
    weight_delta = Column(Float, comment="與前場體重差值")
    declared_weight = Column(Float, comment="宣佈負磅")

    horse = relationship("Horse", back_populates="weight_history")
    race = relationship("Race")

    __table_args__ = (Index("ix_weight_horse_date", "horse_id", "race_id"),)


class Jockey(Base):
    """騎師檔案"""
    __tablename__ = "jockeys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name_en = Column(String(100), nullable=False)
    name_ch = Column(String(100))
    licence_number = Column(String(20), unique=True)
    allowance = Column(Integer, default=0, comment="見習減磅")

    # 統計
    total_starts = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    win_strike_rate = Column(Float)
    place_strike_rate = Column(Float)

    # 場地偏好
    stv_win_rate = Column(Float, comment="沙田勝出率")
    hv_win_rate = Column(Float, comment="跑馬地勝出率")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runners = relationship("Runner", back_populates="jockey")
    jockey_trainer_stats = relationship("JockeyTrainerCombo", back_populates="jockey")

    def __repr__(self):
        return f"<Jockey {self.name_en}>"


class Trainer(Base):
    """練馬師檔案"""
    __tablename__ = "trainers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name_en = Column(String(100), nullable=False)
    name_ch = Column(String(100))
    licence_number = Column(String(20), unique=True)

    # 統計
    total_starts = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    win_strike_rate = Column(Float)
    place_strike_rate = Column(Float)

    # 場地偏好
    stv_win_rate = Column(Float)
    hv_win_rate = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    horses = relationship("Horse", back_populates="trainer")
    jockey_trainer_stats = relationship("JockeyTrainerCombo", back_populates="trainer")

    def __repr__(self):
        return f"<Trainer {self.name_en}>"


class JockeyTrainerCombo(Base):
    """騎練組合歷史統計"""
    __tablename__ = "jockey_trainer_combo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jockey_id = Column(Integer, ForeignKey("jockeys.id"), nullable=False)
    trainer_id = Column(Integer, ForeignKey("trainers.id"), nullable=False)
    season = Column(String(10), comment="賽季，如 2024/2025")

    starts = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    seconds = Column(Integer, default=0)
    thirds = Column(Integer, default=0)
    win_rate = Column(Float)
    place_rate = Column(Float)

    jockey = relationship("Jockey", back_populates="jockey_trainer_stats")
    trainer = relationship("Trainer", back_populates="jockey_trainer_stats")

    __table_args__ = (
        UniqueConstraint("jockey_id", "trainer_id", "season", name="uq_jt_season"),
        Index("ix_jt_lookup", "jockey_id", "trainer_id"),
    )


# ─────────────────────────────────────────────
# 2. 賽事結構：賽日 → 場次 → 出賽馬
# ─────────────────────────────────────────────

class RaceMeeting(Base):
    """賽事日（一天的所有比賽）"""
    __tablename__ = "race_meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_date = Column(Date, nullable=False, comment="賽事日期")
    venue = Column(String(20), nullable=False, comment="賽道：STV=沙田, HV=跑馬地")
    course = Column(String(5), comment="跑道：A/B/C/C+3 等")
    going = Column(String(30), comment="場地狀況：Good/Yielding/Soft/Muddy")
    weather = Column(String(50), comment="天氣描述")
    rail_position = Column(String(20), comment="欄位位置")

    total_races = Column(Integer, comment="該日總場數")

    created_at = Column(DateTime, default=datetime.utcnow)

    races = relationship("Race", back_populates="meeting", order_by="Race.race_number")

    __table_args__ = (
        UniqueConstraint("meeting_date", "venue", name="uq_meeting_date_venue"),
    )

    def __repr__(self):
        return f"<RaceMeeting {self.meeting_date} {self.venue}>"


class Race(Base):
    """單場賽事"""
    __tablename__ = "races"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("race_meetings.id"), nullable=False)
    race_number = Column(Integer, nullable=False, comment="場次 1-11")

    # 賽事屬性
    race_class = Column(String(20), comment="班次：Class1-5, Griffin, G1-G3")
    distance = Column(Integer, comment="路程（米）")
    race_name_en = Column(String(200))
    race_name_ch = Column(String(200))
    race_time = Column(Time, comment="開跑時間")
    prize_money = Column(BigInteger, comment="總獎金（HKD）")

    # 賽道配置
    course = Column(String(5), comment="本場跑道")
    going = Column(String(30), comment="本場場地狀況")

    # 步速分析（賽後更新）
    pace_scenario = Column(String(20), comment="步速類型：Slow/Moderate/Fast")
    pace_speed_figure = Column(Float, comment="步速指標")

    # 賽後資訊
    is_completed = Column(Boolean, default=False)
    winning_time = Column(Float, comment="頭馬時間（秒）")
    winning_margin = Column(Float, comment="勝出距離（馬位）")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meeting = relationship("RaceMeeting", back_populates="races")
    runners = relationship("Runner", back_populates="race", order_by="Runner.barrier")
    sectional_times = relationship("SectionalTime", back_populates="race")
    odds_snapshots = relationship("OddsSnapshot", back_populates="race")

    __table_args__ = (
        UniqueConstraint("meeting_id", "race_number", name="uq_meeting_race"),
        Index("ix_race_date", "meeting_id"),
    )

    def __repr__(self):
        return f"<Race #{self.race_number} dist={self.distance}m>"


class Runner(Base):
    """出賽馬匹（含排位、負磅、臨場數據）—— 每場每馬一條"""
    __tablename__ = "runners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id = Column(Integer, ForeignKey("horses.id"), nullable=False)
    jockey_id = Column(Integer, ForeignKey("jockeys.id"), nullable=True)
    trainer_id = Column(Integer, ForeignKey("trainers.id"), nullable=True)

    # 排位與負磅
    runner_number = Column(Integer, comment="馬號（出賽編號）")
    barrier = Column(Integer, comment="檔位（閘箱號）")
    declared_weight = Column(Float, comment="宣佈負磅（磅）")
    handicap_weight = Column(Float, comment="讓磅")
    weight_carried = Column(Float, comment="實際負磅（含騎師減磅）")
    gear = Column(String(50), comment="出賽裝備，如 B/TT/CP")

    # 臨場數據
    declared_weight_lbs = Column(Float, comment="宣佈到埗體重")
    weight_change = Column(Float, comment="體重變幅")
    pre_race_condition = Column(String(200), comment="閘前狀態描述（汗濕/焦躁等）")

    # 跑法分類
    running_style = Column(String(20), comment="跑法：Front/Presser/Stalker/Closer")

    # 賽後數據
    finishing_position = Column(Integer, comment="名次")
    finishing_time = Column(Float, comment="完成時間（秒）")
    margin = Column(Float, comment="與頭馬距離（馬位）")
    odds_at_start = Column(Float, comment="起步賠率")

    # 模型計算結果
    true_probability = Column(Float, comment="模型計算真實勝率")
    market_probability = Column(Float, comment="市場隱含勝率")
    expected_value = Column(Float, comment="期望值 EV")
    is_value_bet = Column(Boolean, default=False, comment="是否 +EV")
    kelly_fraction = Column(Float, comment="凱利公式建議投注比例")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    race = relationship("Race", back_populates="runners")
    horse = relationship("Horse", back_populates="runners")
    jockey = relationship("Jockey", back_populates="runners")
    trainer = relationship("Trainer")

    __table_args__ = (
        UniqueConstraint("race_id", "horse_id", name="uq_race_horse"),
        Index("ix_runner_race", "race_id"),
        Index("ix_runner_horse", "horse_id"),
    )

    def __repr__(self):
        return f"<Runner horse={self.horse_id} race={self.race_id} barrier={self.barrier}>"


# ─────────────────────────────────────────────
# 3. 性能數據：分段時間 / 賠率快照
# ─────────────────────────────────────────────

class SectionalTime(Base):
    """分段時間（每段路程的時間）"""
    __tablename__ = "sectional_times"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    runner_id = Column(Integer, ForeignKey("runners.id"), nullable=False)
    section_number = Column(Integer, comment="段數：1=首段, 2=中段, 3=末段")
    section_distance = Column(Integer, comment="段距離（米）")
    section_time = Column(Float, comment="段時間（秒）")
    section_speed_figure = Column(Float, comment="段速指標（標準化）")
    position_at_section = Column(Integer, comment="過段時名次")

    race = relationship("Race", back_populates="sectional_times")
    runner = relationship("Runner")

    __table_args__ = (
        UniqueConstraint("runner_id", "section_number", name="uq_runner_section"),
        Index("ix_sectional_runner", "runner_id"),
    )


class OddsSnapshot(Base):
    """即時賠率快照（每 N 秒一條）"""
    __tablename__ = "odds_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    runner_id = Column(Integer, ForeignKey("runners.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, comment="快照時間")

    # 獨贏彩池
    win_odds = Column(Float, comment="獨贏賠率")
    win_pool = Column(BigInteger, comment="獨贏彩池金額")
    place_odds = Column(Float, comment="位置賠率")
    place_pool = Column(BigInteger, comment="位置彩池金額")

    # 變動偵測
    odds_delta = Column(Float, comment="與上次快照的賠率變動")
    is_smart_money = Column(Boolean, default=False, comment="是否觸發聰明錢警報")

    race = relationship("Race", back_populates="odds_snapshots")
    runner = relationship("Runner")

    __table_args__ = (
        Index("ix_odds_race_time", "race_id", "timestamp"),
        Index("ix_odds_runner_time", "runner_id", "timestamp"),
    )


# ─────────────────────────────────────────────
# 4. 量化模型輸出：訊號 / 權重配置
# ─────────────────────────────────────────────

class ValueBetSignal(Base):
    """+EV 價值投注訊號記錄"""
    __tablename__ = "value_bet_signals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    runner_id = Column(Integer, ForeignKey("runners.id"), nullable=False)
    signal_time = Column(DateTime, default=datetime.utcnow, comment="訊號觸發時間")

    # 核心指標
    true_probability = Column(Float, nullable=False, comment="模型真實勝率")
    market_probability = Column(Float, nullable=False, comment="市場隱含勝率")
    win_odds = Column(Float, comment="觸發時獨贏賠率")
    expected_value = Column(Float, nullable=False, comment="EV")
    kelly_fraction = Column(Float, comment="凱利比例")

    # 結果追蹤（賽後更新）
    did_win = Column(Boolean, comment="是否勝出")
    did_place = Column(Boolean, comment="是否入位")
    profit_loss = Column(Float, comment="盈虧（基於 1 注）")

    race = relationship("Race")
    runner = relationship("Runner")

    __table_args__ = (
        Index("ix_signal_race", "race_id"),
        Index("ix_signal_time", "signal_time"),
    )


class FeatureWeightProfile(Base):
    """使用者自訂特徵權重配置（用於面板 B 模型計算機）"""
    __tablename__ = "feature_weight_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_name = Column(String(100), nullable=False, comment="配置名稱，如 '雨天策略'")
    is_default = Column(Boolean, default=False)

    # ── 核心特徵權重（預設 1.0，使用者可調 0.0-3.0）──
    w_barrier = Column(Float, default=1.0, comment="檔位優勢權重")
    w_jockey = Column(Float, default=1.0, comment="騎師能力權重")
    w_trainer = Column(Float, default=1.0, comment="練馬師能力權重")
    w_jt_combo = Column(Float, default=1.0, comment="騎練組合權重")
    w_recent_form = Column(Float, default=1.0, comment="近績權重")
    w_class_drop = Column(Float, default=1.0, comment="降班權重")
    w_class_rise = Column(Float, default=1.0, comment="升班懲罰權重")
    w_distance_suitability = Column(Float, default=1.0, comment="路程適性權重")
    w_going_preference = Column(Float, default=1.0, comment="場地偏好權重")
    w_weight_change = Column(Float, default=1.0, comment="體重變幅權重")
    w_speed_figure = Column(Float, default=1.0, comment="速度指標權重")
    w_pace_scenario = Column(Float, default=1.0, comment="步速預測權重")
    w_smart_money = Column(Float, default=1.5, comment="聰明錢權重（預設加成）")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FeatureWeightProfile {self.profile_name}>"
