"""
End-to-end test: Verify HKJC data fetching works.

Run: python -m pytest tests/test_hkjc_fetcher.py -v -s
"""
import pytest
from datetime import date

from app.scraper.hkjc_fetcher import (
    HKJCResultsParser,
    HKJCGraphQLClient,
    HKJCDataFetcher,
)


class TestResultsParser:
    """測試賽果 HTML 解析器"""

    @pytest.fixture
    def parser(self):
        return HKJCResultsParser()

    def test_fetch_and_parse_race_results(self, parser):
        """獲取並解析實際賽果頁面"""
        race_date = date(2026, 5, 17)
        result = parser.fetch_and_parse(race_date)

        assert result.meeting_date == race_date
        assert result.venue in ("STV", "HV"), f"Venue should be STV or HV, got {result.venue}"
        assert len(result.races) > 0, "Should have at least 1 race"

        # Check race metadata
        print(f"\nDate: {race_date}, Venue: {result.venue}")
        for race_no, meta in sorted(result.race_metadata.items()):
            print(f"  Race {race_no}: Class {meta['race_class']}, "
                  f"{meta['distance']}m, Going: {meta['going']}")

        # Check first race results
        first_race_no = min(result.races.keys())
        first_race = result.races[first_race_no]
        print(f"\n  Race {first_race_no} results ({len(first_race)} runners):")
        for r in first_race[:3]:
            print(f"    #{r.position}: {r.horse_name} ({r.brand_number}) "
                  f"J:{r.jockey_name} T:{r.trainer_name} "
                  f"Wt:{r.actual_weight} Dr:{r.barrier} "
                  f"LBW:{r.lbw} Time:{r.finish_time} Odds:{r.win_odds}")

        # Verify result structure
        for r in first_race:
            assert r.position >= 1, f"Position should be >= 1, got {r.position}"
            assert r.horse_name, "Horse name should not be empty"
            assert r.barrier >= 1, f"Barrier should be >= 1, got {r.barrier}"

    def test_parse_multiple_dates(self, parser):
        """測試批量獲取多天賽果"""
        results = parser.fetch_date_range(
            date(2026, 5, 15),
            date(2026, 5, 17),
        )
        print(f"\nFetched {len(results)} race days")
        for day in results:
            print(f"  {day.meeting_date}: {day.venue}, {len(day.races)} races")

    def test_non_race_day(self, parser):
        """非賽馬日應該返回空結果"""
        result = parser.fetch_and_parse(date(2026, 5, 18))  # Monday
        assert isinstance(result.races, dict)


class TestGraphQLClient:
    """測試 GraphQL 客戶端（基於 hkjc-api npm 包逆向的真實 query）"""

    @pytest.fixture
    def client(self):
        return HKJCGraphQLClient()

    def test_get_active_meetings(self, client):
        """獲取當前活躍賽事日"""
        result = client.get_active_meetings()
        assert result is not None, "Should return active meetings (not None)"
        assert len(result) > 0, "Should have at least 1 active meeting"
        # Verify structure
        for m in result:
            assert "venueCode" in m
            assert "date" in m
            assert "races" in m
        print(f"\nActive meetings: {len(result)}")
        for m in result:
            print(f"  {m['venueCode']} @ {m['date']} ({len(m['races'])} races)")

    def test_get_race_meetings_with_date(self, client):
        """獲取指定日期的賽事日詳情"""
        result = client.get_race_meetings(race_date="2026-05-24")
        assert result is not None, "Should return meetings"
        assert len(result) > 0
        meeting = result[0]
        assert "races" in meeting
        assert len(meeting["races"]) > 0
        print(f"\nMeeting: {meeting['venueCode']} @ {meeting['date']}, {len(meeting['races'])} races")

    def test_get_race_runners(self, client):
        """獲取出賽馬排位表"""
        runners = client.get_race_runners(race_date="2026-05-24", venue_code="ST")
        assert runners is not None
        assert len(runners) > 0
        race = runners[0]
        assert "runners" in race
        assert len(race["runners"]) > 0
        # Verify runner structure
        h = race["runners"][0]
        assert "name_en" in h
        assert "barrierDrawNumber" in h
        assert "handicapWeight" in h
        print(f"\nRace 1: {race['race_name_en']} {race['distance']}m")
        print(f"  First runner: {h['name_en']} Dr:{h['barrierDrawNumber']} Wt:{h['handicapWeight']}")

    def test_get_race_odds(self, client):
        """獲取賠率數據"""
        odds = client.get_race_odds(
            race_no=1,
            odds_types=["WIN", "PLA"],
            race_date="2026-05-24",
            venue_code="ST",
        )
        assert odds is not None
        assert len(odds) >= 2, "Should have WIN and PLA pools"
        # Find WIN pool
        win_pool = next((p for p in odds if p["oddsType"] == "WIN"), None)
        assert win_pool is not None, "Should have WIN pool"
        assert len(win_pool["oddsNodes"]) > 0, "Should have odds nodes"
        print(f"\nWIN pool: {len(win_pool['oddsNodes'])} entries")
        for node in win_pool["oddsNodes"][:3]:
            print(f"  #{node['combString']}: {node['oddsValue']}")

    def test_get_race_pools(self, client):
        """獲取彩池投注額"""
        pools = client.get_race_pools(
            race_no=1,
            odds_types=["WIN", "PLA"],
            race_date="2026-05-24",
            venue_code="ST",
        )
        assert pools is not None
        print(f"\nPool entries: {len(pools)}")
        for p in pools:
            print(f"  {p['oddsType']}: Invest={p.get('investment', 'N/A')}")


class TestDataFetcher:
    """測試統一數據獲取器"""

    @pytest.fixture
    def fetcher(self):
        return HKJCDataFetcher()

    def test_fetch_results(self, fetcher):
        """測試統一接口的賽果獲取"""
        result = fetcher.fetch_results(date(2026, 5, 17))
        assert result.venue in ("STV", "HV")
        assert len(result.races) > 0

    def test_fetch_live_odds(self, fetcher):
        """測試即時賠率獲取（GraphQL → HTML fallback）"""
        snapshot = fetcher.fetch_live_odds(date(2026, 5, 24), 1)
        # If no live race, odds may be empty but should not crash
        if snapshot:
            assert snapshot.race_number == 1
            print(f"\nLive odds: {len(snapshot.win_odds)} WIN, {len(snapshot.place_odds)} PLA")
        else:
            print("\nNo live odds available (expected outside race hours)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
