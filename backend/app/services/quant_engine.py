"""
核心量化計算邏輯 —— Hong Kong Racing Quant Engine

三大模組：
  1. TrueProbabilityCalculator  → 計算 P_true（模型真實勝率）
  2. MarketProbabilityEngine    → 反向工程 P_market（市場隱含勝率）
  3. ValueBetDetector           → +EV 篩選 + 凱利公式
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import numpy as np
from sklearn.preprocessing import StandardScaler


# ═══════════════════════════════════════════════
#  Data Classes: 特徵向量與計算結果
# ═══════════════════════════════════════════════

@dataclass
class RunnerFeatures:
    """單匹出賽馬的特徵向量"""
    runner_id: int
    horse_id: int

    # ── 基礎特徵 ──
    barrier: int                              # 檔位
    declared_weight: float                    # 負磅
    weight_change: float                      # 體重變幅
    horse_age: int                            # 馬齡
    horse_rating: int                         # 評分

    # ── 戰績特徵 ──
    recent_positions: List[int]               # 近 5 場名次
    win_strike_rate: float                    # 勝出率
    place_strike_rate: float                  # 入位率

    # ── 人員特徵 ──
    jockey_win_rate: float                    # 騎師勝率
    trainer_win_rate: float                   # 練馬師勝率
    jockey_trainer_combo_rate: float          # 騎練組合勝率
    jockey_horse_win_rate: float              # 騎師騎此馬勝率

    # ── 場地/路程特徵 ──
    distance_suitability: float               # 路程適性 0-1
    going_preference: float                   # 場地偏好 0-1
    venue_win_rate: float                     # 該場地勝率
    course_config_advantage: float            # 跑道配置優勢（如 HV C+3 短途內檔加成）

    # ── 步速特徵 ──
    running_style: str                        # Front/Presser/Stalker/Closer
    pace_advantage_score: float               # 步速形勢評分

    # ── 速度指標 ──
    speed_figure_last: float                  # 上場速度指標
    speed_figure_avg3: float                  # 近 3 場平均速度指標
    sectional_time_best: float                # 最佳段速

    # ── 賽事結構特徵 ──
    class_drop: bool                          # 是否降班
    class_rise: bool                          # 是否升班
    days_since_last_run: int                  # 距上次出賽天數

    # ── 市場特徵 ──
    smart_money_flag: bool = False            # 是否有聰明錢流入
    odds_movement_5min: float = 0.0           # 5 分鐘賠率變動


@dataclass
class ValueBetResult:
    """+EV 計算結果"""
    runner_id: int
    true_probability: float                   # P_true
    market_probability: float                 # P_market
    win_odds: float                           # 獨贏賠率
    expected_value: float                     # EV = P_true × 賠率 - 1
    is_value_bet: bool                        # 是否 +EV
    kelly_fraction: float                     # 凱利投注比例
    edge_percentage: float                    # 優勢百分比 (P_true - P_market) / P_market
    confidence_level: str                     # High / Medium / Low


@dataclass
class FeatureWeights:
    """特徵權重配置（對應 FeatureWeightProfile DB model）"""
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


# ═══════════════════════════════════════════════
#  Module 1: True Probability Calculator
# ═══════════════════════════════════════════════

class TrueProbabilityCalculator:
    """
    計算每匹馬的真實勝率 P_true。

    方法論：
    - 第一版使用加權評分法（Weighted Rating），快速可解釋
    - 第二版可升級為 XGBoost / Multinomial Logistic Regression
    - 關鍵：同場馬匹的 P_true 之和必須 = 1（正規化為 Softmax）

    香港賽馬特別考量：
    1. 檔位優勢：跑馬地短途內檔（1-4檔）加成明顯
    2. 步速預測：領放馬在慢步速場次有巨大優勢
    3. 班次升降：降班馬勝率顯著高於平均
    4. 騎練組合：頂級騎練組合勝率是散戶的 3-5 倍
    """

    # 跑馬地短途檔位優勢表（1200m C 跑道，基於歷史統計）
    HV_1200_BARRIER_ADVANTAGE = {
        1: 1.25, 2: 1.22, 3: 1.18, 4: 1.15,
        5: 1.10, 6: 1.05, 7: 1.00, 8: 0.95,
        9: 0.92, 10: 0.88, 11: 0.85, 12: 0.82,
    }

    # 沙田 1200m 檔位優勢（外檔劣勢不如跑馬地明顯）
    STV_1200_BARRIER_ADVANTAGE = {
        1: 1.10, 2: 1.08, 3: 1.06, 4: 1.05,
        5: 1.03, 6: 1.01, 7: 1.00, 8: 0.98,
        9: 0.97, 10: 0.96, 11: 0.95, 12: 0.94,
        13: 0.93, 14: 0.92,
    }

    def __init__(self, weights: Optional[FeatureWeights] = None):
        self.weights = weights or FeatureWeights()

    def compute_raw_scores(self, runners: List[RunnerFeatures]) -> np.ndarray:
        """
        計算每匹馬的原始綜合評分（未正規化）。

        評分公式：
        score = Σ(weight_i × feature_i) + special_adjustments

        特殊調整：
        - 檔位優勢：根據賽道+路程查表
        - 步速形勢：領放馬在慢步速場次獲得加成
        - 降班加成 / 升班懲罰
        """
        scores = []
        for r in runners:
            s = 0.0

            # ── 檔位評分 ──
            # 這裡用通用版，實際調用時會根據 venue/distance 查表替換
            barrier_score = self._barrier_score(r.barrier)
            s += self.weights.w_barrier * barrier_score

            # ── 近績評分（近 5 場名次轉評分）──
            form_score = self._form_score(r.recent_positions)
            s += self.weights.w_recent_form * form_score

            # ── 騎師評分 ──
            s += self.weights.w_jockey * (r.jockey_win_rate * 10)  # scale 0-10

            # ── 練馬師評分 ──
            s += self.weights.w_trainer * (r.trainer_win_rate * 10)

            # ── 騎練組合 ──
            s += self.weights.w_jt_combo * (r.jockey_trainer_combo_rate * 12)

            # ── 路程適性 ──
            s += self.weights.w_distance_suitability * (r.distance_suitability * 5)

            # ── 場地偏好 ──
            s += self.weights.w_going_preference * (r.going_preference * 5)

            # ── 體重變幅（大幅變化扣分）──
            weight_penalty = -abs(r.weight_change) * 0.1
            s += self.weights.w_weight_change * weight_penalty

            # ── 速度指標 ──
            speed_score = (r.speed_figure_avg3 * 0.6 + r.speed_figure_last * 0.4)
            s += self.weights.w_speed_figure * speed_score

            # ── 步速形勢 ──
            s += self.weights.w_pace_scenario * r.pace_advantage_score

            # ── 班次升降 ──
            if r.class_drop:
                s += self.weights.w_class_drop * 2.0   # 降班加成
            if r.class_rise:
                s += self.weights.w_class_rise * (-1.5)  # 升班懲罰

            # ── 聰明錢 ──
            if r.smart_money_flag:
                s += self.weights.w_smart_money * 3.0

            scores.append(s)

        return np.array(scores)

    def compute_probabilities(self, runners: List[RunnerFeatures]) -> List[float]:
        """
        用 Softmax 將原始評分轉換為勝率分佈。
        P_true(i) = exp(score_i) / Σ exp(score_j)

        溫度參數 (temperature) 控制「確定性程度」：
        - temperature < 1：分佈更尖銳（更確定）
        - temperature > 1：分佈更平坦（更不確定）
        - 預設 1.0

        數值穩定：先平移使最大值為 0，再對極小值做 floor 防止 exp 溢出。
        """
        scores = self.compute_raw_scores(runners)

        # Softmax with temperature
        temperature = 1.0
        scaled = scores / temperature

        # 數值穩定：平移使最大值為 0
        shifted = scaled - np.max(scaled)

        # 對極小值做 floor（防止 exp 溢出為 0）
        shifted = np.clip(shifted, -50, 0)

        exp_scores = np.exp(shifted)
        total = exp_scores.sum()
        if total == 0:
            # Fallback：均勻分佈
            probabilities = np.ones(len(runners)) / len(runners)
        else:
            probabilities = exp_scores / total

        # 最終保底：確保沒有 0（每匹馬至少有 0.5% 勝率）
        MIN_PROB = 0.005
        probabilities = np.maximum(probabilities, MIN_PROB)
        probabilities = probabilities / probabilities.sum()

        return probabilities.tolist()

    @staticmethod
    def _barrier_score(barrier: int) -> float:
        """通用檔位評分（1-3 檔最優，14+ 最劣）"""
        if barrier <= 3:
            return 3.0
        elif barrier <= 6:
            return 2.5
        elif barrier <= 9:
            return 2.0
        elif barrier <= 12:
            return 1.5
        else:
            return 1.0

    @staticmethod
    def _barrier_advantage(barrier: int, venue: str, distance: int) -> float:
        """
        根據賽道+路程的檔位優勢查表。
        跑馬地短途（1200m）內檔優勢極大。
        """
        if venue == "HV" and distance <= 1200:
            table = TrueProbabilityCalculator.HV_1200_BARRIER_ADVANTAGE
        elif venue == "STV" and distance <= 1200:
            table = TrueProbabilityCalculator.STV_1200_BARRIER_ADVANTAGE
        else:
            return 1.0  # 中長途檔位影響較小
        return table.get(barrier, 0.80)

    @staticmethod
    def _form_score(recent_positions: List[int]) -> float:
        """
        近績評分：
        - 第 1 名 = 5 分
        - 第 2 名 = 3 分
        - 第 3 名 = 2 分
        - 第 4-5 名 = 1 分
        - 第 6+ 名 = 0 分
        - 越近的場次權重越高（指數衰減）
        """
        position_points = {1: 5, 2: 3, 3: 2, 4: 1, 5: 1}
        total = 0.0
        for i, pos in enumerate(recent_positions[:5]):
            # 權重衰減：最近一場 weight=1.0, 往前每場 ×0.8
            weight = 0.8 ** i
            points = position_points.get(pos, 0)
            total += weight * points
        return total


# ═══════════════════════════════════════════════
#  Module 2: Market Probability Engine
# ═══════════════════════════════════════════════

class MarketProbabilityEngine:
    """
    反向工程市場機率 P_market。

    香港賽馬採彩池制（Pari-mutuel）：
    - 獨贏彩池抽水率 ≈ 17.5%（含博彩稅 + 馬會佣金 + 獎券基金）
    - 市場隱含機率 = 1 / 賠率
    - 所有馬匹隱含機率之和 > 1（超額代表抽水）

    公式：
      P_market(i) = (1 / win_odds_i) / Σ(1 / win_odds_j)

    其中分母是正規化因子，確保 P_market 之和 = 1
    """

    HKJC_TAKEOUT_RATE = 0.175  # 馬會抽水率

    @staticmethod
    def compute_market_probabilities(win_odds: List[float]) -> List[float]:
        """
        從獨贏賠率計算市場隱含機率（已去除抽水）。

        Args:
            win_odds: 各匹馬的獨贏賠率列表

        Returns:
            各匹馬的市場機率列表（已正規化，之和 = 1）
        """
        implied = [1.0 / odds for odds in win_odds]
        total_implied = sum(implied)

        # 正規化：去除抽水的影響
        market_probs = [imp / total_implied for imp in implied]
        return market_probs

    @staticmethod
    def compute_takeout_percentage(win_odds: List[float]) -> float:
        """
        計算市場實際抽水百分比（Overround）。
        overround = Σ(1/odds) - 1

        正常情況下：
        - HKJC 獨贏 overround ≈ 17-19%
        - 如果 overround < 15%，可能有數據異常
        """
        return sum(1.0 / odds for odds in win_odds) - 1.0

    @staticmethod
    def fair_odds_from_probability(probability: float) -> float:
        """從真實機率計算公平賠率（不含抽水）"""
        if probability <= 0:
            return float('inf')
        return 1.0 / probability

    @staticmethod
    def adjusted_fair_odds(probability: float, takeout: float = 0.175) -> float:
        """
        計算含抽水調整的公平賠率。
        彩池制下實際可獲賠率 = 公平賠率 × (1 - takeout)
        即 fair_odds_adjusted = (1/P) × (1 - takeout)
        抽水令可獲賠率比公平賠率更低（更差）
        """
        if probability <= 0:
            return float('inf')
        return (1.0 / probability) * (1 - takeout)


# ═══════════════════════════════════════════════
#  Module 3: Value Bet Detector (+EV Filter + Kelly)
# ═══════════════════════════════════════════════

class ValueBetDetector:
    """
    +EV 價值投注偵測器。

    核心邏輯：
      EV = P_true × win_odds - 1

    當 EV > 0 時，該投注具有正期望值。

    篩選條件（三重驗證）：
    1. EV > 0（基本條件）
    2. Edge > 閾值（避免微小邊際被方差吞噬）
       edge = (P_true - P_market) / P_market
    3. P_true 最低門檻（避免極低勝率的高赔率陷阱）

    凱利公式：
      f* = (P_true × win_odds - 1) / (win_odds - 1)
      簡化版：f* = (b × p - q) / b
        其中 b = win_odds - 1, p = P_true, q = 1 - P_true

    實際應用使用 Fractional Kelly（通常 1/3 到 1/2）以降低方差。
    """

    # ── 篩選參數 ──
    MIN_EV_THRESHOLD = 0.05          # 最低 EV 門檻：+5%
    MIN_EDGE_THRESHOLD = 0.10        # 最低 Edge 門檻：10%
    MIN_TRUE_PROBABILITY = 0.04      # 最低真實勝率：4%
    KELLY_FRACTION = 0.33            # 使用 1/3 Kelly（保守）

    # ── 信心等級 ──
    CONFIDENCE_HIGH_EV = 0.15        # EV > 15% = High
    CONFIDENCE_MEDIUM_EV = 0.10      # EV > 10% = Medium

    @classmethod
    def detect(
        cls,
        true_probabilities: List[float],
        win_odds: List[float],
        runner_ids: List[int],
        smart_money_flags: Optional[List[bool]] = None,
    ) -> List[ValueBetResult]:
        """
        對一場比賽的所有馬匹執行 +EV 檢測。

        Args:
            true_probabilities: 模型計算的各馬真實勝率
            win_odds: 各馬的獨贏賠率
            runner_ids: 各馬的 runner_id
            smart_money_flags: 各馬是否有聰明錢流入

        Returns:
            各馬的 ValueBetResult 列表
        """
        market_probs = MarketProbabilityEngine.compute_market_probabilities(win_odds)
        results = []

        for i, (rid, p_true, p_market, odds) in enumerate(
            zip(runner_ids, true_probabilities, market_probs, win_odds)
        ):
            # 計算 EV
            ev = p_true * odds - 1.0

            # 計算 Edge
            edge = (p_true - p_market) / p_market if p_market > 0 else 0.0

            # 凱利公式
            kelly = cls._kelly_criterion(p_true, odds)

            # 三重驗證
            is_value = (
                ev > cls.MIN_EV_THRESHOLD
                and edge > cls.MIN_EDGE_THRESHOLD
                and p_true > cls.MIN_TRUE_PROBABILITY
            )

            # 聰明錢加成（如果該馬有 smart money 流入，降低 EV 門檻）
            if smart_money_flags and smart_money_flags[i]:
                is_value = is_value or (ev > 0.02 and p_true > 0.05)

            # 信心等級
            if ev >= cls.CONFIDENCE_HIGH_EV:
                confidence = "High"
            elif ev >= cls.CONFIDENCE_MEDIUM_EV:
                confidence = "Medium"
            else:
                confidence = "Low"

            results.append(ValueBetResult(
                runner_id=rid,
                true_probability=round(p_true, 4),
                market_probability=round(p_market, 4),
                win_odds=odds,
                expected_value=round(ev, 4),
                is_value_bet=is_value,
                kelly_fraction=round(kelly * cls.KELLY_FRACTION, 4),
                edge_percentage=round(edge, 4),
                confidence_level=confidence,
            ))

        return results

    @staticmethod
    def _kelly_criterion(p_true: float, win_odds: float) -> float:
        """
        凱利公式：計算最優投注比例。

        f* = (b × p - q) / b
          b = win_odds - 1  (淨賠率)
          p = P_true
          q = 1 - P_true

        Returns:
            建議投注比例（0 到 1）。若結果為負，表示不應投注。
        """
        b = win_odds - 1.0
        if b <= 0:
            return 0.0
        q = 1.0 - p_true
        kelly = (b * p_true - q) / b
        return max(0.0, kelly)


# ═══════════════════════════════════════════════
#  Module 4: Pace Forecasting Engine
# ═══════════════════════════════════════════════

class PaceForecaster:
    """
    步速預測引擎。

    香港賽馬步速分析：
    - 根據出賽馬匹的 running_style 分佈，預測本場步速
    - 前領馬多 → 快步速 → 利後上馬
    - 前領馬少 → 慢步速 → 利領放馬

    步速形勢評分：
    - Front runner in slow pace → 高分
    - Closer in fast pace → 高分
    """

    @staticmethod
    def forecast_pace(runners: List[RunnerFeatures]) -> Dict:
        """
        預測步速形勢。

        Returns:
            {
                "pace_scenario": "Slow" / "Moderate" / "Fast",
                "front_runners": int,
                "pressers": int,
                "closers": int,
                "pace_advantage": { runner_id: score }
            }
        """
        front_count = sum(1 for r in runners if r.running_style in ("Front", "Presser"))
        stalker_count = sum(1 for r in runners if r.running_style == "Stalker")
        closer_count = sum(1 for r in runners if r.running_style == "Closer")

        total = len(runners)
        front_ratio = front_count / total if total > 0 else 0

        # 步速判定
        if front_ratio >= 0.5:
            pace = "Fast"
        elif front_ratio <= 0.25:
            pace = "Slow"
        else:
            pace = "Moderate"

        # 為每匹馬計算步速形勢優勢分
        pace_advantage = {}
        for r in runners:
            if pace == "Slow":
                # 慢步速利領放馬
                adv = {"Front": 4.0, "Presser": 2.5, "Stalker": 0.5, "Closer": -1.0}
            elif pace == "Fast":
                # 快步速利後上馬
                adv = {"Front": -1.5, "Presser": 0.0, "Stalker": 2.0, "Closer": 3.5}
            else:
                adv = {"Front": 1.0, "Presser": 1.5, "Stalker": 1.0, "Closer": 0.5}

            pace_advantage[r.runner_id] = adv.get(r.running_style, 0.0)

        return {
            "pace_scenario": pace,
            "front_runners": front_count,
            "pressers": stalker_count,
            "cloers": closer_count,
            "pace_advantage": pace_advantage,
        }


# ═══════════════════════════════════════════════
#  Module 5: Smart Money Detector
# ═══════════════════════════════════════════════

class SmartMoneyDetector:
    """
    聰明錢（Smart Money / Insider Money）偵測器。

    原理：
    - 職業辛迪加和內幕人士通常在閘前 5-1 分鐘大額下注
    - 表現為賠率急跌（odds drop）且彩池金額同步急增
    - 識別條件：
      1. 賠率在 5 分鐘內下跌 ≥ 15%
      2. 彩池金額在同期增長 ≥ 20%（排除因退注導致的假跌）
      3. 跌幅集中在閘前 5 分鐘內（非漸進式）
    """

    ODDS_DROP_THRESHOLD = 0.15      # 賠率跌幅 ≥ 15%
    POOL_SURGE_THRESHOLD = 0.20     # 彩池增幅 ≥ 20%
    TIME_WINDOW_SECONDS = 300       # 5 分鐘窗口

    @classmethod
    def detect_smart_money(
        cls,
        odds_history: List[Dict],
    ) -> Dict[int, bool]:
        """
        分析賠率歷史，偵測聰明錢。

        Args:
            odds_history: [
                {
                    "runner_id": int,
                    "timestamp": datetime,
                    "win_odds": float,
                    "win_pool": int
                }, ...
            ]

        Returns:
            { runner_id: is_smart_money }
        """
        # 按 runner_id 分組
        by_runner: Dict[int, List[Dict]] = {}
        for entry in odds_history:
            rid = entry["runner_id"]
            by_runner.setdefault(rid, []).append(entry)

        results = {}
        for rid, entries in by_runner.items():
            if len(entries) < 2:
                results[rid] = False
                continue

            # 按時間排序
            entries.sort(key=lambda x: x["timestamp"])

            # 找 5 分鐘窗口內最大跌幅
            is_smart = False
            for i in range(len(entries)):
                window = [
                    e for e in entries
                    if 0 <= (e["timestamp"] - entries[i]["timestamp"]).total_seconds() <= cls.TIME_WINDOW_SECONDS
                ]
                if len(window) < 2:
                    continue

                earliest = window[0]
                latest = window[-1]

                odds_drop = (earliest["win_odds"] - latest["win_odds"]) / earliest["win_odds"]
                pool_surge = (latest["win_pool"] - earliest["win_pool"]) / max(earliest["win_pool"], 1)

                if odds_drop >= cls.ODDS_DROP_THRESHOLD and pool_surge >= cls.POOL_SURGE_THRESHOLD:
                    is_smart = True
                    break

            results[rid] = is_smart

        return results


# ═══════════════════════════════════════════════
#  Orchestrator: 量化分析主流程
# ═══════════════════════════════════════════════

class QuantAnalysisOrchestrator:
    """
    量化分析主流程編排器。

    流程：
    1. PaceForecaster → 預測步速，更新 pace_advantage_score
    2. TrueProbabilityCalculator → 計算 P_true
    3. MarketProbabilityEngine → 計算 P_market
    4. ValueBetDetector → +EV 篩選 + 凱利公式
    5. （可選）SmartMoneyDetector → 聰明錢偵測
    """

    def __init__(self, weights: Optional[FeatureWeights] = None):
        self.weights = weights or FeatureWeights()
        self.prob_calc = TrueProbabilityCalculator(self.weights)
        self.pace_forecaster = PaceForecaster()

    def analyze_race(
        self,
        runners: List[RunnerFeatures],
        win_odds: List[float],
        runner_ids: List[int],
        odds_history: Optional[List[Dict]] = None,
    ) -> List[ValueBetResult]:
        """
        對一場比賽執行完整量化分析。

        Args:
            runners: 出賽馬特徵列表
            win_odds: 各馬獨贏賠率
            runner_ids: 各馬 runner_id
            odds_history: 賠率歷史（用於聰明錢偵測）

        Returns:
            各馬的 ValueBetResult
        """
        # Step 1: 步速預測 → 更新各馬的 pace_advantage_score
        pace_result = self.pace_forecaster.forecast_pace(runners)
        for r in runners:
            r.pace_advantage_score = pace_result["pace_advantage"].get(r.runner_id, 0.0)

        # Step 1.5: 聰明錢偵測（如有賠率歷史）
        smart_money_flags = [False] * len(runners)
        if odds_history:
            sm_results = SmartMoneyDetector.detect_smart_money(odds_history)
            for i, r in enumerate(runners):
                smart_money_flags[i] = sm_results.get(r.runner_id, False)
                r.smart_money_flag = smart_money_flags[i]

        # Step 2: 計算 P_true
        true_probs = self.prob_calc.compute_probabilities(runners)

        # Step 3 + 4: 計算 P_market 並偵測 +EV
        results = ValueBetDetector.detect(
            true_probabilities=true_probs,
            win_odds=win_odds,
            runner_ids=runner_ids,
            smart_money_flags=smart_money_flags,
        )

        return results
