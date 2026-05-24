"""
Unit tests for the Quant Engine core logic.
Run: python -m pytest tests/test_quant_engine.py -v
"""
import pytest
import numpy as np
from app.services.quant_engine import (
    TrueProbabilityCalculator,
    MarketProbabilityEngine,
    ValueBetDetector,
    PaceForecaster,
    QuantAnalysisOrchestrator,
    RunnerFeatures,
    FeatureWeights,
)


# ─────────────────────────────────────────────
#  Test Fixtures: 模擬一場 8 匹馬的比賽
# ─────────────────────────────────────────────

def make_sample_runners() -> list:
    """構建 8 匹模擬出賽馬"""
    runners = [
        RunnerFeatures(
            runner_id=1, horse_id=101,
            barrier=1, declared_weight=120, weight_change=0,
            horse_age=5, horse_rating=95,
            recent_positions=[1, 2, 1, 3, 1],
            win_strike_rate=0.25, place_strike_rate=0.50,
            jockey_win_rate=0.18, trainer_win_rate=0.15,
            jockey_trainer_combo_rate=0.20, jockey_horse_win_rate=0.30,
            distance_suitability=0.85, going_preference=0.80,
            venue_win_rate=0.22, course_config_advantage=0.1,
            running_style="Front", pace_advantage_score=2.0,
            speed_figure_last=85, speed_figure_avg3=83,
            sectional_time_best=22.5,
            class_drop=False, class_rise=False,
            days_since_last_run=21,
        ),
        RunnerFeatures(
            runner_id=2, horse_id=102,
            barrier=3, declared_weight=118, weight_change=2,
            horse_age=4, horse_rating=88,
            recent_positions=[3, 1, 2, 4, 1],
            win_strike_rate=0.20, place_strike_rate=0.45,
            jockey_win_rate=0.16, trainer_win_rate=0.12,
            jockey_trainer_combo_rate=0.15, jockey_horse_win_rate=0.20,
            distance_suitability=0.70, going_preference=0.60,
            venue_win_rate=0.18, course_config_advantage=0.05,
            running_style="Presser", pace_advantage_score=1.5,
            speed_figure_last=82, speed_figure_avg3=81,
            sectional_time_best=22.8,
            class_drop=True, class_rise=False,
            days_since_last_run=28,
        ),
        RunnerFeatures(
            runner_id=3, horse_id=103,
            barrier=7, declared_weight=125, weight_change=-5,
            horse_age=6, horse_rating=82,
            recent_positions=[5, 4, 6, 3, 5],
            win_strike_rate=0.10, place_strike_rate=0.30,
            jockey_win_rate=0.12, trainer_win_rate=0.10,
            jockey_trainer_combo_rate=0.08, jockey_horse_win_rate=0.10,
            distance_suitability=0.55, going_preference=0.50,
            venue_win_rate=0.10, course_config_advantage=0,
            running_style="Closer", pace_advantage_score=-1.0,
            speed_figure_last=78, speed_figure_avg3=77,
            sectional_time_best=23.2,
            class_drop=False, class_rise=False,
            days_since_last_run=14,
        ),
        RunnerFeatures(
            runner_id=4, horse_id=104,
            barrier=10, declared_weight=115, weight_change=8,
            horse_age=7, horse_rating=78,
            recent_positions=[8, 6, 7, 9, 8],
            win_strike_rate=0.05, place_strike_rate=0.15,
            jockey_win_rate=0.08, trainer_win_rate=0.07,
            jockey_trainer_combo_rate=0.05, jockey_horse_win_rate=0.03,
            distance_suitability=0.40, going_preference=0.35,
            venue_win_rate=0.05, course_config_advantage=-0.05,
            running_style="Stalker", pace_advantage_score=0.5,
            speed_figure_last=72, speed_figure_avg3=73,
            sectional_time_best=23.5,
            class_drop=False, class_rise=True,
            days_since_last_run=7,
        ),
        RunnerFeatures(
            runner_id=5, horse_id=105,
            barrier=2, declared_weight=122, weight_change=-1,
            horse_age=4, horse_rating=92,
            recent_positions=[2, 1, 1, 2, 3],
            win_strike_rate=0.22, place_strike_rate=0.48,
            jockey_win_rate=0.20, trainer_win_rate=0.18,
            jockey_trainer_combo_rate=0.22, jockey_horse_win_rate=0.25,
            distance_suitability=0.90, going_preference=0.85,
            venue_win_rate=0.25, course_config_advantage=0.08,
            running_style="Front", pace_advantage_score=2.5,
            speed_figure_last=88, speed_figure_avg3=86,
            sectional_time_best=22.2,
            class_drop=False, class_rise=False,
            days_since_last_run=25,
        ),
        RunnerFeatures(
            runner_id=6, horse_id=106,
            barrier=5, declared_weight=119, weight_change=3,
            horse_age=5, horse_rating=85,
            recent_positions=[4, 3, 5, 2, 4],
            win_strike_rate=0.12, place_strike_rate=0.35,
            jockey_win_rate=0.14, trainer_win_rate=0.13,
            jockey_trainer_combo_rate=0.10, jockey_horse_win_rate=0.12,
            distance_suitability=0.65, going_preference=0.70,
            venue_win_rate=0.14, course_config_advantage=0.02,
            running_style="Presser", pace_advantage_score=1.0,
            speed_figure_last=80, speed_figure_avg3=79,
            sectional_time_best=22.9,
            class_drop=False, class_rise=False,
            days_since_last_run=18,
        ),
        RunnerFeatures(
            runner_id=7, horse_id=107,
            barrier=11, declared_weight=128, weight_change=0,
            horse_age=8, horse_rating=75,
            recent_positions=[6, 8, 5, 7, 6],
            win_strike_rate=0.06, place_strike_rate=0.20,
            jockey_win_rate=0.06, trainer_win_rate=0.05,
            jockey_trainer_combo_rate=0.04, jockey_horse_win_rate=0.02,
            distance_suitability=0.30, going_preference=0.25,
            venue_win_rate=0.04, course_config_advantage=-0.08,
            running_style="Closer", pace_advantage_score=-0.5,
            speed_figure_last=70, speed_figure_avg3=71,
            sectional_time_best=23.8,
            class_drop=False, class_rise=False,
            days_since_last_run=35,
        ),
        RunnerFeatures(
            runner_id=8, horse_id=108,
            barrier=8, declared_weight=117, weight_change=-2,
            horse_age=3, horse_rating=80,
            recent_positions=[1, 3, 2, 1, 2],
            win_strike_rate=0.18, place_strike_rate=0.42,
            jockey_win_rate=0.15, trainer_win_rate=0.14,
            jockey_trainer_combo_rate=0.12, jockey_horse_win_rate=0.15,
            distance_suitability=0.75, going_preference=0.65,
            venue_win_rate=0.16, course_config_advantage=0.01,
            running_style="Stalker", pace_advantage_score=0.8,
            speed_figure_last=81, speed_figure_avg3=82,
            sectional_time_best=22.7,
            class_drop=True, class_rise=False,
            days_since_last_run=22,
        ),
    ]
    return runners


