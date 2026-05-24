"""
HKJC Data Scraper — 香港賽馬會數據爬蟲

功能：
1. 抓取排位表（Race Card）
2. 抓取歷史賽績（Past Performance）
3. 抓取即時賠率（Live Odds）
4. 抓取分段時間（Sectional Times）

注意：
- HKJC 網站有反爬機制，需設置合理的 request 間隔
- 建議使用 HTTPX + 瀏覽器 User-Agent
- 即時賠率需在閘前 10 分鐘內高頻抓取（每 5 秒一次）
"""
import asyncio
import re
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

# HKJC 官方 URL
HKJC_BASE = "https://racing.hkjc.com"
HKJC_RACECARD = f"{HKJC_BASE}/racing/information/English/Racing/RaceCard"
HKJC_RESULTS = f"{HKJC_BASE}/racing/information/English/Racing/LocalResults"
HKJC_ODDS_WIN = f"{HKJC_BASE}/racing/information/English/Racing/OddsWin"
HKJC_SECTIONAL = f"{HKJC_BASE}/racing/information/English/Racing/SectionalTimes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}


@dataclass
class ScrapedRaceCard:
    """從排位表抓取的數據"""
    meeting_date: date
    venue: str
    race_number: int
    distance: int
    race_class: str
    course: str
    runners: List[Dict]


@dataclass
class ScrapedOdds:
    """即時賠率數據"""
    race_id: str
    timestamp: datetime
    win_odds: Dict[int, float]       # {horse_number: odds}
    win_pool: int
    place_odds: Dict[int, float]
    place_pool: int


