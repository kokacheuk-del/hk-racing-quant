"""
Live Data API — HKJC GraphQL Proxy + 即時量化分析。

不依賴數據庫，直接從 HKJC GraphQL API 獲取數據並返回給前端。
後端負責：
1. 代理 HKJC GraphQL 請求（解決 CORS）
2. 即時量化分析（P_true / P_market / +EV）
3. 賠率快照緩存（Redis / 內存 fallback）
"""
import time
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.data_provider import get_provider
from app.services.quant_engine import (
    QuantAnalysisOrchestrator, RunnerFeatures, FeatureWeights,
)
from app.services.signal_detector import HiddenSignalDetector
from app.services.quant_engine import JockeyTrainerComboScorer

router = APIRouter(prefix="/api/live", tags=["live"])

# ── Type-safe getter for HKJC string fields ──
def _int(val, default=0) -> int:
    """Safely convert HKJC GraphQL string fields to int."""
    if val is None or val == '':
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _float(val, default=0.0) -> float:
    """Safely convert HKJC GraphQL string fields to float."""
    if val is None or val == '':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# ── Data source (abstracted via DataProvider) ──
# 切換數據源只需改環境變數 DATA_PROVIDER，路由層無需改動


# ═══════════════════════════════════════════════
#  Request / Response Models
# ═══════════════════════════════════════════════

class WeightOverrides(BaseModel):
    barrier_advantage: Optional[float] = None
    jockey_win_rate: Optional[float] = None
    trainer_win_rate: Optional[float] = None
    horse_form: Optional[float] = None
    weight_factor: Optional[float] = None
    pace_suitability: Optional[float] = None
    wet_track: Optional[float] = None
    distance_suitability: Optional[float] = None


class RunnerAnalysisOut(BaseModel):
    horse_no: int
    horse_name: str
    horse_name_ch: str
    barrier: int
    weight: int
    jockey: str
    jockey_ch: str
    trainer: str
    trainer_ch: str
    win_odds: float
    p_true: float
    p_market: float
    ev: float
    edge: float
    kelly_fraction: float
    is_value_bet: bool
    ev_confidence: str  # "high" / "medium" / "low" — 冷門馬 EV 信任度
    strong_contender: bool  # 穩膽：勝率高但 EV 可能為負（賠率太低）
    barrier_versatile: bool  # 檔位無影響：近績多次前四，證明不同檔位都能跑
    superhorse: bool  # 超級馬王：近績極度出色（近6跑≥5冠），市場亦認同（賠率極低）
    pace_style: str
    rating: float
    last6run: str
    hot_favourite: bool
    odds_drop: float


class PaceForecastOut(BaseModel):
    pace_type: str
    front_runners: List[int]
    mid_field: List[int]
    closers: List[int]
    description: str


class SmartMoneyAlertOut(BaseModel):
    horse_no: int
    horse_name: str
    alert_type: str
    severity: str
    description: str
    odds_drop_value: Optional[float] = None
    current_odds: Optional[float] = None


class HiddenSignalOut(BaseModel):
    horse_no: int
    horse_name: str
    signal_type: str
    severity: str
    category: str
    title_en: str
    title_ch: str
    description: str
    confidence: float
    edge_boost: float


class RaceAnalysisOut(BaseModel):
    meeting_id: str
    venue_code: str
    date: str
    race_no: int
    horse_no: int
    horse_name: str
    jockey: str
    trainer: str
    race_name_en: str
    race_name_ch: str
    distance: int
    going: str
    race_class: str
    total_runners: int
    runners: List[RunnerAnalysisOut]
    pace_forecast: PaceForecastOut
    smart_money_alerts: List[SmartMoneyAlertOut]
    hidden_signals: List[HiddenSignalOut] = []
    value_bet_count: int
    timestamp: float
    jockey_trainer_combo: Optional[dict] = None


class MeetingOut(BaseModel):
    id: str
    venue_code: str
    date: str
    status: str
    total_races: int
    races: List[Dict]


# ═══════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════