# ─────────────────────────────────────────────
#  Test 1: TrueProbabilityCalculator
# ─────────────────────────────────────────────

class TestTrueProbabilityCalculator:

    def test_probabilities_sum_to_one(self):
        """勝率之和必須 = 1.0"""
        runners = make_sample_runners()
        calc = TrueProbabilityCalculator()
        probs = calc.compute_probabilities(runners)
        assert abs(sum(probs) - 1.0) < 1e-6, f"Probabilities sum to {sum(probs)}"

    def test_better_horse_higher_probability(self):
        """強馬（5號）勝率應高於弱馬（7號）"""
        runners = make_sample_runners()
        calc = TrueProbabilityCalculator()
        probs = calc.compute_probabilities(runners)

        horse_5_prob = probs[4]   # runner_id=5, index=4
        horse_7_prob = probs[6]   # runner_id=7, index=6
        assert horse_5_prob > horse_7_prob, (
            f"Horse 5 ({horse_5_prob:.4f}) should be > Horse 7 ({horse_7_prob:.4f})"
        )

    def test_all_probabilities_positive(self):
        """所有勝率 > 0"""
        runners = make_sample_runners()
        calc = TrueProbabilityCalculator()
        probs = calc.compute_probabilities(runners)
        for i, p in enumerate(probs):
            assert p > 0, f"Runner {i+1} has zero probability"

    def test_custom_weights_affect_probabilities(self):
        """自訂權重會影響勝率分佈"""
        runners = make_sample_runners()

        # Default weights
        calc_default = TrueProbabilityCalculator(FeatureWeights())
        probs_default = calc_default.compute_probabilities(runners)

        # Overweight jockey
        heavy_jockey = FeatureWeights(w_jockey=3.0)
        calc_heavy = TrueProbabilityCalculator(heavy_jockey)
        probs_heavy = calc_heavy.compute_probabilities(runners)

        # 分佈應該不同
        assert probs_default != probs_heavy


