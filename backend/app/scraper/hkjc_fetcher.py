"""
HKJC Data Fetcher — 香港賽馬會數據獲取模組

數據管道策略（三層架構）：
1. HTML 解析器：解析 racing.hkjc.com 的賽果/排位表頁面（穩定、可用）
2. GraphQL API 客戶端：直接調用 info.cld.hkjc.com/graphql/base/（需從瀏覽器 DevTools 獲取 query）
3. 手動 CSV 導入：管理員後台上傳歷史數據

數據格式（從實際頁面解析確認）：
賽果表格列：Position | HorseNo | HorseName(Brand) | Jockey | Trainer | ActualWt | HorseWt | Draw | LBW | RunningPos | FinishTime | WinOdds
馬匹 ID 格式：HK_YYYY_BRAND (如 HK_2023_J182)
"""
import asyncio
import re
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import httpx
import random
import time
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
#  Constants & Headers
# ═══════════════════════════════════════════════

HKJC_BASE = "https://racing.hkjc.com"
RESULTS_URL = f"{HKJC_BASE}/racing/information/English/Racing/ResultsAll.aspx"
RACECARD_URL = f"{HKJC_BASE}/racing/information/English/Racing/RaceCard.aspx"
ODDS_URL = f"{HKJC_BASE}/racing/information/English/Racing/OddsWin.aspx"
SECTIONAL_URL = f"{HKJC_BASE}/racing/information/English/Racing/SectionalTimes.aspx"

GRAPHQL_URL = "https://info.cld.hkjc.com/graphql/base/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{HKJC_BASE}/racing/english/",
}

GRAPHQL_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Referer": f"{HKJC_BASE}/",
    "Origin": HKJC_BASE,
}


# ═══════════════════════════════════════════════
#  Anti-Block Utilities
# ═══════════════════════════════════════════════

def _human_delay(min_s: float = 0.8, max_s: float = 3.0):
    """隨機延遲，模擬人類瀏覽行為，避免固定間隔被 WAF 偵測"""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Anti-block delay: {delay:.2f}s")
    time.sleep(delay)