@router.get("/meetings", response_model=List[MeetingOut])
async def live_meetings(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    venue_code: Optional[str] = Query(None),
):
    """獲取賽事日列表（從 HKJC GraphQL 代理）"""
    provider = get_provider()
    meetings = provider.get_race_meetings(race_date=date, venue_code=venue_code)
    if meetings is None:
        raise HTTPException(502, "Failed to fetch from HKJC GraphQL API")

    result = []
    for m in meetings:
        result.append(MeetingOut(
            id=m.get("id", ""),
            venue_code=m.get("venueCode", ""),
            date=m.get("date", ""),
            status=m.get("status", ""),
            total_races=len(m.get("races", [])),
            races=m.get("races", []),
        ))
    return result


@router.get("/odds")
async def live_odds(
    race_no: int = Query(1),
    odds_types: str = Query("WIN,PLA", description="逗號分隔的賠率類型"),
    date: Optional[str] = Query(None),
    venue_code: Optional[str] = Query(None),
):
    """獲取即時賠率（從 HKJC GraphQL 代理）"""
    provider = get_provider()
    types_list = [t.strip() for t in odds_types.split(",")]
    pools = provider.get_race_odds(
        race_no=race_no,
        odds_types=types_list,
    )
    if pools is None:
        raise HTTPException(502, "Failed to fetch odds from HKJC")

    return {"pools": pools, "timestamp": time.time()}


@router.get("/pools")
async def live_pools(
    race_no: int = Query(1),
    odds_types: str = Query("WIN,PLA"),
    date: Optional[str] = Query(None),
    venue_code: Optional[str] = Query(None),
):
    """獲取彩池投注額"""
    provider = get_provider()
    types_list = [t.strip() for t in odds_types.split(",")]
    pools = provider.get_race_pools(
        race_no=race_no,
        odds_types=types_list,
        race_date=date,
        venue_code=venue_code,
    )
    if pools is None:
        raise HTTPException(502, "Failed to fetch pool data from HKJC")

    return {"pools": pools, "timestamp": time.time()}