# ─────────────────────────────────────────────
#  Test 2: MarketProbabilityEngine
# ─────────────────────────────────────────────

class TestMarketProbabilityEngine:

    def test_market_probabilities_sum_to_one(self):
        """市場機率之和 = 1.0"""
        odds = [3.5, 5.0, 8.0, 15.0, 4.0, 7.0, 25.0, 10.0]
        probs = MarketProbabilityEngine.compute_market_probabilities(odds)
        assert abs(sum(probs) - 1.0) < 1e-6

    def test_lower_odds_higher_probability(self):
        """低賠率 = 高市場機率"""
        odds = [3.5, 5.0, 8.0, 15.0, 4.0, 7.0, 25.0, 10.0]
        probs = MarketProbabilityEngine.compute_market_probabilities(odds)
        # 賠率 3.5 應該對應最高機率
        assert probs[0] > probs[6]  # odds 3.5 vs 25.0

    def test_takeout_calculation(self):
        """抽水率計算"""
        # 理論上 HKJC overround ≈ 17.5%
        # 用一組模擬賠率
        odds = [3.0, 4.5, 7.0, 12.0, 3.5, 6.0, 20.0, 9.0]
        overround = MarketProbabilityEngine.compute_takeout_percentage(odds)
        assert overround > 0, "Overround should be positive"
        # 對於合理的賽馬賠率，overround 通常在 15-25%
        print(f"Overround: {overround:.2%}")

    def test_fair_odds_calculation(self):
        """公平賠率計算"""
        prob = 0.25  # 25% 勝率
        fair = MarketProbabilityEngine.fair_odds_from_probability(prob)
        assert fair == 4.0

        # 含抽水：可獲賠率 = fair × (1 - takeout)，比公平賠率更低
        adjusted = MarketProbabilityEngine.adjusted_fair_odds(prob)
        assert adjusted < fair, "Adjusted odds should be lower (worse) than fair odds due to takeout"


# ─────────────────────────────────────────────
#  Test 3: ValueBetDetector
# ─────────────────────────────────────────────

class TestValueBetDetector:

    def test_value_bet_detection(self):
        """偵測 +EV 投注"""
        # 模擬：模型認為 2 號馬勝率 25%，但市場只給 6.0 賠率
        # EV = 0.25 × 6.0 - 1 = 0.50 (+50%)  → 明顯 +EV
        true_probs = [0.30, 0.25, 0.15, 0.08, 0.10, 0.05, 0.03, 0.04]
        win_odds =   [3.0,  6.0,  8.0,  15.0, 10.0, 20.0, 30.0, 25.0]
        runner_ids = [1, 2, 3, 4, 5, 6, 7, 8]

        results = ValueBetDetector.detect(true_probs, win_odds, runner_ids)

        # 2 號馬應該被標記為 +EV
        horse_2 = results[1]
        assert horse_2.is_value_bet, f"Horse 2 should be value bet: EV={horse_2.expected_value}"
        assert horse_2.expected_value > 0
        assert horse_2.kelly_fraction > 0

    def test_no_value_when_overrated(self):
        """被高估的馬不應被標記為 +EV"""
        # 模擬：模型認為 7 號馬勝率 3%，但市場只給 10.0 賠率
        # EV = 0.03 × 10.0 - 1 = -0.70  → 負 EV
        true_probs = [0.35, 0.20, 0.18, 0.10, 0.08, 0.05, 0.03, 0.01]
        win_odds =   [2.5,  4.5,  5.0,  10.0, 12.0, 18.0, 10.0, 50.0]
        runner_ids = [1, 2, 3, 4, 5, 6, 7, 8]

        results = ValueBetDetector.detect(true_probs, win_odds, runner_ids)
        horse_7 = results[6]
        assert not horse_7.is_value_bet or horse_7.expected_value < 0.05

    def test_kelly_fraction_bounded(self):
        """凱利比例在 0-1 之間"""
        true_probs = [0.30, 0.25, 0.15, 0.08, 0.10, 0.05, 0.03, 0.04]
        win_odds =   [3.0,  6.0,  8.0,  15.0, 10.0, 20.0, 30.0, 25.0]
        runner_ids = [1, 2, 3, 4, 5, 6, 7, 8]

        results = ValueBetDetector.detect(true_probs, win_odds, runner_ids)
        for r in results:
            assert 0 <= r.kelly_fraction <= 1, f"Kelly out of bounds for runner {r.runner_id}"


