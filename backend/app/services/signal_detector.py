"""
隱藏信號偵測器 —— 捕捉老手才懂的暗號

捕捉以下信號：
  1. 首次戴眼罩/遮眼帶 (First-time blinkers/visor)
  2. 裝備變更 (Gear change — 新增/移除裝備)
  3. 大幅減磅 (Significant weight drop ≥5 lbs)
  4. 騎師升級 (Top jockey on lower-class horse)
  5. 從化歸來 (Conghua return — detected by gear change + absence pattern)
  6. 檔位特殊優勢 (Barrier edge at specific venue/distance)
  7. 評分急跌但近績好 (Rating dropped but recent form competitive)
  8. Trump Card / Priority 雙重加持
  9. 賠率急跌 (Smart money — odds crashing)
  10. 讓磅優勢 (Apprentice allowance on competitive horse)
"""
from dataclasses import dataclass
from typing import List, Optional, Dict


# ═══════════════════════════════════════════════
#  Signal Data Classes
# ═══════════════════════════════════════════════

@dataclass
class HiddenSignal:
    """單個隱藏信號"""
    horse_no: int
    horse_name: str
    signal_type: str           # e.g. "first_blinkers", "weight_drop", "jockey_upgrade"
    severity: str              # "critical" / "high" / "medium" / "low"
    category: str              # "gear" / "weight" / "jockey" / "barrier" / "rating" / "smart_money" / "conghua"
    title_en: str              # Short title
    title_ch: str              # 中文標題
    description: str           # 詳細描述
    confidence: float          # 0.0 - 1.0，信心程度
    edge_boost: float          # 對 P_true 的預估加成（百分比點）


# ═══════════════════════════════════════════════
#  Known Patterns / Heuristics
# ═══════════════════════════════════════════════

# 香港賽馬裝備代碼對照
GEAR_CODES = {
    "B": {"en": "Blinkers", "ch": "眼罩"},
    "V": {"en": "Visor", "ch": "遮眼帶"},
    "TT": {"en": "Tongue Tie", "ch": "繫舌帶"},
    "CP": {"en": "Cross Noseband", "ch": "交叉鼻箍"},
    "XB": {"en": "Bit Lifter", "ch": "銜鐵提升器"},
    "H": {"en": "Hood", "ch": "頭罩"},
    "W": {"en": "Earmuffs", "ch": "耳罩"},
    "P": {"en": "Pacifiers", "ch": "拍籠"},
    "SO": {"en": "Shadow Roll", "ch": "遮光帶"},
    "BO": {"en": "Boots", "ch": "靴"},
    "B1": {"en": "Blinkers (1st time)", "ch": "首次戴眼罩"},
    "V1": {"en": "Visor (1st time)", "ch": "首次戴遮眼帶"},
    "TT1": {"en": "Tongue Tie (1st time)", "ch": "首次繫舌帶"},
    "CP1": {"en": "Cross Noseband (1st time)", "ch": "首次交叉鼻箍"},
    "H1": {"en": "Hood (1st time)", "ch": "首次戴頭罩"},
}

# 首次裝備信號（影響最大的裝備）
FIRST_TIME_GEARS = {"B1", "V1", "TT1", "H1", "CP1"}

# 跑馬地短途內檔優勢（距離 → 內檔範圍）
HV_BARRIER_ADVANTAGE = {
    1000: {"range": 6, "boost": 3.0, "desc": "跑馬地1000m內檔1-6檔優勢明顯"},
    1200: {"range": 5, "boost": 2.5, "desc": "跑馬地1200m內檔1-5檔有優勢"},
    1650: {"range": 4, "boost": 1.5, "desc": "跑馬地1650m內檔1-4檔微優"},
}

# 沙田草地內檔優勢
ST_BARRIER_ADVANTAGE = {
    1000: {"range": 3, "boost": 2.0, "desc": "沙田1000m內檔1-3檔有優勢"},
    1200: {"range": 4, "boost": 1.5, "desc": "沙田1200m內檔1-4檔微優"},
    1600: {"range": 3, "boost": 1.0, "desc": "沙田1600m內檔1-3檔微優"},
}

# 頂級騎師代碼（近年勝率 > 15%）
TOP_JOCKEYS = {
    "ZP": 0.22,    # 潘頓
    "MCJ": 0.20,   # 麥道朗
    "BH": 0.18,    # 布文
    "AA": 0.16,    # 艾兆禮
    "KTH": 0.15,   # 何澤堯 (approx)
    "JOM": 0.15,   # 奧爾民
    "YTE": 0.14,   # 田泰安
    "LFR": 0.14,   # 霍宏聲
}