@router.get("/analyze", response_model=RaceAnalysisOut)
async def live_analyze(
    race_no: int = Query(1),
    date: Optional[str] = Query(None),
    venue_code: Optional[str] = Query(None),
):
    """
    即時量化分析：獲取排位表 + 賠率 → 計算 P_true / P_market / +EV。

    不依賴數據庫，全部實時計算。
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

        # ═══ 加入騎練組合評分 ═══
    combo_scorer = JockeyTrainerComboScorer(db_session=None)
    
    # 給每匹馬加上組合評分信息
    for runner in runners_raw:
        jockey_name = runner.get("jockey", {}).get("name_ch", "")
        trainer_name = runner.get("trainer", {}).get("name_ch", "")
        
        if jockey_name and trainer_name:
            combo_info = combo_scorer.get_combo_score(jockey_name, trainer_name)
            runner["jockey_trainer_combo"] = combo_info

    # ── 掃描當日已完賽場次，建立騎師當日成績 ──
    jockey_today_stats: Dict[str, Dict] = {}  # {jockey_code: {wins, places, rides}}
    for r in meeting.get("races", []):
        rn = _int(r.get("no"))
        # 只看比當前場次更早的已完賽場次
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
                jockey_today_stats[jcode]["places"] += 1  # 冠軍也計入位
            elif 2 <= final_pos <= 3:
                jockey_today_stats[jcode]["places"] += 1

    # 2. 獲取賠率
    odds_pools = provider.get_race_odds(
        race_no=race_no,
        odds_types=["WIN", "PLA", "QIN"],
    ) or []

    # Build odds maps
    win_odds_map: Dict[int, float] = {}
    hot_fav_map: Dict[int, bool] = {}
    odds_drop_map: Dict[int, float] = {}

    for pool in odds_pools:
        if pool.get("oddsType") == "WIN":
            for node in pool.get("oddsNodes", []):
                try:
                    no = int(node.get("combString", "0") or "0")
                    val = node.get("oddsValue")
                    win_odds_map[no] = float(val) if val else 0
                    hot_fav_map[no] = bool(node.get("hotFavourite"))
                    drop_str = node.get("oddsDropValue")
                    drop = float(drop_str) if drop_str else 0
                    if drop > 0:
                        odds_drop_map[no] = drop
                except (ValueError, TypeError):
                    continue

    # 3. 計算量化分析
    TAKEOUT = 0.175
    MIN_PROB = 0.005
    EV_THRESH = 0.01      # EV > 1% (只要有正期望值)
    EDGE_THRESH = 0.001   # Edge > 0.1% (P_true 比 P_market 高)
    P_TRUE_THRESH = 0.04  # P_true > 4%
    KELLY_FRAC = 1 / 3

    # ── Build raw scores ──
    # 用對數概率模型而非簡單加權，避免 Softmax 崩塌
    scores = []
    for r in runners_raw:
        s = 0  # log-odds style (centered around 0)
        barrier = _int(r.get("barrierDrawNumber"), 10)
        weight = _int(r.get("handicapWeight"), 115)
        last6 = r.get("last6run") or ""
        jockey = r.get("jockey", {})
        trainer = r.get("trainer", {})
        jockey_code = jockey.get("code", "")

        # Barrier: 1-3 有小加成，>12 有小懲罰
        if barrier <= 3:
            s += 0.3
        elif barrier <= 6:
            s += 0.1
        elif barrier >= 12:
            s -= 0.2

        # Weight: 高磅有利（評分高的馬）
        if weight >= 133:
            s += 0.4
        elif weight >= 128:
            s += 0.2
        elif weight <= 118:
            s -= 0.2

        # Form: 近績
        positions = [int(p) for p in last6.split('/') if p.strip().isdigit()]
        if positions:
            avg_pos = sum(positions) / len(positions)
            if avg_pos <= 2.5:
                s += 0.6
            elif avg_pos <= 4:
                s += 0.3
            elif avg_pos <= 6:
                s += 0.0
            else:
                s -= 0.3
            # 近2跑特別好
            recent2 = positions[:2] if len(positions) >= 2 else positions
            if sum(recent2) / len(recent2) <= 2:
                s += 0.3

        # Jockey quality (data-driven, not fixed +5)
        top_jockey_wr = {
            "ZP": 0.22, "MCJ": 0.20, "BH": 0.18, "AA": 0.16,
            "YTE": 0.14, "LFR": 0.14, "JOM": 0.15, "TEK": 0.13,
            "CCY": 0.12, "OJM": 0.13, "CML": 0.10, "CJE": 0.11,
        }
        jwr = top_jockey_wr.get(jockey_code, 0.08)
        s += (jwr - 0.10) * 5  # 10% baseline, top jockeys get +0.6, weak ones -0.1

        # Trainer quality (heuristic by code)
        top_trainers = {"SCS": 0.18, "CAS": 0.17, "J Size": 0.16, "LKW": 0.15, "FDS": 0.15}
        trainer_name = trainer.get("name_en", "")
        twr = top_trainers.get(trainer.get("code", ""), 0.10)
        s += (twr - 0.10) * 3  # lighter weight than jockey

        # Trump Card / Priority
        if r.get("trumpCard") and r.get("priority"):
            s += 0.4
        elif r.get("trumpCard"):
            s += 0.2

        # Hot favourite from odds data
        no_int = _int(r.get("no"))
        if hot_fav_map.get(no_int, False):
            s += 0.3

        # Odds drop signal — if odds are crashing, the market knows something
        if no_int in odds_drop_map:
            drop = odds_drop_map[no_int]
            if drop >= 5:
                s += 0.5
            elif drop >= 2:
                s += 0.3
            elif drop >= 1:
                s += 0.15

        # 當日火紅騎師加成
        if jockey_code in jockey_today_stats:
            jstats = jockey_today_stats[jockey_code]
            if jstats["wins"] >= 2:
                s += 0.5
            elif jstats["wins"] >= 1:
                s += 0.2
            if jstats["places"] / max(jstats["rides"], 1) >= 0.5 and jstats["rides"] >= 2:
                s += 0.2

        scores.append(s)

    # ── Softmax with temperature scaling ──
    # 溫度系數 T 越大，分佈越平均；T=1 是標準 softmax
    # 用 T=3 使分佈更平滑，避免 99% 集中在一匹馬
    TEMPERATURE = 3.0
    max_score = max(scores) if scores else 0
    shifted = [(s - max_score) / TEMPERATURE for s in scores]
    exps = [__import__('math').exp(c) for c in shifted]
    total_exp = sum(exps)
    p_true_arr = [max(MIN_PROB, e / total_exp) for e in exps]

    # ── Blend P_true with P_market (市場知情權) ──
    # 核心思路：市場賠率是最強的單一預測信號
    # P_true 以 P_market 為錨點，模型只在有信號時做調整
    # 這是專業 handicapper 的做法：先信市場，再找市場偏誤
    P_MODEL_WEIGHT = 0.25   # 模型原始概率權重
    P_MARKET_WEIGHT = 0.75  # 市場概率權重

    # P_market from WIN odds
    # 用原始隱含概率 1/odds，不調整抽水也不歸一化
    # 原因：抽水是全局成本，不應攤到個別馬的概率上
    # 歸一化會壓縮熱門馬的概率，讓 EV 計算失真
    p_market_arr = []
    for r in runners_raw:
        no = _int(r.get("no"))
        odds = win_odds_map.get(no, _float(r.get("winOdds"), 100))
        raw_p = 1 / odds if odds > 0 else 0
        p_market_arr.append(raw_p)

    # ── Pace classification (v2: 基於真實前領候選) ──
    # 檔位 ≠ 跑法。關鍵是：有多少匹馬「有能力也有動機搶前」
    # 前領候選 = 內檔(barrier≤3) + 輕磅(<125) = 有速度搶前且體重允許
    # 如果多匹前領候選 → 必定搶位 → 快步速 → 領放馬消耗大 → 後上馬有利
    # 如果沒有或很少前領候選 → 容易領放 → 慢步速 → 前領馬省力 → 前領有利
    front_candidates = []   # 真正有能力搶前的馬
    pace_setters = []       # 前領型（輕磅+內檔，必定搶前）
    stalkers = []           # 跟放型（中檔，會跟在前領之後）
    closers = []            # 後上型（外檔或重磅，只能後追）
    for r in runners_raw:
        no = _int(r.get("no"))
        if no == 0:
            continue
        barrier = _int(r.get("barrierDrawNumber"), 10)
        weight = _int(r.get("handicapWeight"), 115)

        if barrier <= 3 and weight < 125:
            pace_setters.append(no)
            front_candidates.append(no)
        elif barrier <= 3 and weight < 130:
            # 內檔但稍重 — 可能搶前也可能跟放
            stalkers.append(no)
            front_candidates.append(no)
        elif barrier <= 6 and weight < 120:
            # 中檔輕磅 — 有可能搶前
            stalkers.append(no)
            front_candidates.append(no)
        elif barrier >= 10 and weight < 120:
            # 外檔輕磅 — 外閘快放
            stalkers.append(no)
        else:
            closers.append(no)

    # 步速判定：基於前領候選數量
    n_front = len(front_candidates)
    n_setters = len(pace_setters)
    if n_setters >= 3:
        # 3+ 匹必定搶前 → 激烈搶位 → 快步速
        pace_type = "fast"
    elif n_front >= 4:
        # 4+ 前領候選（含可能搶前的） → 大概率快步速
        pace_type = "fast"
    elif n_setters >= 2:
        # 2 匹搶前 → 可能快也可能正常
        pace_type = "moderate"
    elif n_front <= 1:
        # 0-1 前領候選 → 容易領放 → 慢步速
        pace_type = "slow"
    else:
        pace_type = "moderate"

    # 兼容舊接口
    front_runners = pace_setters + stalkers[:2]  # 前幾匹跟放也算
    mid_field = stalkers[2:] if len(stalkers) > 2 else []
    all_front = set(pace_setters + stalkers)
    closers_list = [no for no in [_int(r.get("no")) for r in runners_raw] if no not in all_front and no > 0]

    # ── 隱藏信號偵測（先跑，後面計算 P_true 要用） ──
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
    odds_data_for_signal = {
        "win_odds_map": win_odds_map,
        "hot_fav_map": hot_fav_map,
        "odds_drop_map": odds_drop_map,
    }
    detected_signals = signal_detector.detect(runners_raw, race_context, odds_data_for_signal, jockey_today_stats)

    # Build runner analyses
    runner_analyses = []
    alerts = []

    # Pre-compute blended P_true for all runners (need normalization)
    p_blend_arr = []
    for i, r in enumerate(runners_raw):
        p_model = p_true_arr[i]
        p_market = p_market_arr[i]

        # ── Step 1: Base blend (model + market) ──
        p_blend = P_MODEL_WEIGHT * p_model + P_MARKET_WEIGHT * p_market

        # ── Step 2: Signal boost (乘法，不是加法) ──
        # 暗號信號應該以乘法效應提升概率，而非固定加一個數值
        # 因為熱門馬的 +3% 和冷門馬的 +3% 意義完全不同
        no_int = _int(r.get("no"))
        horse_signals = [s for s in detected_signals if s.horse_no == no_int]
        
        # 計算乘法因子：每個信號貢獻一個 (1 + boost_factor)
        signal_multiplier = 1.0
        has_odds_drop = False
        for s in horse_signals:
            boost_factor = s.edge_boost * s.confidence * 0.035  # scaling factor
            signal_multiplier *= (1 + boost_factor)
            if s.signal_type == "odds_drop":
                has_odds_drop = True
        
        # ── 乘法上限與賠率掛鉤 ──
        # 冷門馬的 P_true/P_market 比率稍有偏誤就會被 EV 公式放大
        # 賠率越高的馬，允許的乘法上限越低
        odds_for_cap = win_odds_map.get(no_int, _float(r.get("winOdds"), 100))
        if odds_for_cap <= 5:
            signal_cap = 2.5   # 熱門馬：最多 2.5x
        elif odds_for_cap <= 10:
            signal_cap = 2.0   # 半熱門：最多 2.0x
        elif odds_for_cap <= 20:
            signal_cap = 1.6   # 中等：最多 1.6x
        elif odds_for_cap <= 40:
            signal_cap = 1.3   # 冷門：最多 1.3x
        else:
            signal_cap = 1.15  # 大冷門：最多 1.15x
        signal_multiplier = min(signal_multiplier, signal_cap)
        p_blend = p_blend * signal_multiplier

        # ── Step 3: 賠率急跌保底 ──
        # 如果賠率正在急跌，P_true 不應低於 P_market
        # 因為市場正在用真金白銀告訴你這匹馬被看好
        if has_odds_drop and p_blend < p_market:
            # 保底：P_true 至少 = P_market * 1.10（比市場高 10%）
            p_blend = p_market * 1.10

        # ── Step 4: P_true 偏離上限（與賠率掛鉤） ──
        # 冷門馬模型偏誤大，P_true 不得偏離 P_market 太遠
        # 賠率越高的馬，P_true/P_market 的允許比率越低
        if p_market > 0:
            odds_for_dev = win_odds_map.get(no_int, _float(r.get("winOdds"), 100))
            if odds_for_dev <= 5:
                max_deviation = 1.25   # 熱門馬：允許 P_true 最高 = P_market × 1.25
            elif odds_for_dev <= 10:
                max_deviation = 1.20   # 半熱門
            elif odds_for_dev <= 20:
                max_deviation = 1.15   # 中等
            elif odds_for_dev <= 40:
                max_deviation = 1.10   # 冷門
            else:
                max_deviation = 1.05   # 大冷門：P_true 最多比 P_market 高 5%
            
            ratio = p_blend / p_market
            if ratio > max_deviation:
                p_blend = p_market * max_deviation

        # Cap at 95%
        p_blend = min(p_blend, 0.95)
        p_blend_arr.append(p_blend)

    # ── 不做歸一化 ──
    # EV = P_true * odds - 1 是每匹馬獨立計算的
    # 歸一化會壓縮熱門馬的概率，破壞信號加成效果
    # P_true 不需要加起來等於 100%，因為我們是在跟 P_market 1/odds 比較
    # P_market 本身加起來也是 ~125%（含抽水）

    for i, r in enumerate(runners_raw):
        no = _int(r.get("no"))
        odds = win_odds_map.get(no, _float(r.get("winOdds"), 100))
        p_true = round(p_blend_arr[i], 4)
        p_market = round(p_market_arr[i], 4)
        ev = round(p_true * (odds - 1) - (1 - p_true), 4)
        edge = round(p_true - p_market, 4)
        kelly = max(0, (p_true * (odds - 1) - (1 - p_true)) / (odds - 1)) * KELLY_FRAC if odds > 1 else 0
        kelly = round(kelly, 4)

        # ── EV 信任度分級 ──
        # 高赔率冷門馬的 EV 不可靠（模型偏誤被放大），需要標記
        if odds <= 10:
            ev_confidence = "high"
        elif odds <= 25:
            ev_confidence = "medium"
        else:
            ev_confidence = "low"

        # ── 穩膽判定 ──
        # 熱門馬勝率很高但賠率太低導致 EV 為負，不該被當成壞選擇
        # 條件：P_market > 20%（市場認為勝率 >20%），或 P_true > 25% 且賠率 < 5
        strong_contender = False
        if p_market > 0.20 or (p_true > 0.25 and odds < 5):
            strong_contender = True

        # ── 檔位無影響判定 ──
        # 近績多次入前四，證明不同檔位都能跑，當前檔位劣勢可被抵消
        # 用 last6run 分析：≥5 次前四（6跑中）或 ≥4 次前四（≥5跑中）
        barrier_versatile = False
        last6 = r.get("last6run") or ""
        positions = [int(p) for p in last6.split('/') if p.strip().isdigit()]
        if positions:
            top4_count = sum(1 for p in positions if p <= 4)
            total_runs = len(positions)
            if total_runs >= 5 and top4_count >= 4:
                barrier_versatile = True
            elif total_runs >= 6 and top4_count >= 5:
                barrier_versatile = True
            # 額外：如果近4跑全部前四，更強信號
            if len(positions) >= 4 and all(p <= 4 for p in positions[:4]):
                barrier_versatile = True

        # ── 超級馬王判定 ──
        # 如「嘉應高昇」一類馬匹：近績極度出色，市場亦認同
        # 判定：近6跑≥5冠（不是前四，是冠軍！）且賠率<2.5
        # 這類馬匹超越正常分析框架——檔位、負磅、步速都影響有限
        superhorse = False
        if positions:
            win_count = sum(1 for p in positions if p == 1)
            total_runs_sh = len(positions)
            # 近6跑≥5冠 或 近5跑全部冠軍
            if (total_runs_sh >= 5 and win_count >= 5) or \
               (total_runs_sh >= 6 and win_count >= 5):
                if odds < 2.5:
                    superhorse = True
            # 額外：近4跑全部冠軍且賠率<3.0（即使樣本較少也足夠說明）
            if len(positions) >= 4 and all(p == 1 for p in positions[:4]) and odds < 3.0:
                superhorse = True

        # ── 價值投注篩選 ──
        # 冷門馬 (low confidence) 需要更高的門檻才能過關
        if ev_confidence == "high":
            is_vb = ev > EV_THRESH and edge > EDGE_THRESH and p_true > P_TRUE_THRESH
        elif ev_confidence == "medium":
            is_vb = ev > 0.03 and edge > 0.005 and p_true > P_TRUE_THRESH
        else:  # low confidence — 冷門馬需要更強的證據
            is_vb = ev > 0.05 and edge > 0.01 and p_true > 0.06

        pace_style = "front" if no in set(pace_setters + stalkers) else "closer"

        jockey = r.get("jockey", {})
        trainer = r.get("trainer", {})

        from app.services.quant_engine import JockeyTrainerComboScorer
           scorer = JockeyTrainerComboScorer()
           combo_result = scorer.get_combo_win_rate(
           jockey_name=runner.jockey,
           trainer_name=runner.trainer
         )

        runner_analyses.append(RunnerAnalysisOut(
            horse_no=no,
            horse_name=r.get("name_en", ""),
            horse_name_ch=r.get("name_ch", ""),
            barrier=_int(r.get("barrierDrawNumber"), 0),
            weight=_int(r.get("handicapWeight"), 0),
            jockey=jockey.get("name_en", ""),
            jockey_ch=jockey.get("name_ch", ""),
            trainer=trainer.get("name_en", ""),
            trainer_ch=trainer.get("name_ch", ""),
            win_odds=round(odds, 2),
            p_true=round(p_true * 100, 2),
            p_market=round(p_market * 100, 2),
            ev=round(ev * 100, 2),
            edge=round(edge * 100, 2),
            kelly_fraction=round(kelly * 100, 2),
            is_value_bet=is_vb,
            ev_confidence=ev_confidence,
            strong_contender=strong_contender,
            barrier_versatile=barrier_versatile,
            superhorse=superhorse,
            pace_style=pace_style,
            rating=round(scores[i], 1),
            last6run=r.get("last6run") or "",
            hot_favourite=hot_fav_map.get(no, False),
            odds_drop=odds_drop_map.get(no, 0),
            jockey_trainer_combo=combo_result
        ))

        # Smart money alerts
        if no in odds_drop_map:
            alerts.append(SmartMoneyAlertOut(
                horse_no=no,
                horse_name=r.get("name_en", ""),
                alert_type="odds_drop",
                severity="high" if odds_drop_map[no] > 2 else "medium" if odds_drop_map[no] > 1 else "low",
                description=f"賠率急跌 {odds_drop_map[no]:.1f}",
                odds_drop_value=odds_drop_map[no],
                current_odds=odds,
            ))
        if hot_fav_map.get(no, False):
            alerts.append(SmartMoneyAlertOut(
                horse_no=no,
                horse_name=r.get("name_en", ""),
                alert_type="hot_favourite",
                severity="medium",
                description="熱門馬（大額資金流入）",
                current_odds=odds,
            ))

    race_course = race.get("raceCourse") or {}

    # Convert detected signals to output format
    hidden_signals = [
        HiddenSignalOut(
            horse_no=s.horse_no,
            horse_name=s.horse_name,
            signal_type=s.signal_type,
            severity=s.severity,
            category=s.category,
            title_en=s.title_en,
            title_ch=s.title_ch,
            description=s.description,
            confidence=s.confidence,
            edge_boost=s.edge_boost,
        )
        for s in detected_signals
    ]

    return RaceAnalysisOut(
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
        runners=runner_analyses,
        pace_forecast=PaceForecastOut(
            pace_type=pace_type,
            front_runners=front_runners,
            mid_field=mid_field,
            closers=closers,
            description=f"快步速 — {n_setters}匹搶前馬互搶，後上馬有利" if pace_type == "fast"
                else f"慢步速 — 只有{n_front}匹前領候選，前領馬省力有利" if pace_type == "slow"
                else f"正常步速 — {n_front}匹前領候選",
        ),
        smart_money_alerts=alerts,
        hidden_signals=hidden_signals,
        value_bet_count=sum(1 for r in runner_analyses if r.is_value_bet),
        timestamp=time.time(),
    )


@router.get("/results")
async def live_results(
    date: str = Query(..., description="YYYY-MM-DD"),
):
    """獲取歷史賽果（HTML 解析）"""
    from datetime import date as date_type
    try:
        y, m, d = date.split("-")
        race_date = date_type(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    provider = get_provider()
    result = provider.fetch_results(race_date)

    return {
        "date": date,
        "venue": result.venue,
        "races": {
            str(k): [
                {
                    "position": r.position,
                    "horse_no": r.horse_number,
                    "horse_name": r.horse_name,
                    "brand": r.brand_number,
                    "jockey": r.jockey_name,
                    "trainer": r.trainer_name,
                                   "weight": r.actual_weight,
                    "horse_weight": r.horse_weight,
                    "barrier": r.barrier,
                    "lbw": r.lbw,
                    "finish_time": r.finish_time,
                    "win_odds": r.win_odds,
                    "running_positions": r.running_positions,
                }
                for r in runners
            ]
            for k, runners in result.races.items()
        },
        "race_metadata": {
            str(k): v for k, v in result.race_metadata.items()
        },
    }
