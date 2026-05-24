"""
API Routes: Race & Analysis endpoints.
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.models import RaceMeeting, Race, Runner, Horse, Jockey, Trainer, ValueBetSignal
from app.services.quant_engine import (
    QuantAnalysisOrchestrator, RunnerFeatures, FeatureWeights
)
from app.services.schemas import (
    RaceMeetingResponse, RaceDetailResponse, RunnerInRace,
    QuantAnalysisRequest, RaceAnalysisResponse, ValueBetSignalResponse,
    SmartMoneyAlertResponse, CSVImportResult,
)

router = APIRouter(prefix="/api/v1", tags=["racing"])


# ═══════════════════════════════════════════════
#  賽事查詢 API
# ═══════════════════════════════════════════════

@router.get("/meetings", response_model=List[RaceMeetingResponse])
async def list_meetings(
    start_date: Optional[str] = Query(None, description="開始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="結束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """查詢賽事日列表"""
    stmt = select(RaceMeeting).order_by(RaceMeeting.meeting_date.desc())
    if start_date and end_date:
        stmt = stmt.where(
            RaceMeeting.meeting_date.between(start_date, end_date)
        )
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.get("/meetings/{meeting_id}/races", response_model=List[RaceDetailResponse])
async def list_races_in_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
):
    """查詢某賽事日的所有場次"""
    stmt = (
        select(Race)
        .where(Race.meeting_id == meeting_id)
        .order_by(Race.race_number)
    )
    result = await db.execute(stmt)
    races = result.scalars().all()

    response = []
    for race in races:
        # 載入 runners
        r_stmt = (
            select(Runner, Horse.name_en, Horse.name_ch, Jockey.name_en, Trainer.name_en)
            .join(Horse, Runner.horse_id == Horse.id)
            .outerjoin(Jockey, Runner.jockey_id == Jockey.id)
            .outerjoin(Trainer, Runner.trainer_id == Trainer.id)
            .where(Runner.race_id == race.id)
            .order_by(Runner.barrier)
        )
        r_result = await db.execute(r_stmt)
        rows = r_result.all()

        runners = []
        for runner, h_name_en, h_name_ch, j_name, t_name in rows:
            runners.append(RunnerInRace(
                runner_id=runner.id,
                runner_number=runner.runner_number,
                horse_name_en=h_name_en,
                horse_name_ch=h_name_ch,
                barrier=runner.barrier,
                declared_weight=runner.declared_weight,
                jockey_name=j_name,
                trainer_name=t_name,
                win_odds=runner.odds_at_start,
                true_probability=runner.true_probability,
                market_probability=runner.market_probability,
                expected_value=runner.expected_value,
                is_value_bet=runner.is_value_bet or False,
                kelly_fraction=runner.kelly_fraction,
            ))

        response.append(RaceDetailResponse(
            id=race.id,
            race_number=race.race_number,
            race_class=race.race_class,
            distance=race.distance,
            race_name_en=race.race_name_en,
            going=race.going,
            pace_scenario=race.pace_scenario,
            is_completed=race.is_completed or False,
            runners=runners,
        ))

    return response


@router.get("/races/{race_id}", response_model=RaceDetailResponse)
async def get_race_detail(race_id: int, db: AsyncSession = Depends(get_db)):
    """查詢單場賽事詳情（含所有出賽馬匹）"""
    race = await db.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")

    r_stmt = (
        select(Runner, Horse.name_en, Horse.name_ch, Jockey.name_en, Trainer.name_en)
        .join(Horse, Runner.horse_id == Horse.id)
        .outerjoin(Jockey, Runner.jockey_id == Jockey.id)
        .outerjoin(Trainer, Runner.trainer_id == Trainer.id)
        .where(Runner.race_id == race_id)
        .order_by(Runner.barrier)
    )
    r_result = await db.execute(r_stmt)
    rows = r_result.all()

    runners = []
    for runner, h_name_en, h_name_ch, j_name, t_name in rows:
        runners.append(RunnerInRace(
            runner_id=runner.id,
            runner_number=runner.runner_number,
            horse_name_en=h_name_en,
            horse_name_ch=h_name_ch,
            barrier=runner.barrier,
            declared_weight=runner.declared_weight,
            jockey_name=j_name,
            trainer_name=t_name,
            win_odds=runner.odds_at_start,
            true_probability=runner.true_probability,
            market_probability=runner.market_probability,
            expected_value=runner.expected_value,
            is_value_bet=runner.is_value_bet or False,
            kelly_fraction=runner.kelly_fraction,
        ))

    return RaceDetailResponse(
        id=race.id,
        race_number=race.race_number,
        race_class=race.race_class,
        distance=race.distance,
        race_name_en=race.race_name_en,
        going=race.going,
        pace_scenario=race.pace_scenario,
        is_completed=race.is_completed or False,
        runners=runners,
    )


# ═══════════════════════════════════════════════
#  量化分析 API
# ═══════════════════════════════════════════════

@router.post("/analyze/{race_id}", response_model=RaceAnalysisResponse)
async def analyze_race(
    race_id: int,
    request: QuantAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    對指定場次執行完整量化分析。

    流程：
    1. 從 DB 載入賽事 & 出賽馬數據
    2. 構建 RunnerFeatures
    3. 執行 QuantAnalysisOrchestrator
    4. 將結果寫回 DB
    5. 返回分析結果
    """
    # 載入賽事
    race = await db.get(Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")

    # 載入 meeting（取 venue）
    meeting = await db.get(RaceMeeting, race.meeting_id)

    # 載入出賽馬匹（含關聯數據）
    stmt = (
        select(Runner, Horse, Jockey, Trainer)
        .join(Horse, Runner.horse_id == Horse.id)
        .outerjoin(Jockey, Runner.jockey_id == Jockey.id)
        .outerjoin(Trainer, Runner.trainer_id == Trainer.id)
        .where(Runner.race_id == race_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail="No runners found for this race")

    # 構建特徵向量
    feature_weights = FeatureWeights()
    if request.feature_weights:
        for k, v in request.feature_weights.items():
            if hasattr(feature_weights, k):
                setattr(feature_weights, k, v)

    runners_features = []
    win_odds_list = []
    runner_ids = []

    for runner, horse, jockey, trainer in rows:
        # 簡化版特徵構建（完整版需從歷史數據聚合）
        rf = RunnerFeatures(
            runner_id=runner.id,
            horse_id=horse.id,
            barrier=runner.barrier or 0,
            declared_weight=runner.declared_weight or 0,
            weight_change=runner.weight_change or 0,
            horse_age=horse.age or 5,
            horse_rating=horse.rating or 0,
            recent_positions=[],  # TODO: 從 RaceResult 聚合
            win_strike_rate=horse.win_strike_rate or 0,
            place_strike_rate=horse.place_strike_rate or 0,
            jockey_win_rate=jockey.win_strike_rate if jockey else 0,
            trainer_win_rate=trainer.win_strike_rate if trainer else 0,
            jockey_trainer_combo_rate=0,  # TODO: 從 JockeyTrainerCombo 查詢
            jockey_horse_win_rate=0,  # TODO: 需額外查詢
            distance_suitability=0.5,  # 預設中等
            going_preference=0.5,
            venue_win_rate=horse.win_strike_rate or 0,
            course_config_advantage=0,
            running_style=runner.running_style or "Presser",
            pace_advantage_score=0,
            speed_figure_last=0,
            speed_figure_avg3=0,
            sectional_time_best=0,
            class_drop=runner.finishing_position is None and horse.rating and race.race_class and "Class" in race.race_class,
            class_rise=False,
            days_since_last_run=0,
        )
        runners_features.append(rf)
        win_odds_list.append(runner.odds_at_start or 10.0)
        runner_ids.append(runner.id)

    # 執行量化分析
    orchestrator = QuantAnalysisOrchestrator(weights=feature_weights)
    results = orchestrator.analyze_race(
        runners=runners_features,
        win_odds=win_odds_list,
        runner_ids=runner_ids,
    )

    # 將結果寫回 DB
    for r in results:
        runner = next((row[0] for row in rows if row[0].id == r.runner_id), None)
        if runner:
            runner.true_probability = r.true_probability
            runner.market_probability = r.market_probability
            runner.expected_value = r.expected_value
            runner.is_value_bet = r.is_value_bet
            runner.kelly_fraction = r.kelly_fraction

    await db.commit()

    # 構建回應
    pace_result = orchestrator.pace_forecaster.forecast_pace(runners_features)

    # 載入馬名
    horse_names = {}
    for runner, horse, jockey, trainer in rows:
        horse_names[runner.id] = horse.name_en

    value_bets = [
        ValueBetSignalResponse(
            runner_id=r.runner_id,
            runner_number=next((row[0].runner_number for row in rows if row[0].id == r.runner_id), 0),
            horse_name=horse_names.get(r.runner_id, "Unknown"),
            true_probability=r.true_probability,
            market_probability=r.market_probability,
            win_odds=r.win_odds,
            expected_value=r.expected_value,
            is_value_bet=r.is_value_bet,
            kelly_fraction=r.kelly_fraction,
            edge_percentage=r.edge_percentage,
            confidence_level=r.confidence_level,
        )
        for r in results if r.is_value_bet
    ]

    all_runners = [
        ValueBetSignalResponse(
            runner_id=r.runner_id,
            runner_number=next((row[0].runner_number for row in rows if row[0].id == r.runner_id), 0),
            horse_name=horse_names.get(r.runner_id, "Unknown"),
            true_probability=r.true_probability,
            market_probability=r.market_probability,
            win_odds=r.win_odds,
            expected_value=r.expected_value,
            is_value_bet=r.is_value_bet,
            kelly_fraction=r.kelly_fraction,
            edge_percentage=r.edge_percentage,
            confidence_level=r.confidence_level,
        )
        for r in results
    ]

    return RaceAnalysisResponse(
        race_id=race_id,
        race_number=race.race_number,
        distance=race.distance or 0,
        venue=meeting.venue if meeting else "STV",
        going=race.going,
        pace_scenario=pace_result["pace_scenario"],
        pace_detail=pace_result,
        value_bets=value_bets,
        all_runners=all_runners,
    )


# ═══════════════════════════════════════════════
#  +EV 訊號歷史
# ═══════════════════════════════════════════════

@router.get("/signals", response_model=List[ValueBetSignalResponse])
async def list_value_bet_signals(
    race_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查詢歷史 +EV 訊號"""
    stmt = select(ValueBetSignal).order_by(ValueBetSignal.signal_time.desc())
    if race_id:
        stmt = stmt.where(ValueBetSignal.race_id == race_id)
    result = await db.execute(stmt.limit(limit))
    return result.scalars().all()