def _retry_request(func, max_retries: int = 3, backoff_base: float = 2.0):
    """
    帶指數退避的重試機制。
    如果被 Block（429/503），自動等待後重試。
    """
    for attempt in range(max_retries):
        try:
            return func()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503):
                wait = backoff_base ** attempt + random.uniform(0.5, 2.0)
                logger.warning(f"Rate limited ({e.response.status_code}), retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
            elif e.response.status_code == 403:
                logger.error(f"Blocked by WAF (403) — IP or fingerprint may be flagged")
                raise
            else:
                raise
    raise httpx.HTTPStatusError(f"Max retries ({max_retries}) exceeded", request=e.request, response=e.response)


# ═══════════════════════════════════════════════
#  Data Classes
# ═══════════════════════════════════════════════

@dataclass
class ParsedRaceResult:
    """從賽果頁面解析的單場賽果"""
    position: int
    horse_number: int
    horse_name: str
    brand_number: str        # 如 J182
    jockey_name: str
    trainer_name: str
    actual_weight: int       # 負磅（磅）
    horse_weight: int        # 馬匹體重
    barrier: int             # 檔位
    lbw: str                 # 與頭馬距離
    running_positions: List[int]  # 各段名次
    finish_time: str         # 完成時間
    win_odds: float          # 獨贏賠率


@dataclass
class ParsedRaceDay:
    """一天的所有賽果"""
    meeting_date: date
    venue: str               # STV / HV
    races: Dict[int, List[ParsedRaceResult]] = field(default_factory=dict)
    # race metadata per race number
    race_metadata: Dict[int, Dict] = field(default_factory=dict)


@dataclass
class ParsedOddsSnapshot:
    """即時賠率快照"""
    race_number: int
    timestamp: datetime
    win_odds: Dict[int, float]     # {horse_number: odds}
    win_pool: Optional[int] = None
    place_odds: Dict[int, float] = field(default_factory=dict)
    place_pool: Optional[int] = None


# ═══════════════════════════════════════════════
#  Layer 1: HTML Parser (賽果頁面)
# ═══════════════════════════════════════════════

class HKJCResultsParser:
    """
    解析 HKJC 賽果頁面 HTML。

    頁面結構（已驗證）：
    - 227KB HTML，包含當天所有場次結果
    - 表格列：Position | HorseNo | HorseName(Brand) | Jockey | Trainer |
              ActualWt | HorseWt | Draw | LBW | RunningPos | FinishTime | WinOdds
    - 馬匹名稱格式："HORSE NAME (J182)"
    - Running positions 用換行+空格分隔各段名次
    - 場次標題包含班次、路程、場地狀況
    """

    def __init__(self, request_interval: float = 2.0):
        self.interval = request_interval
        self.client = httpx.Client(
            headers=HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self):
        self.client.close()

    def fetch_results_page(self, race_date: date) -> str:
        """獲取賽果頁面 HTML（帶隨機延遲 + 重試）"""
        _human_delay(1.0, 3.0)  # HTML 頁面需要更長延遲
        date_str = race_date.strftime("%Y/%m/%d")

        def _do_fetch():
            resp = self.client.get(RESULTS_URL, params={"RaceDate": date_str})
            resp.raise_for_status()
            return resp

        resp = _retry_request(_do_fetch)
        return resp.text

    def parse_results(self, html: str, race_date: date) -> ParsedRaceDay:
        """解析賽果頁面，返回結構化數據"""
        result = ParsedRaceDay(meeting_date=race_date, venue="STV")

        # 1. 提取場地
        venue_match = re.findall(r"(Sha Tin|Happy Valley)", html)
        if "Happy Valley" in venue_match:
            result.venue = "HV"
        elif "Sha Tin" in venue_match:
            result.venue = "STV"

        # 2. 提取場次元數據（班次、路程、場地狀況）
        race_metas = re.finditer(
            r"RACE\s+(\d+).*?Class\s+(\d+)\s*-\s*(\d+)\s*M\s*-\s*\(([^)]+)\).*?"
            r"(GOOD(?:\s+TO\s+(?:YIELDING|SOFT))?|YIELDING(?:\s+TO\s+SOFT)?|SOFT|"
            r"SLOW|HEAVY|FIRM|FAST)",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        for m in race_metas:
            race_no = int(m.group(1))
            result.race_metadata[race_no] = {
                "race_class": int(m.group(2)),
                "distance": int(m.group(3)),
                "rating_range": m.group(4),
                "going": m.group(5).upper(),
            }

        # 3. 提取賽果行
        # 找到所有表格行，通過第一列是否為數字排名來判斷是否為賽果行
        row_matches = re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
        for match in row_matches:
            row_html = match.group(1)
            row_pos = match.start()  # 獲取行在 HTML 中的位置
            
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)
            if len(cells) < 7:  # 新頁面只有 7 列
                continue
            
            # 檢查第一列是不是數字排名（1, 2, 3...）
            first_cell = re.sub(r"<[^>]+>", "", cells[0]).strip()
            if not first_cell.isdigit():
                continue

            clean_cells = []
            for cell in cells:
                text = re.sub(r"<[^>]+>", "", cell).strip()
                text = text.replace("\xa0", " ").replace("&nbsp;", " ")
                # Normalize whitespace in running positions
                text = re.sub(r"\s+", " ", text).strip()
                clean_cells.append(text)

            try:
                parsed = self._parse_result_row(clean_cells)
                if parsed:
                    # 直接使用行的位置來計算場次
                    preceding = html[:row_pos]
                    race_markers = list(re.finditer(r"RACE\s+(\d+)", preceding, re.IGNORECASE))
                    if race_markers:
                        race_no = int(race_markers[-1].group(1))
                    else:
                        # Fallback：搜索 Class - Distance pattern
                        class_markers = list(re.finditer(r"Class\s+\d+\s*-\s*\d+\s*M", preceding))
                        race_no = len(class_markers) if class_markers else 1
                    
                    if race_no not in result.races:
                        result.races[race_no] = []
                    result.races[race_no].append(parsed)
            except (ValueError, IndexError) as e:
                # Skip malformed rows
                continue

        # 如果沒有從 Race headers 找到場次，嘗試從連續的行推斷
        if not result.race_metadata and result.races:
            self._infer_race_metadata(html, result)

        return result

    def _parse_result_row(self, cells: List[str]) -> Optional[ParsedRaceResult]:
        """解析單行賽果"""
        if len(cells) < 6:  # 新頁面只有 7 列，最少需要 6 列
            return None

        try:
            position = int(cells[0])
        except ValueError:
            return None

        try:
            horse_number = int(cells[1])
        except ValueError:
            return None

        # 解析馬名和烙印編號
        horse_name_raw = cells[2] if len(cells) > 2 else ""
        name_match = re.match(r"(.+?)\s*\(([A-Z]\d{3})\)", horse_name_raw)
        horse_name = name_match.group(1).strip() if name_match else horse_name_raw.strip()
        brand_number = name_match.group(2) if name_match else ""

        jockey_name = cells[3].strip() if len(cells) > 3 else ""
        trainer_name = cells[4].strip() if len(cells) > 4 else ""

        try:
            actual_weight = int(cells[5]) if len(cells) > 5 else 0
        except ValueError:
            actual_weight = 0

        try:
            barrier = int(cells[6]) if len(cells) > 6 else 0
        except ValueError:
            barrier = 0

        # 新頁面缺少以下列，使用默認值
        horse_weight = 0
        lbw = "---"
        running_positions = []
        finish_time = ""
        win_odds = 0.0

        return ParsedRaceResult(
            position=position,
            horse_number=horse_number,
            horse_name=horse_name,
            brand_number=brand_number,
            jockey_name=jockey_name,
            trainer_name=trainer_name,
            actual_weight=actual_weight,
            horse_weight=horse_weight,
            barrier=barrier,
            lbw=lbw,
            running_positions=running_positions,
            finish_time=finish_time,
            win_odds=win_odds,
        )

    def _current_race_no(
        self, html: str, row_html: str, race_metadata: Dict
    ) -> int:
        """根據行在頁面中的位置，推斷該行屬於哪個場次"""
        row_pos = html.find(row_html)
        if row_pos < 0:
            return 1

        # 向前搜索最近的 RACE N 標記
        preceding = html[:row_pos]
        race_markers = list(re.finditer(r"RACE\s+(\d+)", preceding, re.IGNORECASE))
        if race_markers:
            return int(race_markers[-1].group(1))

        # Fallback：搜索 Class - Distance pattern
        class_markers = list(re.finditer(r"Class\s+\d+\s*-\s*\d+\s*M", preceding))
        if class_markers:
            # Count how many race headers came before this row
            return len(class_markers)

        return 1

    def _infer_race_metadata(self, html: str, result: ParsedRaceDay):
        """從頁面推斷場次元數據"""
        # 提取所有 Class/Distance 段
        class_dist = re.findall(r"Class\s+(\d+)\s*-\s*(\d+)\s*M\s*-\s*\(([^)]+)\)", html)
        going_match = re.search(
            r"(GOOD(?:\s+TO\s+(?:YIELDING|SOFT))?|YIELDING|SOFT|SLOW|HEAVY)",
            html, re.IGNORECASE,
        )
        going = going_match.group(1).upper() if going_match else "GOOD"

        for i, (cls, dist, rating) in enumerate(class_dist, 1):
            result.race_metadata[i] = {
                "race_class": int(cls),
                "distance": int(dist),
                "rating_range": rating,
                "going": going,
            }

    def fetch_and_parse(self, race_date: date) -> ParsedRaceDay:
        """一步完成：獲取 + 解析"""
        html = self.fetch_results_page(race_date)
        return self.parse_results(html, race_date)

    def fetch_date_range(
        self, start: date, end: date
    ) -> List[ParsedRaceDay]:
        """批量獲取日期範圍內的賽果"""
        results = []
        current = start
        while current <= end:
            try:
                day_result = self.fetch_and_parse(current)
                if day_result.races:
                    results.append(day_result)
                    print(
                        f"[Results] {current} {day_result.venue}: "
                        f"{len(day_result.races)} races"
                    )
                else:
                    # No races on this day (not a race day)
                    pass
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    pass  # Not a race day
                else:
                    print(f"[Results] Error on {current}: {e}")
            except Exception as e:
                print(f"[Results] Error on {current}: {e}")

            current += timedelta(days=1)

        return results


# ═══════════════════════════════════════════════
#  Layer 2: GraphQL API Client
# ═══════════════════════════════════════════════

class HKJCGraphQLClient:
    """
    HKJC GraphQL API 客戶端（基於 hkjc-api npm 包逆向的 query 語句）。

    端點：https://info.cld.hkjc.com/graphql/base/
    來源：https://github.com/Bobosky2005/hkjc-api

    支援三類查詢：
    - raceMeetings：賽事日 + 排位表 + 出賽馬 + 彩池概覽
    - racing（odds）：獨贏/位置/QIN 等賠率詳細
    - racing（pools）：彩池投注額

    支援的賠率類型（OddsType enum）：
    WIN, PLA, QIN, QPL, CWA, CWB, CWC, IWN, FCT, TCE, TRI, FF, QTT, DBL, TBL, DT, TT, SixUP
    """

    # ── Query 1: 賽事日 + 排位表（含出賽馬完整資訊）──
    HORSE_RACE_MEETINGS_QUERY = """
    fragment raceFragment on Race {
        id no status raceName_en raceName_ch postTime
        country_en country_ch distance wageringFieldSize
        go_en go_ch ratingType
        raceTrack { description_en description_ch }
        raceCourse { description_en description_ch displayCode }
        claCode raceClass_en raceClass_ch
        judgeSigns { value_en }
    }
    fragment racingBlockFragment on RaceMeeting {
        jpEsts: pmPools(
            oddsTypes: [WIN, PLA, TCE, TRI, FF, QTT, DT, TT, SixUP]
            filters: ["jackpot", "estimatedDividend"]
        ) {
            leg { number races }
            oddsType jackpot estimatedDividend mergedPoolId
        }
        poolInvs: pmPools(
            oddsTypes: [WIN, PLA, QIN, QPL, CWA, CWB, CWC, IWN, FCT, TCE, TRI, FF, QTT, DBL, TBL, DT, TT, SixUP]
        ) {
            id leg { races }
        }
        penetrometerReadings(filters: ["first"]) { reading readingTime }
        hammerReadings(filters: ["first"]) { reading readingTime }
        changeHistories(filters: ["top3"]) {
            type time raceNo runnerNo
            horseName_ch horseName_en
            jockeyName_ch jockeyName_en
            scratchHorseName_ch scratchHorseName_en
            handicapWeight scrResvIndicator
        }
    }
    query raceMeetings($date: String, $venueCode: String) {
        timeOffset { rc }
        activeMeetings: raceMeetings {
            id venueCode date status
            races { no postTime status wageringFieldSize }
        }
        raceMeetings(date: $date, venueCode: $venueCode) {
            id status venueCode date totalNumberOfRace currentNumberOfRace
            dateOfWeek meetingType totalInvestment
            country { code namech nameen seq }
            races {
                ...raceFragment
                runners {
                    id no standbyNo status name_ch name_en
                    horse { id code }
                    color barrierDrawNumber handicapWeight currentWeight
                    currentRating internationalRating gearInfo
                    racingColorFileName allowance trainerPreference
                    last6run saddleClothNo trumpCard priority
                    finalPosition deadHeat winOdds
                    jockey { code name_en name_ch }
                    trainer { code name_en name_ch }
                }
            }
            obSt: pmPools(oddsTypes: [WIN, PLA]) {
                leg { races }
                oddsType comingleStatus
            }
            poolInvs: pmPools(
                oddsTypes: [WIN, PLA, QIN, QPL, CWA, CWB, CWC, IWN, FCT, TCE, TRI, FF, QTT, DBL, TBL, DT, TT, SixUP]
            ) {
                id leg { number races }
                status sellStatus oddsType investment mergedPoolId lastUpdateTime
            }
            ...racingBlockFragment
            pmPools(oddsTypes: []) { id }
            jkcInstNo: foPools(oddsTypes: [JKC], filters: ["top"]) { instNo }
            tncInstNo: foPools(oddsTypes: [TNC], filters: ["top"]) { instNo }
        }
    }
    """

    # ── Query 2: 賠率詳細（獨贏/位置/QIN 等）──
    HORSE_RACE_ODDS_QUERY = """
    query racing($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
        raceMeetings(date: $date, venueCode: $venueCode) {
            pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
                id status sellStatus oddsType lastUpdateTime
                guarantee minTicketCost name_en name_ch
                leg { number races }
                cWinSelections { composite name_ch name_en starters }
                oddsNodes {
                    combString oddsValue hotFavourite oddsDropValue
                    bankerOdds { combString oddsValue }
                }
            }
        }
    }
    """

    # ── Query 3: 彩池投注額 ──
    HORSE_RACE_POOL_QUERY = """
    query racing($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
        raceMeetings(date: $date, venueCode: $venueCode) {
            totalInvestment
            poolInvs: pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
                id leg { number races }
                status sellStatus oddsType investment mergedPoolId lastUpdateTime
            }
        }
    }
    """

    def __init__(self):
        self.client = httpx.Client(
            headers=GRAPHQL_HEADERS,
            timeout=15.0,
            follow_redirects=True,
        )

    def close(self):
        self.client.close()

    def execute_query(
        self, query: str, variables: Optional[Dict] = None
    ) -> Dict:
        """
        執行 GraphQL 查詢（帶隨機延遲 + 重試機制）。

        Args:
            query: GraphQL 查詢語句
            variables: 查詢變量

        Returns:
            API 返回的 JSON 數據

        Raises:
            ValueError: 如果查詢不匹配 schema
            httpx.HTTPError: 如果請求失敗
        """
        _human_delay(0.3, 1.5)  # 輕量延遲，避免連續請求觸發 WAF

        payload = {
            "query": query,
            "variables": variables or {},
        }

        def _do_request():
            resp = self.client.post(GRAPHQL_URL, json=payload)
            resp.raise_for_status()
            return resp

        resp = _retry_request(_do_request)
        data = resp.json()
        if "errors" in data:
            error_msgs = [e.get("message", "") for e in data["errors"]]
            raise ValueError(
                f"GraphQL query error: {'; '.join(error_msgs)}"
            )

        return data.get("data", {})

    def get_active_meetings(self) -> Optional[List[Dict]]:
        """獲取當前活躍的賽事日（無需日期參數）"""
        try:
            data = self.execute_query(self.HORSE_RACE_MEETINGS_QUERY)
            return data.get("activeMeetings", [])
        except (ValueError, httpx.HTTPError) as e:
            print(f"[GraphQL] get_active_meetings failed: {e}")
            return None

    def get_race_meetings(
        self, race_date: Optional[str] = None, venue_code: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        獲取賽事日詳情（含排位表、出賽馬、彩池）。

        Args:
            race_date: 日期字符串，如 "2026-05-24"
            venue_code: 場地代碼，如 "ST" 或 "HV"
        """
        try:
            variables = {}
            if race_date:
                variables["date"] = race_date
            if venue_code:
                variables["venueCode"] = venue_code

            data = self.execute_query(
                self.HORSE_RACE_MEETINGS_QUERY, variables=variables
            )
            return data.get("raceMeetings", [])
        except (ValueError, httpx.HTTPError) as e:
            print(f"[GraphQL] get_race_meetings failed: {e}")
            return None

    def get_race_runners(
        self, race_date: Optional[str] = None, venue_code: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        獲取出賽馬資訊（排位表），從 raceMeetings query 中提取。

        Returns:
            List of race dicts, each with runners list
        """
        meetings = self.get_race_meetings(race_date, venue_code)
        if not meetings:
            return None

        result = []
        for meeting in meetings:
            for race in meeting.get("races", []):
                result.append({
                    "race_no": race.get("no"),
                    "race_name_en": race.get("raceName_en"),
                    "race_name_ch": race.get("raceName_ch"),
                    "post_time": race.get("postTime"),
                    "distance": race.get("distance"),
                    "going_en": race.get("go_en"),
                    "going_ch": race.get("go_ch"),
                    "race_class_en": race.get("raceClass_en"),
                    "race_course": race.get("raceCourse", {}).get("displayCode"),
                    "runners": race.get("runners", []),
                })
        return result

    def get_race_odds(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        race_date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """
        獲取賠率詳細數據。

        Args:
            race_no: 場次號碼
            odds_types: 賠率類型列表，如 ["WIN", "PLA", "QIN"]
            race_date: 日期字符串
            venue_code: 場地代碼
        """
        try:
            variables = {"raceNo": race_no}
            if odds_types:
                variables["oddsTypes"] = odds_types
            else:
                variables["oddsTypes"] = ["WIN", "PLA"]
            if race_date:
                variables["date"] = race_date
            if venue_code:
                variables["venueCode"] = venue_code

            data = self.execute_query(
                self.HORSE_RACE_ODDS_QUERY, variables=variables
            )
            meetings = data.get("raceMeetings", [])
            if meetings:
                return meetings[0].get("pmPools", [])
            return []
        except (ValueError, httpx.HTTPError) as e:
            print(f"[GraphQL] get_race_odds failed: {e}")
            return None

    def get_race_pools(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        race_date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """
        獲取彩池投注額數據。

        Args:
            race_no: 場次號碼
            odds_types: 賠率類型列表
            race_date: 日期字符串
            venue_code: 場地代碼
        """
        try:
            variables = {"raceNo": race_no}
            if odds_types:
                variables["oddsTypes"] = odds_types
            else:
                variables["oddsTypes"] = ["WIN", "PLA"]
            if race_date:
                variables["date"] = race_date
            if venue_code:
                variables["venueCode"] = venue_code

            data = self.execute_query(
                self.HORSE_RACE_POOL_QUERY, variables=variables
            )
            meetings = data.get("raceMeetings", [])
            if meetings:
                return meetings[0].get("poolInvs", [])
            return []
        except (ValueError, httpx.HTTPError) as e:
            print(f"[GraphQL] get_race_pools failed: {e}")
            return None


# ═══════════════════════════════════════════════
#  Layer 3: Unified Data Fetcher
# ═══════════════════════════════════════════════

class HKJCDataFetcher:
    """
    統一數據獲取器 —— 結合 HTML 解析和 GraphQL API。

    策略：
    - 歷史賽果：使用 HTML 解析器（穩定可靠）
    - 即時賠率：優先使用 GraphQL，失敗則 fallback 到 HTML
    - 排位表：優先使用 GraphQL，失敗則 fallback 到 HTML
    """

    def __init__(self):
        self.results_parser = HKJCResultsParser()
        self.graphql_client = HKJCGraphQLClient()

    def close(self):
        self.results_parser.close()
        self.graphql_client.close()

    # ── 歷史賽果 ──

    def fetch_results(self, race_date: date) -> ParsedRaceDay:
        """獲取指定日期的賽果"""
        return self.results_parser.fetch_and_parse(race_date)

    def fetch_results_range(
        self, start: date, end: date
    ) -> List[ParsedRaceDay]:
        """批量獲取日期範圍內的賽果"""
        return self.results_parser.fetch_date_range(start, end)

    # ── 即時賠率 ──

    def fetch_live_odds(
        self, race_date: date, race_no: int,
        odds_types: Optional[List[str]] = None,
    ) -> Optional[ParsedOddsSnapshot]:
        """
        獲取即時賠率。

        優先使用 GraphQL API，失敗則解析 HTML 頁面。
        """
        # Try GraphQL first
        date_str = race_date.strftime("%Y-%m-%d")
        odds_data = self.graphql_client.get_race_odds(
            race_no=race_no,
            odds_types=odds_types or ["WIN", "PLA"],
            race_date=date_str,
        )
        if odds_data:
            return self._parse_graphql_odds(odds_data, race_no)

        # Fallback to HTML parsing
        return self._fetch_odds_from_html(race_date, race_no)

    def _parse_graphql_odds(
        self, pools: List[Dict], race_no: int
    ) -> ParsedOddsSnapshot:
        """
        解析 GraphQL 返回的賠率數據（pmPools → oddsNodes 格式）。

        pmPools 結構：
        [
            {
                "oddsType": "WIN",
                "oddsNodes": [
                    {"combString": "1", "oddsValue": "3.5", "hotFavourite": false, "oddsDropValue": null},
                    ...
                ]
            },
            {
                "oddsType": "PLA",
                "oddsNodes": [...]
            }
        ]
        """
        win_odds = {}
        place_odds = {}
        win_pool = None
        place_pool = None

        for pool in pools:
            odds_type = pool.get("oddsType", "")
            for node in pool.get("oddsNodes", []):
                comb = node.get("combString", "")
                odds_val = node.get("oddsValue", "")
                try:
                    horse_no = int(comb.split(",")[0].strip())
                    odds_float = float(odds_val) if odds_val else 0.0
                except (ValueError, IndexError):
                    continue

                if odds_type == "WIN":
                    win_odds[horse_no] = odds_float
                elif odds_type == "PLA":
                    place_odds[horse_no] = odds_float

            # Extract pool investment if available
            investment = pool.get("investment")
            if odds_type == "WIN" and investment:
                win_pool = int(float(investment))
            elif odds_type == "PLA" and investment:
                place_pool = int(float(investment))

        return ParsedOddsSnapshot(
            race_number=race_no,
            timestamp=datetime.utcnow(),
            win_odds=win_odds,
            win_pool=win_pool,
            place_odds=place_odds,
            place_pool=place_pool,
        )

    def _fetch_odds_from_html(
        self, race_date: date, race_no: int
    ) -> Optional[ParsedOddsSnapshot]:
        """從 HTML 頁面解析賠率（fallback）"""
        date_str = race_date.strftime("%Y/%m/%d")
        try:
            resp = self.results_parser.client.get(
                ODDS_URL,
                params={"RaceDate": date_str, "RaceNo": str(race_no)},
            )
            resp.raise_for_status()
            html = resp.text

            # Parse odds from HTML
            # This needs to be adapted based on actual page structure
            win_odds = {}
            odds_matches = re.findall(
                r'horseNo["\s:]+(\d+).*?winOdds["\s:]+([\d.]+)',
                html, re.IGNORECASE,
            )
            for horse_no, odds_val in odds_matches:
                win_odds[int(horse_no)] = float(odds_val)

            return ParsedOddsSnapshot(
                race_number=race_no,
                timestamp=datetime.utcnow(),
                win_odds=win_odds,
            )
        except Exception as e:
            print(f"[Odds HTML] Failed: {e}")
            return None

    # ── 賠率高頻監控 ──

    async def monitor_odds(
        self,
        race_date: date,
        race_no: int,
        interval_seconds: float = 5.0,
        duration_minutes: int = 10,
    ) -> List[ParsedOddsSnapshot]:
        """
        閘前高頻賠率監控（用於捕捉聰明錢）。

        在開跑前 N 分鐘，每 M 秒抓取一次賠率。
        """
        snapshots = []
        end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)

        while datetime.utcnow() < end_time:
            snapshot = self.fetch_live_odds(race_date, race_no)
            if snapshot:
                snapshots.append(snapshot)
                print(
                    f"[Odds Monitor] Race {race_no} @ {snapshot.timestamp} - "
                    f"Horses: {len(snapshot.win_odds)}"
                )
            await asyncio.sleep(interval_seconds)

        return snapshots


# ═══════════════════════════════════════════════
#  Utility: Discover available race dates
# ═══════════════════════════════════════════════

def discover_race_dates(start: date, end: date) -> List[date]:
    """
    探測日期範圍內哪些天有賽事。

    香港賽馬日通常是：
    - 沙田：週三或週六/日
    - 跑馬地：週三夜賽

    返回有賽果的日期列表。
    """
    fetcher = HKJCResultsParser()
    race_dates = []

    current = start
    while current <= end:
        try:
            result = fetcher.fetch_and_parse(current)
            if result.races:
                race_dates.append(current)
        except Exception:
            pass
        current += timedelta(days=1)

    fetcher.close()
    return race_dates