# 從化訓練中心回來的裝備變更特徵
# 馬匹去從化訓練後常見：新增頭罩(H)、眼罩(B)、繫舌帶(TT)
CONGHUA_GEAR_PATTERN = {"H", "B", "TT", "V", "CP", "SO"}


# ═══════════════════════════════════════════════
#  Signal Detector
# ═══════════════════════════════════════════════

class HiddenSignalDetector:
    """
    隱藏信號偵測器 — 掃描每匹出賽馬，找出老手暗號。
    
    用法：
        detector = HiddenSignalDetector()
        signals = detector.detect(runner_data, race_context)
    """

    def detect(
        self,
        runners: List[Dict],
        race_context: Dict,
        odds_data: Optional[Dict] = None,
        jockey_today_stats: Optional[Dict[str, Dict]] = None,
    ) -> List[HiddenSignal]:
        """
        掃描所有出賽馬，返回偵測到的信號列表。
        
        Args:
            runners: 從 HKJC GraphQL 獲取的 runners 列表
            race_context: {venue_code, distance, race_class, going, race_course}
            odds_data: 可選的賠率數據 {win_odds_map, hot_fav_map, odds_drop_map}
            jockey_today_stats: 可選的騎師當日成績 {jockey_code: {wins: int, places: int, rides: int}}
        """
        signals = []
        venue = race_context.get("venue_code", "")
        distance = race_context.get("distance", 0)
        race_class = race_context.get("race_class", "")
        race_no = race_context.get("race_no", 0)
        total_runners = len(runners)

        for r in runners:
            no = self._int(r.get("no"))
            name = r.get("name_en", "")
            gear_info = r.get("gearInfo", "") or ""
            barrier = self._int(r.get("barrierDrawNumber"), 10)
            weight = self._int(r.get("handicapWeight"), 115)
            current_weight = self._int(r.get("currentWeight"), 0)
            last6 = r.get("last6run", "") or ""
            trump_card = r.get("trumpCard", False)
            priority = r.get("priority", False)
            allowance = r.get("allowance", "") or ""
            jockey = r.get("jockey", {})
            trainer = r.get("trainer", {})
            jockey_code = jockey.get("code", "")
            jockey_name = jockey.get("name_en", "")
            trainer_name = trainer.get("name_ch", "")

            # ── 1. 首次裝備信號 ──
            signals.extend(self._check_first_time_gear(no, name, gear_info))

            # ── 2. 裝備變更（新增裝備） ──
            signals.extend(self._check_gear_additions(no, name, gear_info))

            # ── 3. 從化歸來信號 ──
            signals.extend(self._check_conghua_return(no, name, gear_info, last6))

            # ── 4. 大幅減磅 ──
            signals.extend(self._check_weight_drop(no, name, weight, last6))

            # ── 5. 騎師升級 ──
            signals.extend(self._check_jockey_upgrade(no, name, jockey_code, jockey_name, race_class, weight))

            # ── 6. 檔位特殊優勢 ──
            signals.extend(self._check_barrier_edge(no, name, barrier, venue, distance, total_runners))

            # ── 7. 評分急跌但近績好 ──
            signals.extend(self._check_rating_form_mismatch(no, name, r, last6))

            # ── 8. Trump Card + Priority 雙重加持 ──
            signals.extend(self._check_trump_priority(no, name, trump_card, priority, trainer_name))

            # ── 9. 賠率急跌（聰明錢） ──
            if odds_data:
                signals.extend(self._check_odds_drop(no, name, odds_data))

            # ── 10. 見習騎師讓磅 ──
            signals.extend(self._check_apprentice_allowance(no, name, allowance, weight, last6))

            # ── 11. 當日火紅騎師 ──
            if jockey_today_stats:
                signals.extend(self._check_hot_jockey_today(no, name, jockey_code, jockey_name, jockey_today_stats, race_no))

            # ── 12. 穩膽（熱門馬高勝率但 EV 低） ──
            if odds_data:
                signals.extend(self._check_strong_contender(no, name, odds_data, last6))

            # ── 13. 檔位無影響（近績多次前四） ──
            signals.extend(self._check_barrier_versatile(no, name, barrier, last6, venue, distance))

            # ── 14. 超級馬王（如嘉應高昇） ──
            if odds_data:
                signals.extend(self._check_superhorse(no, name, barrier, weight, last6, odds_data, race_context))

        # 按嚴重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        signals.sort(key=lambda s: (severity_order.get(s.severity, 9), -s.confidence))

        return signals

    # ── 個別偵測方法 ──

    def _check_first_time_gear(self, no: int, name: str, gear_info: str) -> List[HiddenSignal]:
        """首次戴眼罩/遮眼帶等 — 最重要的裝備信號"""
        signals = []
        gears = self._parse_gears(gear_info)

        for g in gears:
            if g in FIRST_TIME_GEARS:
                info = GEAR_CODES.get(g, {"en": g, "ch": g})
                # 首次眼罩是最強信號
                if g == "B1":
                    severity = "critical"
                    confidence = 0.85
                    edge_boost = 5.0
                    desc = f"首次戴眼罩 — 歷史統計首戴眼罩勝率提升約8-12%"
                elif g == "V1":
                    severity = "high"
                    confidence = 0.75
                    edge_boost = 3.5
                    desc = f"首次戴遮眼帶 — 馬匹专注度通常提升"
                elif g == "TT1":
                    severity = "high"
                    confidence = 0.70
                    edge_boost = 3.0
                    desc = f"首次繫舌帶 — 改善呼吸，對喘氣馬效果顯著"
                elif g == "H1":
                    severity = "medium"
                    confidence = 0.60
                    edge_boost = 2.0
                    desc = f"首次戴頭罩 — 減少外界干擾"
                else:
                    severity = "medium"
                    confidence = 0.55
                    edge_boost = 1.5
                    desc = f"首次使用{info['ch']}"

                signals.append(HiddenSignal(
                    horse_no=no,
                    horse_name=name,
                    signal_type="first_time_gear",
                    severity=severity,
                    category="gear",
                    title_en=f"1st Time {info['en']}",
                    title_ch=f"{info['ch']}(首)",
                    description=desc,
                    confidence=confidence,
                    edge_boost=edge_boost,
                ))

        return signals

    def _check_gear_additions(self, no: int, name: str, gear_info: str) -> List[HiddenSignal]:
        """裝備變更（非首次，但新增了裝備）"""
        signals = []
        gears = self._parse_gears(gear_info)

        # 如果 gear_info 中有 "-" 結尾的代碼（表示移除），旁邊有新代碼就是變更
        # HKJC 格式: "CP-/XB-/B1/TT1" → CP- 表示移除了CP, B1 表示新增了B(首次)
        # "CP/TT1" → CP保留, TT1首次新增

        if "-" in gear_info:
            removed = [g.rstrip("-") for g in gears if g.endswith("-")]
            added = [g for g in gears if not g.endswith("-") and g not in FIRST_TIME_GEARS and g not in removed]

            for g in added:
                info = GEAR_CODES.get(g, {"en": g, "ch": g})
                signals.append(HiddenSignal(
                    horse_no=no,
                    horse_name=name,
                    signal_type="gear_change",
                    severity="medium",
                    category="gear",
                    title_en=f"Gear Added: {info['en']}",
                    title_ch=f"新增{info['ch']}",
                    description=f"新增{info['ch']}，移除了{','.join(removed)} — 裝備調整通常代表練馬師有針對性部署",
                    confidence=0.55,
                    edge_boost=1.5,
                ))

        return signals

    def _check_conghua_return(self, no: int, name: str, gear_info: str, last6: str) -> List[HiddenSignal]:
        """
        從化歸來信號 — 馬匹被送到從化訓練中心後回來，通常伴隨裝備變更和休養後復出。
        
        偵測邏輯：
        - 近6跑中有明顯的間歇（如只跑過2-3次，或近期成績突然下滑後休養）
        - 同時有裝備變更（頭罩、眼罩、繫舌帶等）
        - 這組合是老手熟知的「從化歸來」暗號
        """
        signals = []
        gears = self._parse_gears(gear_info)

        # 檢查是否有裝備變更（首次或新增）
        has_gear_change = any(g in FIRST_TIME_GEARS for g in gears) or "-" in gear_info

        # 檢查近績是否有「休息後復出」的模式
        # last6 格式: "6/7/4/9/7/11" — 如果前面有連續差成績然後近1-2場有好轉，或整體跑得少
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]
        
        has_rest_pattern = False
        rest_desc = ""
        
        if len(positions) <= 3:
            # 只跑過3場或更少 → 可能是從化休養後復出
            has_rest_pattern = True
            rest_desc = f"近6跑僅出賽{len(positions)}次 — 疑似從化休養後復出"
        elif len(positions) >= 4:
            # 近期成績突然下滑（前半段好，後半段差），然後可能休養回來
            early = positions[:len(positions)//2]
            late = positions[len(positions)//2:]
            early_avg = sum(early) / len(early) if early else 10
            late_avg = sum(late) / len(late) if late else 10
            if late_avg > early_avg + 3:
                has_rest_pattern = True
                rest_desc = f"近績下滑（前半均{early_avg:.1f}→後半均{late_avg:.1f}）後可能休養復出"

        if has_gear_change and has_rest_pattern:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="conghua_return",
                severity="high",
                category="conghua",
                title_en="Conghua Return",
                title_ch="從化歸來",
                description=f"🔍 從化歸來信號！{rest_desc}，同時有裝備變更 — 練馬師在從化做了針對性訓練，回來後常見脫胎換骨",
                confidence=0.70,
                edge_boost=4.0,
            ))
        elif has_gear_change and "-" in gear_info:
            # 有裝備移除+新增，即使沒有明顯休息模式也值得注意
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="gear_overhaul",
                severity="medium",
                category="conghua",
                title_en="Gear Overhaul",
                title_ch="裝備大改",
                description=f"裝備大幅調整（同時移除和新增） — 練馬師可能對此馬有特別部署",
                confidence=0.50,
                edge_boost=2.0,
            ))

        return signals

    def _check_weight_drop(self, no: int, name: str, weight: int, last6: str) -> List[HiddenSignal]:
        """
        大幅減磅 — 評分下調導致負磅減輕，如果近績尚可就是利好。
        
        注意：HKJC 的 handicapWeight 是本場負磅，不是與上場的對比。
        我們需要通過評分推斷 — 評分下降 = 減磅。
        但目前沒有歷史數據，只能做簡單推斷：
        - 低班馬（Class 4-5）負磅突然很低（<120），且近績有勝/位 → 減磅利好
        """
        signals = []
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]

        # 負磅輕 + 近績有入位 = 可能是減磅後的利好
        if weight <= 117 and positions:
            wins = sum(1 for p in positions if p == 1)
            places = sum(1 for p in positions if p <= 3)
            if wins > 0 or places >= 2:
                signals.append(HiddenSignal(
                    horse_no=no,
                    horse_name=name,
                    signal_type="light_weight_form",
                    severity="medium",
                    category="weight",
                    title_en="Light Weight + Form",
                    title_ch="輕磅好態",
                    description=f"負磅僅{weight}lbs，近{len(positions)}跑{wins}W{places-wins}P — 減磅後狀態維持，是利好信號",
                    confidence=0.55,
                    edge_boost=1.5,
                ))

        return signals

    def _check_jockey_upgrade(
        self, no: int, name: str, jockey_code: str, jockey_name: str, 
        race_class: str, weight: int
    ) -> List[HiddenSignal]:
        """
        騎師升級 — 頂級騎師降臨低班賽事或騎低評分馬，通常是練馬師主動邀約。
        """
        signals = []
        win_rate = TOP_JOCKEYS.get(jockey_code, 0)

        if win_rate >= 0.18:
            # 頂級騎師
            if "Class 4" in race_class or "Class 5" in race_class:
                severity = "high"
                edge_boost = 3.5
                desc = f"頂級騎師{jockey_name}(勝率{win_rate:.0%})降臨{race_class} — 練馬師主動邀約，必有文章"
            elif "Class 3" in race_class:
                severity = "medium"
                edge_boost = 2.0
                desc = f"頂級騎師{jockey_name}(勝率{win_rate:.0%})出戰{race_class}"
            else:
                severity = "low"
                edge_boost = 1.0
                desc = f"頂級騎師{jockey_name}(勝率{win_rate:.0%})出賽"

            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="jockey_upgrade",
                severity=severity,
                category="jockey",
                title_en="Top Jockey",
                title_ch=f"名將壓陣",
                description=desc,
                confidence=0.65 if severity == "high" else 0.50,
                edge_boost=edge_boost,
            ))

        return signals

    def _check_barrier_edge(
        self, no: int, name: str, barrier: int, venue: str, distance: int, total_runners: int
    ) -> List[HiddenSignal]:
        """
        檔位特殊優勢 — 在特定場地/距離，某些檔位有統計學上的顯著優勢。
        """
        signals = []

        # 跑馬地
        if venue == "HV":
            for dist, config in HV_BARRIER_ADVANTAGE.items():
                if distance <= dist + 50 and distance >= dist - 50:
                    if barrier <= config["range"]:
                        boost = config["boost"]
                        # 如果外檔馬很多，內檔優勢更大
                        if total_runners >= 12 and barrier <= 3:
                            boost += 1.0
                        signals.append(HiddenSignal(
                            horse_no=no,
                            horse_name=name,
                            signal_type="barrier_edge",
                            severity="high" if boost >= 3 else "medium",
                            category="barrier",
                            title_en=f"Barrier {barrier} Edge",
                            title_ch=f"{barrier}檔利",
                            description=f"跑馬地{distance}m {barrier}檔 — {config['desc']}，{total_runners}匹馬出賽令內檔更值錢",
                            confidence=0.65,
                            edge_boost=boost,
                        ))
                    elif barrier >= total_runners - 1 and total_runners >= 12:
                        # 外檔不利
                        signals.append(HiddenSignal(
                            horse_no=no,
                            horse_name=name,
                            signal_type="barrier_disadvantage",
                            severity="low",
                            category="barrier",
                            title_en=f"Barrier {barrier} Wide",
                            title_ch=f"{barrier}檔外檔",
                            description=f"跑馬地{distance}m 大外檔({barrier}檔) — 歷史勝率偏低",
                            confidence=0.55,
                            edge_boost=-1.5,
                        ))

        # 沙田
        elif venue == "ST":
            for dist, config in ST_BARRIER_ADVANTAGE.items():
                if distance <= dist + 50 and distance >= dist - 50:
                    if barrier <= config["range"]:
                        signals.append(HiddenSignal(
                            horse_no=no,
                            horse_name=name,
                            signal_type="barrier_edge",
                            severity="medium" if config["boost"] < 2 else "high",
                            category="barrier",
                            title_en=f"Barrier {barrier} Edge",
                            title_ch=f"{barrier}檔利",
                            description=f"沙田{distance}m {barrier}檔 — {config['desc']}",
                            confidence=0.55,
                            edge_boost=config["boost"],
                        ))

        return signals

    def _check_rating_form_mismatch(self, no: int, name: str, runner: Dict, last6: str) -> List[HiddenSignal]:
        """
        評分急跌但近績好 — 評分被下調但最近跑出好成績，說明馬匹狀態回升但評分尚未反映。
        """
        signals = []
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]

        if len(positions) < 2:
            return signals

        current_rating = self._int(runner.get("currentRating"), 0)
        international_rating = self._int(runner.get("internationalRating"), 0)

        # 如果有國際評分且明顯高於本地評分 → 評分可能被低估
        if international_rating > 0 and current_rating > 0:
            rating_diff = international_rating - current_rating
            if rating_diff >= 10:
                recent_best = min(positions[:3]) if len(positions) >= 3 else min(positions)
                if recent_best <= 3:
                    signals.append(HiddenSignal(
                        horse_no=no,
                        horse_name=name,
                        signal_type="rating_undervalued",
                        severity="high",
                        category="rating",
                        title_en="Rating Undervalued",
                        title_ch="評分偏低",
                        description=f"國際評分{international_rating}遠高於本地{current_rating}(差{rating_diff}分)，近績有入位 — 評分未反映實力",
                        confidence=0.65,
                        edge_boost=3.0,
                    ))

        # 近2跑突然好轉（之前差，最近2場入位）
        if len(positions) >= 4:
            early = positions[2:]
            recent = positions[:2]
            early_avg = sum(early) / len(early)
            recent_avg = sum(recent) / len(recent)
            if recent_avg < early_avg - 3 and min(recent) <= 3:
                signals.append(HiddenSignal(
                    horse_no=no,
                    horse_name=name,
                    signal_type="form_surge",
                    severity="medium",
                    category="rating",
                    title_en="Form Surge",
                    title_ch="態況急升",
                    description=f"近2跑均{recent_avg:.1f}遠優於之前均{early_avg:.1f}，且最近入位 — 狀態明顯回升",
                    confidence=0.55,
                    edge_boost=2.0,
                ))

        return signals

    def _check_trump_priority(
        self, no: int, name: str, trump_card: bool, priority: bool, trainer_name: str
    ) -> List[HiddenSignal]:
        """
        Trump Card + Priority 雙重加持 — HKJC 官方標記，表示練馬師對此馬有特別期望。
        """
        signals = []

        if trump_card and priority:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="trump_priority",
                severity="high",
                category="jockey",
                title_en="Trump + Priority",
                title_ch="皇牌+優先",
                description=f"🎯 練馬師{trainer_name}同時標記 Trump Card + Priority — 這是官方暗號，練馬師對此馬信心十足",
                confidence=0.70,
                edge_boost=3.5,
            ))
        elif trump_card:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="trump_card",
                severity="medium",
                category="jockey",
                title_en="Trump Card",
                title_ch="皇牌",
                description=f"Trump Card 標記 — 練馬師認為此馬有爭勝機會",
                confidence=0.55,
                edge_boost=1.5,
            ))

        return signals

    def _check_odds_drop(self, no: int, name: str, odds_data: Dict) -> List[HiddenSignal]:
        """
        賠率急跌 — 聰明錢流入，是最直接的市場信號。
        """
        signals = []
        odds_drop_map = odds_data.get("odds_drop_map", {})
        win_odds_map = odds_data.get("win_odds_map", {})

        if no in odds_drop_map:
            drop = odds_drop_map[no]
            current_odds = win_odds_map.get(no, 0)

            if drop >= 2.0:
                severity = "critical"
                confidence = 0.85
                edge_boost = 5.0
            elif drop >= 1.0:
                severity = "high"
                confidence = 0.75
                edge_boost = 3.5
            else:
                severity = "medium"
                confidence = 0.60
                edge_boost = 2.0

            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="odds_drop",
                severity=severity,
                category="smart_money",
                title_en=f"Odds Crash -{drop:.1f}",
                title_ch=f"賠率急跌 -{drop:.1f}",
                description=f"💰 聰明錢警報！賠率由{current_odds+drop:.1f}跌至{current_odds:.1f}(跌{drop:.1f}) — 大額資金流入",
                confidence=confidence,
                edge_boost=edge_boost,
            ))

        return signals

    def _check_apprentice_allowance(
        self, no: int, name: str, allowance: str, weight: int, last6: str
    ) -> List[HiddenSignal]:
        """
        見習騎師讓磅 — 如果見習騎師的讓磅（7-10 lbs）讓負磅變得很有競爭力，
        且近績有入位，這是利好信號。
        """
        signals = []
        
        # allowance 格式: "10" or "2 " or "  " (空格=無讓磅)
        allowance_val = 0
        try:
            allowance_val = int(allowance.strip())
        except (ValueError, AttributeError):
            return signals

        if allowance_val >= 7:
            effective_weight = weight - allowance_val
            positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]
            places = sum(1 for p in positions if p <= 3) if positions else 0

            if places >= 2:
                signals.append(HiddenSignal(
                    horse_no=no,
                    horse_name=name,
                    signal_type="apprentice_allowance",
                    severity="medium",
                    category="weight",
                    title_en=f"Apprentice -{allowance_val}lbs",
                    title_ch=f"見習讓{allowance_val}磅",
                    description=f"見習騎師讓磅{allowance_val}lbs，實際負磅僅{effective_weight}lbs，近{len(positions)}跑{places}次入位 — 讓磅優勢明顯",
                    confidence=0.50,
                    edge_boost=2.0,
                ))

        return signals

    def _check_hot_jockey_today(
        self, no: int, name: str, jockey_code: str, jockey_name: str,
        jockey_today_stats: Dict[str, Dict], current_race_no: int,
    ) -> List[HiddenSignal]:
        """
        當日火紅騎師 — 如果騎師在今日頭幾場已經勝出或連續入位，
        表示他今日狀態大好，後續策騎的馬也值得關注。
        
        偵測邏輯：
        - 今日已勝出 ≥2 場 → critical（超級火紅）
        - 今日已勝出 1 場 + 有入位 → high
        - 今日連續入位 ≥2（無勝出） → medium
        """
        signals = []
        stats = jockey_today_stats.get(jockey_code)
        if not stats:
            return signals

        wins = stats.get("wins", 0)
        places = stats.get("places", 0)
        rides = stats.get("rides", 0)

        # 至少要策騎過 2 場才有意義
        if rides < 2:
            return signals

        # 計算入位率
        place_rate = places / rides if rides > 0 else 0

        if wins >= 2:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="hot_jockey_today",
                severity="critical",
                category="jockey",
                title_en=f"🔥 {jockey_name} {wins}W{places-wins}P",
                title_ch=f"🔥{jockey_name}{wins}W{places}P",
                description=f"🔥 騎師{jockey_name}今日大爆發！{rides}騎{wins}W{places}P — 手風極順，後續策騎的馬值得重點關注",
                confidence=0.80,
                edge_boost=5.0,
            ))
        elif wins >= 1 and places >= 2:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="hot_jockey_today",
                severity="high",
                category="jockey",
                title_en=f"🔥 {jockey_name} {wins}W{places-wins}P",
                title_ch=f"🔥{jockey_name}{wins}W{places}P",
                description=f"🔥 騎師{jockey_name}今日狀態好！{rides}騎{wins}W{places}P — 手風正順",
                confidence=0.70,
                edge_boost=3.5,
            ))
        elif wins >= 1:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="hot_jockey_today",
                severity="medium",
                category="jockey",
                title_en=f"🔥 {jockey_name} {wins}W",
                title_ch=f"🔥{jockey_name}已勝",
                description=f"騎師{jockey_name}今日{rides}騎已取1W — 已開齋，信心正旺",
                confidence=0.55,
                edge_boost=2.0,
            ))
        elif places >= 2 and place_rate >= 0.5:
            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="hot_jockey_today",
                severity="medium",
                category="jockey",
                title_en=f"🔥 {jockey_name} 0W{places}P",
                title_ch=f"🔥{jockey_name}連位",
                description=f"騎師{jockey_name}今日{rides}騎{places}次入位（入位率{place_rate:.0%}）— 雖未取勝但頻頻入位，距離贏馬不遠",
                confidence=0.50,
                edge_boost=1.5,
            ))

        return signals

    def _check_strong_contender(
        self, no: int, name: str, odds_data: Dict, last6: str
    ) -> List[HiddenSignal]:
        """
        穩膽 — 熱門馬勝率很高，但賠率太低導致 EV 為負。
        這不代表是壞選擇，只是「沒有價值」而非「沒有勝率」。
        應該標記出來，提醒用戶：這馬很可能是冠軍，只是不值得下重注。
        """
        signals = []
        win_odds_map = odds_data.get("win_odds_map", {})
        odds = win_odds_map.get(no, 999)

        if odds > 5:
            return signals  # 只標記賠率 ≤5 的熱門馬

        p_market = 1 / odds if odds > 0 else 0
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]
        top4_count = sum(1 for p in positions if p <= 4) if positions else 0
        total_runs = len(positions) if positions else 0

        # 條件：市場隱含勝率 > 20% 且近績有支持
        if p_market >= 0.20 and total_runs >= 2:
            # 近績前四比例
            top4_rate = top4_count / total_runs if total_runs > 0 else 0

            if top4_rate >= 0.6 and total_runs >= 4:
                severity = "high"
                confidence = 0.80
                desc_suffix = f"，近{total_runs}跑{top4_count}次前四 — 實力毋庸置疑"
            elif top4_rate >= 0.5:
                severity = "medium"
                confidence = 0.65
                desc_suffix = f"，近{total_runs}跑{top4_count}次前四 — 勝率有保證"
            else:
                # 近績不夠強，但市場看好
                severity = "low"
                confidence = 0.50
                desc_suffix = "，市場看好但近績一般 — 信市場"

            signals.append(HiddenSignal(
                horse_no=no,
                horse_name=name,
                signal_type="strong_contender",
                severity=severity,
                category="reliability",
                title_en=f"Banker @ {odds:.1f}",
                title_ch=f"🏆穩膽{odds:.1f}倍",
                description=f"🏆 穩膽！賠率{odds:.1f}倍（市場勝率{p_market:.0%}）{desc_suffix}。EV 可能為負但勝率極高，適合膽拖/串關",
                confidence=confidence,
                edge_boost=0.5,  # 穩膽不影響 EV 計算，只是標記
            ))

        return signals

    def _check_superhorse(
        self, no: int, name: str, barrier: int, weight: int,
        last6: str, odds_data: Dict, race_context: Dict
    ) -> List[HiddenSignal]:
        """
        超級馬王 — 近績極度出色的馬匹，如「嘉應高昇」。
        這類馬匹超越正常分析框架——檔位、負磅、步速都影響有限。
        判定：近6跑≥5冠且賠率<2.5，或近4跑全冠且賠率<3.0。
        """
        signals = []
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]
        win_odds_map = odds_data.get("win_odds_map", {})
        odds = win_odds_map.get(no, 999)

        if len(positions) < 4 or odds > 3.0:
            return signals

        win_count = sum(1 for p in positions if p == 1)
        total_runs = len(positions)

        is_super = False
        if (total_runs >= 5 and win_count >= 5) or (total_runs >= 6 and win_count >= 5):
            if odds < 2.5:
                is_super = True
        if len(positions) >= 4 and all(p == 1 for p in positions[:4]) and odds < 3.0:
            is_super = True

        if not is_super:
            return signals

        # 超級馬王的特殊說明
        venue = race_context.get("venue_code", "")
        distance = race_context.get("distance", 0)
        barrier_note = ""
        if barrier >= 10:
            barrier_note = f"，當前{barrier}檔外檔出擊但對此馬毫無影響"
        weight_note = ""
        if weight >= 130:
            weight_note = f"，負{weight}磅頂磅仍可輕取對手"

        desc = f"👑 超級馬王！近{total_runs}跑{win_count}冠"
        if barrier_note:
            desc += barrier_note
        if weight_note:
            desc += weight_note
        desc += f"，賠率{odds:.1f}倍 — 此馬超越正常分析框架"

        signals.append(HiddenSignal(
            horse_no=no,
            horse_name=name,
            signal_type="superhorse",
            severity="critical",
            category="reliability",
            title_en=f"Superhorse ({win_count}/{total_runs} Wins)",
            title_ch=f"👑超級馬王({win_count}/{total_runs}冠)",
            description=desc,
            confidence=0.95,
            edge_boost=1.0,  # 超級馬王不影響 EV 計算，只是標記
        ))

        return signals

    def _check_barrier_versatile(
        self, no: int, name: str, barrier: int, last6: str,
        venue: str, distance: int
    ) -> List[HiddenSignal]:
        """
        檔位無影響 — 近績多次入前四，證明這匹馬在不同檔位都能跑。
        如果當前處於外檔劣勢，但馬匹歷史證明檔位對其影響小，
        則外檔劣勢可被部分抵消。
        """
        signals = []
        positions = [int(p) for p in last6.split("/") if p.strip().isdigit()]

        if len(positions) < 4:
            return signals  # 至少4跑才有意義

        top4_count = sum(1 for p in positions if p <= 4)
        total_runs = len(positions)
        top4_rate = top4_count / total_runs

        # 近4跑全部前四 → 強信號
        all_top4_recent4 = len(positions) >= 4 and all(p <= 4 for p in positions[:4])
        # 近6跑 ≥5 次前四 → 強信號
        mostly_top4 = total_runs >= 5 and top4_count >= 5
        # 近5跑 ≥4 次前四 → 中等信號
        frequent_top4 = total_runs >= 5 and top4_count >= 4

        is_versatile = all_top4_recent4 or mostly_top4 or (frequent_top4 and top4_rate >= 0.7)

        if not is_versatile:
            return signals

        # 判斷當前是否處於外檔劣勢
        is_wide = False
        barrier_note = ""
        if venue == "HV":
            if distance <= 1200 and barrier >= 10:
                is_wide = True
                barrier_note = f"，當前{barrier}檔屬外檔劣勢但可被抵消"
            elif distance <= 1650 and barrier >= 11:
                is_wide = True
                barrier_note = f"，當前{barrier}檔偏外但歷史證明影響不大"
        elif venue == "ST":
            if distance <= 1200 and barrier >= 10:
                is_wide = True
                barrier_note = f"，當前{barrier}檔屬外檔但此馬不受影響"
            elif distance <= 1600 and barrier >= 12:
                is_wide = True
                barrier_note = f"，當前{barrier}檔偏外但歷史證明影響不大"

        if all_top4_recent4:
            severity = "high"
            confidence = 0.80
            edge_boost = 2.5
            desc_core = f"近4跑全部前四 — 檔位對此馬幾乎無影響"
        elif mostly_top4:
            severity = "high"
            confidence = 0.75
            edge_boost = 2.0
            desc_core = f"近{total_runs}跑{top4_count}次前四 — 不同檔位都能跑"
        else:
            severity = "medium"
            confidence = 0.60
            edge_boost = 1.5
            desc_core = f"近{total_runs}跑{top4_count}次前四 — 檔位影響有限"

        signals.append(HiddenSignal(
            horse_no=no,
            horse_name=name,
            signal_type="barrier_versatile",
            severity=severity,
            category="barrier",
            title_en=f"Barrier-Proof ({top4_count}/{total_runs} T4)",
            title_ch=f"🔓檔位無影響({top4_count}/{total_runs}前四)",
            description=f"🔓 {desc_core}{barrier_note}",
            confidence=confidence,
            edge_boost=edge_boost,
        ))

        return signals

    # ── Utility ──

    def _parse_gears(self, gear_info: str) -> List[str]:
        """解析 HKJC 裝備字串，如 'CP-/XB-/B1/TT1' → ['CP-', 'XB-', 'B1', 'TT1']"""
        if not gear_info:
            return []
        return [g.strip() for g in gear_info.split("/") if g.strip()]

    @staticmethod
    def _int(val, default=0) -> int:
        if val is None or val == '':
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
