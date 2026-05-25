"""
Pre-race Analysis API — 賽前排位分析。

當賽事已排位但賠率尚未公佈時使用：
- 只計算 P_true (模型勝率)，不計算 P_market/EV/Kelly
- 勝率排名
- 步速預測
- 隱藏信號偵測
- 不依賴數據庫，全部實時計算
"""
import time
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.data_provider import get_provider
from app.services.quant_engine import QuantAnalysisOrchestrator
from app.services.signal_detector import HiddenSignalDetector

router = APIRouter(prefix="/api/pre", tags=["pre-race"])

# ── Type-safe getter for HKJC string fields ──
def _int(val, default=0) -> int:
    if val is None or val == '':
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _float(val, default=0.0) -> float:
    if val is None or val == '':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════
#  Request / Response Models
# ═══════════════════════════════════════════════

class PreRaceRunnerOut(BaseModel):
    horse_no: int
    horse_name: str
    horse_name_ch: str
    barrier: int
    weight: int
    jockey: str
    jockey_ch: str
    trainer: str
    trainer_ch: str
    win_prob: float  # P_true in %
    win_prob_rank: int  # 1 = highest probability
    pace_style: str  # front / mid / closer
    rating: float
    last6run: str
    strong_contender: bool
    barrier_versatile: bool
    superhorse: bool


class PreRacePaceOut(BaseModel):
    pace_type: str  # slow / moderate / fast
    front_runners: List[int]
    mid_field: List[int]
    closers: List[int]
    description: str
    front_count: int
    impact: str  # "後上馬有利" / "前領馬有利" / "正常發揮"


class PreRaceSignalOut(BaseModel):
    horse_no: int
    horse_name: str
    signal_type: str
    severity: str
    category: str
    title_en: str
    title_ch: str
    description: str
    confidence: float


class PreRaceAnalysisOut(BaseModel):
    meeting_id: str
    venue_code: str
    date: str
    race_no: int
    race_name_en: str
    race_name_ch: str
    distance: int
    going: str
    race_class: str
    total_runners: int
    status: str  # "odds_not_available" or "odds_partial"
    runners: List[PreRaceRunnerOut]
    pace_forecast: PreRacePaceOut
    hidden_signals: List[PreRaceSignalOut]
    timestamp: float


# ═══════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════