# ─────────────────────────────────────────────
#  Test 4: PaceForecaster
# ─────────────────────────────────────────────

class TestPaceForecaster:

    def test_slow_pace_with_few_front_runners(self):
        """前領馬少 → 慢步速"""
        runners = make_sample_runners()
        # 修改：只有 1 匹前領馬
        for r in runners:
            if r.runner_id != 1:
                r.running_style = "Closer"

        result = PaceForecaster.forecast_pace(runners)
        assert result["pace_scenario"] == "Slow"

    def test_fast_pace_with_many_front_runners(self):
        """前領馬多 → 快步速"""
        runners = make_sample_runners()
        # 修改：5 匹前領馬
        for i, r in enumerate(runners):
            if i < 5:
                r.running_style = "Front"

        result = PaceForecaster.forecast_pace(runners)
        assert result["pace_scenario"] == "Fast"

    def test_pace_advantage_for_closer_in_fast_pace(self):
        """快步速利後上馬"""
        runners = make_sample_runners()
        for i, r in enumerate(runners):
            if i < 5:
                r.running_style = "Front"
            else:
                r.running_style = "Closer"

        result = PaceForecaster.forecast_pace(runners)
        closer_ids = [r.runner_id for r in runners if r.running_style == "Closer"]
        front_ids = [r.runner_id for r in runners if r.running_style == "Front"]

        # 後上馬的步速優勢應高於前領馬
        for cid in closer_ids:
            for fid in front_ids:
                assert result["pace_advantage"][cid] > result["pace_advantage"][fid]


# ─────────────────────────────────────────────
#  Test 5: Full Orchestrator
# ─────────────────────────────────────────────

class TestOrchestrator:

    def test_full_analysis(self):
        """完整分析流程"""
        runners = make_sample_runners()
        win_odds = [3.5, 5.0, 8.0, 25.0, 3.0, 7.0, 40.0, 10.0]
        runner_ids = [r.runner_id for r in runners]

        orchestrator = QuantAnalysisOrchestrator()
        results = orchestrator.analyze_race(
            runners=runners,
            win_odds=win_odds,
            runner_ids=runner_ids,
        )

        # 結果數量正確
        assert len(results) == len(runners)

        # 所有 EV 都已計算
        for r in results:
            assert r.expected_value is not None
            assert r.true_probability > 0
            assert r.market_probability > 0
            assert r.kelly_fraction >= 0

        # 至少有一匹 +EV（在模擬場景中很可能）
        value_bets = [r for r in results if r.is_value_bet]
        print(f"\nValue Bets found: {len(value_bets)}")
        for vb in value_bets:
            print(f"  Runner {vb.runner_id}: "
                  f"P_true={vb.true_probability:.2%}, "
                  f"P_market={vb.market_probability:.2%}, "
                  f"EV={vb.expected_value:+.2%}, "
                  f"Kelly={vb.kelly_fraction:.2%}, "
                  f"Confidence={vb.confidence_level}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