class HKJCScraper:
    """香港賽馬會數據爬蟲"""

    def __init__(self, request_interval: float = 2.0):
        """
        Args:
            request_interval: 請求間隔（秒），預設 2 秒避免觸發反爬
        """
        self.interval = request_interval
        self.client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def _get(self, url: str, params: Optional[Dict] = None) -> str:
        """帶間隔的 GET 請求"""
        await asyncio.sleep(self.interval)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.text

    # ─────────────────────────────────────────────
    #  1. 排位表爬蟲
    # ─────────────────────────────────────────────

    async def scrape_racecard(
        self,
        race_date: Optional[date] = None,
    ) -> List[ScrapedRaceCard]:
        """
        抓取指定日期的排位表。

        HKJC 排位表 URL 結構：
        /racing/information/English/Racing/RaceCard?RaceDate=2025-01-15&RaceNo=1

        Returns:
            該日所有場次的排位表數據
        """
        if race_date is None:
            race_date = date.today()

        results = []
        # 先抓第一場，確定總場數
        html = await self._get(HKJC_RACECARD, params={
            "RaceDate": race_date.strftime("%Y-%m-%d"),
            "RaceNo": 1,
        })

        soup = BeautifulSoup(html, "lxml")

        # 解析場次數量
        total_races = self._parse_total_races(soup)

        for race_no in range(1, total_races + 1):
            if race_no > 1:
                html = await self._get(HKJC_RACECARD, params={
                    "RaceDate": race_date.strftime("%Y-%m-%d"),
                    "RaceNo": race_no,
                })
                soup = BeautifulSoup(html, "lxml")

            race_data = self._parse_racecard_page(soup, race_date, race_no)
            if race_data:
                results.append(race_data)

        return results

    def _parse_total_races(self, soup: BeautifulSoup) -> int:
        """解析總場數"""
        # HKJC 頁面通常有場次選擇器
        race_btns = soup.select(".race_btn, .racingNumber, [class*=raceNum]")
        if race_btns:
            return len(race_btns)
        # Fallback
        return 11  # 香港最多 11 場

    def _parse_racecard_page(
        self, soup: BeautifulSoup, race_date: date, race_no: int
    ) -> Optional[ScrapedRaceCard]:
        """解析單場排位表頁面"""
        try:
            # 解析賽事資訊
            venue = "STV"  # Default
            distance = 1200
            race_class = ""
            course = "A"

            # 解析出賽馬匹
            runners = []
            rows = soup.select("tr[class*=row], .raceCardRow, .horse_row")
            for row in rows:
                runner = self._parse_runner_row(row)
                if runner:
                    runners.append(runner)

            return ScrapedRaceCard(
                meeting_date=race_date,
                venue=venue,
                race_number=race_no,
                distance=distance,
                race_class=race_class,
                course=course,
                runners=runners,
            )
        except Exception as e:
            print(f"[Scraper] Error parsing racecard page: {e}")
            return None

    def _parse_runner_row(self, row) -> Optional[Dict]:
        """解析出賽馬匹行"""
        try:
            cells = row.find_all("td")
            if len(cells) < 5:
                return None
            return {
                "runner_number": int(cells[0].text.strip()) if cells[0].text.strip().isdigit() else 0,
                "horse_name": cells[1].text.strip() if len(cells) > 1 else "",
                "barrier": int(cells[2].text.strip()) if len(cells) > 2 and cells[2].text.strip().isdigit() else 0,
                "weight": 0,
                "jockey": cells[3].text.strip() if len(cells) > 3 else "",
                "trainer": cells[4].text.strip() if len(cells) > 4 else "",
            }
        except (ValueError, IndexError):
            return None

    # ─────────────────────────────────────────────
    #  2. 即時賠率爬蟲（高頻）
    # ─────────────────────────────────────────────

    async def scrape_live_odds(
        self,
        race_date: date,
        race_no: int,
    ) -> Optional[ScrapedOdds]:
        """
        抓取即時賠率（單次）。

        用法：在閘前 10 分鐘到 1 分鐘，每 5 秒調用一次。
        """
        html = await self._get(HKJC_ODDS_WIN, params={
            "RaceDate": race_date.strftime("%Y-%m-%d"),
            "RaceNo": race_no,
        })

        soup = BeautifulSoup(html, "lxml")
        return self._parse_odds_page(soup, race_date, race_no)

    def _parse_odds_page(
        self, soup: BeautifulSoup, race_date: date, race_no: int
    ) -> Optional[ScrapedOdds]:
        """解析賠率頁面"""
        try:
            win_odds = {}
            place_odds = {}
            win_pool = 0
            place_pool = 0

            # 嘗試從 JavaScript 變量中提取賠率
            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""
                if "winOdds" in text or "WinPool" in text:
                    # 解析 JS 中的賠率數據
                    odds_match = re.findall(r'"horseNo":(\d+),"winOdds":([\d.]+)', text)
                    for horse_no, odds_val in odds_match:
                        win_odds[int(horse_no)] = float(odds_val)

                    pool_match = re.search(r'"winPool":(\d+)', text)
                    if pool_match:
                        win_pool = int(pool_match.group(1))

            # Fallback：從 HTML 表格解析
            if not win_odds:
                odds_rows = soup.select("tr[class*=odd], .oddsRow")
                for row in odds_rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        try:
                            horse_no = int(cells[0].text.strip())
                            odds_val = float(cells[1].text.strip())
                            win_odds[horse_no] = odds_val
                        except ValueError:
                            continue

            return ScrapedOdds(
                race_id=f"{race_date.strftime('%Y%m%d')}_R{race_no}",
                timestamp=datetime.utcnow(),
                win_odds=win_odds,
                win_pool=win_pool,
                place_odds=place_odds,
                place_pool=place_pool,
            )
        except Exception as e:
            print(f"[Scraper] Error parsing odds: {e}")
            return None

    # ─────────────────────────────────────────────
    #  3. 歷史賽績爬蟲
    # ─────────────────────────────────────────────

    async def scrape_results(
        self,
        from_date: date,
        to_date: date,
    ) -> List[Dict]:
        """
        批量抓取歷史賽績。

        Args:
            from_date: 開始日期
            to_date: 結束日期
        """
        all_results = []
        current = from_date

        while current <= to_date:
            html = await self._get(HKJC_RESULTS, params={
                "RaceDate": current.strftime("%Y-%m-%d"),
            })

            soup = BeautifulSoup(html, "lxml")
            day_results = self._parse_results_page(soup, current)
            all_results.extend(day_results)

            current += timedelta(days=1)

        return all_results

    def _parse_results_page(self, soup: BeautifulSoup, race_date: date) -> List[Dict]:
        """解析賽果頁面"""
        results = []
        # 解析邏輯與排位表類似，需根據 HKJC 實際 HTML 結構調整
        return results

    # ─────────────────────────────────────────────
    #  4. 高頻賠率監控模式
    # ─────────────────────────────────────────────

    async def monitor_odds_before_start(
        self,
        race_date: date,
        race_no: int,
        duration_minutes: int = 10,
        interval_seconds: float = 5.0,
    ) -> List[ScrapedOdds]:
        """
        閘前高頻賠率監控。

        在開跑前 N 分鐘，每 M 秒抓取一次賠率，
        用於捕捉聰明錢（Smart Money）。

        Args:
            race_date: 賽事日期
            race_no: 場次
            duration_minutes: 監控時長（分鐘）
            interval_seconds: 抓取間隔（秒）
        """
        snapshots = []
        end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        original_interval = self.interval

        # 高頻模式：縮短間隔
        self.interval = interval_seconds

        try:
            while datetime.utcnow() < end_time:
                odds = await self.scrape_live_odds(race_date, race_no)
                if odds:
                    snapshots.append(odds)
                    print(f"[Odds Monitor] {odds.race_id} @ {odds.timestamp} - "
                          f"Pool: {odds.win_pool:,}")
        finally:
            self.interval = original_interval

        return snapshots