@router.get("/analyze", response_model=PreRaceAnalysisOut)
async def pre_race_analyze(
    race_no: int = Query(1),
    date: Optional[str] = Query(None),
    venue_code: Optional[str] = Query(None),
):
    """
    賽前排位分析：僅基於馬匹屬性、檔位、負磅、近績等計算勝率。
    
    適用場景：賽事已排位但賠率尚未公佈。
    不計算 +EV / Kelly / P_market (需要賠率)。
    """
    provider = get_provider()

    # 1. 獲取賽事數據
    meetings = provider.get_race_meetings(race_date=date, venue_code=venue_code)
    if not meetings:
        raise HTTPException(502, "No race meetings found")

    meeting = meetings[0]
    race = None
    for r in meeting.get("races", []):
        if _int(r.get("no")) == race_no:
            race = r
            break

    if not race:
        raise HTTPException(404, f"Race {race_no} not found in meeting {meeting.get('id')}")

    runners_raw = race.get("runners", [])

    # Check if odds are available (determine status)
    # Check if ANY runner has winOdds
    has_any_odds = any(_float(r.get("winOdds"), 0) > 0 for r in runners_raw)
    
    # Also check odds pools
    status = "odds_not_available"
    try:
        odds_pools = provider.get_race_odds(
            race_no=race_no,
            odds_types=["WIN"],
            race_date=date or meeting.get("date"),
            venue_code=venue_code or meeting.get("venueCode"),
        ) or []
        win_pool = next((p for p in odds_pools if p.get("oddsType") == "WIN"), None)
        if win_pool and len(win_pool.get("oddsNodes", [])) > 0:
            status = "odds_partial"
    except:
        pass

    # ── 掃描當日已完賽場次，建立騎師當日成績 ──
    jockey_today_stats: Dict[str, Dict] = {}
    for r in meeting.get("races", []):
        rn = _int(r.get("no"))
        if rn >= race_no:
            continue
        for runner in r.get("runners", []):
            final_pos = _int(runner.get("finalPosition"), 0)
            jockey = runner.get("jockey", {})
            jcode = jockey.get("code", "")
            if not jcode:
                continue
            if jcode not in jockey_today_stats:
                jockey_today_stats[jcode] = {"wins": 0, "places": 0, "rides": 0, "jockey_name": jockey.get("name_en", "")}
            jockey_today_stats[jcode]["rides"] += 1
            if final_pos == 1:
                jockey_today_stats[jcode]["wins"] += 1
                jockey_today_stats[jcode]["places"] += 1
            elif 2 <= final_pos <= 3:
                jockey_today_stats[jcode]["places"] += 1

    # ── Pace classification ──
    front_candidates = []
    pace_setters = []
    stalkers = []
    closers = []
    for r in runners_raw:
        no = _int(r.get("no"))
        if no == 0:
            continue
        barrier = _int(r.get("barrierDrawNumber"), 14)
        weight = _int(r.get("handicapWeight"), 126)
        form = r.get("last6run") or ""
        
        # 前領候選：內檔(barrier≤3) + 輕磅(<125)
        if barrier <= 3 and weight < 125:
            pace_setters.append(no)
        elif barrier <= 5 or 125 <= weight < 132:
            stalkers.append(no)
        else:
            closers.append(no)
        
        if barrier <= 4:
            front_candidates.append(no)

    n_front = len(pace_setters)
    if n_front >= 3:
        pace_type = "fast"
        impact = "後上馬有利"
        desc = f"快步速 — {n_front}匹前領候選互搶，消耗大，後追馬有優勢"
    elif n_front <= 1:
        pace_type = "slow"
        impact = "前領馬有利"
        desc = f"慢步速 — 僅{n_front}匹前領候選，領放馬省力，後追難追"
    else:
        pace_type = "moderate"
        impact = "正常發揮"
        desc = f"正常步速 — {n_front}匹前領候選"

    # ── 隱藏信號偵測 ──
    race_course = race.get("raceCourse") or {}
    signal_detector = HiddenSignalDetector()
    race_context = {
        "venue_code": meeting.get("venueCode", ""),
        "distance": race.get("distance", 0),
        "race_class": race.get("raceClass_en", ""),
        "going": race.get("go_en", ""),
        "race_course": race_course,
        "race_no": race_no,
    }
    # Pass empty odds data for pre-race
    detected_signals = signal_detector.detect(runners_raw, race_context, {}, jockey_today_stats)

    # ── 量化引擎計算 P_true ──
    orchestrator = QuantAnalysisOrchestrator()
    p_true_arr, scores = orchestrator.calculate_p_true(runners_raw, race_context)

    # 建立勝率排名
    ranked_indices = sorted(range(len(p_true_arr)), key=lambda i: p_true_arr[i], reverse=True)
    rank_map = {idx: rank + 1 for rank, idx in enumerate(ranked_indices)}

    # Build runner analyses
    runner_analyses = []
    for i, r in enumerate(runners_raw):
        no = _int(r.get("no"))
        jockey = r.get("jockey", {})
        trainer = r.get("trainer", {})
        barrier = _int(r.get("barrierDrawNumber"), 0)
        weight = _int(r.get("handicapWeight"), 0)
        form = r.get("last6run") or ""
        
        # 穩膽判定：勝率前 30%
        rank = rank_map.get(i, 99)
        strong_contender = rank <= max(3, int(len(runners_raw) * 0.3))
        
        # 檔位無影響：近績多次前四
        barrier_versatile = False
        positions = [int(p) for p in form.split('/') if p.strip().isdigit()]
        if positions:
            top4_count = sum(1 for p in positions if p <= 4)
            if len(positions) >= 5 and top4_count >= 4:
                barrier_versatile = True
        
        # 超級馬王：近績極度出色
        superhorse = False
        if positions:
            win_count = sum(1 for p in positions if p == 1)
            if len(positions) >= 5 and win_count >= 5:
                superhorse = True
            if len(positions) >= 4 and all(p == 1 for p in positions[:4]):
                superhorse = True

        pace_style = "front" if no in set(pace_setters + stalkers) else "closer"

        runner_analyses.append(PreRaceRunnerOut(
            horse_no=no,
            horse_name=r.get("name_en", ""),
            horse_name_ch=r.get("name_ch", ""),
            barrier=barrier,
            weight=weight,
            jockey=jockey.get("name_en", ""),
            jockey_ch=jockey.get("name_ch", ""),
            trainer=trainer.get("name_en", ""),
            trainer_ch=trainer.get("name_ch", ""),
            win_prob=round(p_true_arr[i] * 100, 2),
            win_prob_rank=rank,
            pace_style=pace_style,
            rating=round(scores[i], 1),
            last6run=form,
            strong_contender=strong_contender,
            barrier_versatile=barrier_versatile,
            superhorse=superhorse,
        ))

    # Sort by win prob rank for output
    runner_analyses.sort(key=lambda x: x.win_prob_rank)

    return PreRaceAnalysisOut(
        meeting_id=meeting.get("id", ""),
        venue_code=meeting.get("venueCode", ""),
        date=meeting.get("date", ""),
        race_no=race_no,
        race_name_en=race.get("raceName_en", ""),
        race_name_ch=race.get("raceName_ch", ""),
        distance=race.get("distance", 0),
        going=race.get("go_en", ""),
        race_class=race.get("raceClass_en", ""),
        total_runners=len(runners_raw),
        status=status,
        runners=runner_analyses,
        pace_forecast=PreRacePaceOut(
            pace_type=pace_type,
            front_runners=pace_setters + stalkers[:2],
            mid_field=stalkers[2:] if len(stalkers) > 2 else [],
            closers=closers,
            description=desc,
            front_count=len(pace_setters),
            impact=impact,
        ),
        hidden_signals=[
            PreRaceSignalOut(
                horse_no=s.horse_no,
                horse_name=s.horse_name,
                signal_type=s.signal_type,
                severity=s.severity,
                category=s.category,
                title_en=s.title_en,
                title_ch=s.title_ch,
                description=s.description,
                confidence=s.confidence,
            )
            for s in detected_signals
        ],
        timestamp=time.time(),
    )


@router.get("/meetings")
async def pre_race_meetings(
    date: Optional[str] = Query(None),
    venue_code: Optional[str] = Query(None),
):
    """獲取賽事列表（與 live/meetings 相同，這裡只是為了統一路徑）"""
    provider = get_provider()
    meetings = provider.get_race_meetings(race_date=date, venue_code=venue_code)
    return meetings or []
