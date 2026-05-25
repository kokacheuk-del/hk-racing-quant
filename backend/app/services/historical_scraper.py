"""
Historical Data Scraper - 抓取並存儲歷史賽事數據
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, insert, update

from app.scraper.hkjc_fetcher import HKJCResultsParser
from app.services.data_provider import get_provider

logger = logging.getLogger(__name__)


class HistoricalDataScraper:
    """歷史數據爬蟲"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.results_parser = HKJCResultsParser()
        self.provider = get_provider()

    async def scrape_date(self, scrape_date: date) -> Dict[str, Any]:
        """
        抓取指定日期的所有賽事數據
        返回：統計信息
        """
        logger.info(f"Starting scrape for {scrape_date}")
        start_time = datetime.now()

        stats = {
            'date': scrape_date.isoformat(),
            'meetings': 0,
            'races': 0,
            'runners': 0,
            'status': 'success',
            'error': None
        }

        try:
            # 1. 獲取賽事列表
            meetings = self.provider.get_race_meetings(race_date=scrape_date.isoformat())
            
            if not meetings:
                logger.warning(f"No meetings found for {scrape_date}")
                stats['status'] = 'no_data'
                return stats

            stats['meetings'] = len(meetings)

            for meeting in meetings:
                # 2. 創建/更新賽事日程
                meeting_id = await self._upsert_meeting(scrape_date, meeting)
                
                # 3. 獲取賽果數據
                results = self.results_parser.fetch_and_parse(scrape_date)
                
                # 4. 處理每場賽事
                for race in meeting.get('races', []):
                    race_no = race.get('no')
                    if not race_no:
                        continue
                    
                    # 獲取該場賽事的賽果
                    race_results = results.races.get(str(race_no), [])
                    
                    # 創建/更新賽事記錄
                    race_id = await self._upsert_race(meeting_id, race, results)
                    
                    # 處理參賽馬匹
                    for runner in race.get('runners', []):
                        runner_id = await self._upsert_runner(race_id, runner, race_results)
                        if runner_id:
                            stats['runners'] += 1
                    
                    stats['races'] += 1

            # 記錄日誌
            duration = (datetime.now() - start_time).total_seconds()
            await self._log_scrape(scrape_date, stats, duration)

            logger.info(f"Scrape completed: {stats['races']} races, {stats['runners']} runners in {duration:.1f}s")

        except Exception as e:
            logger.error(f"Scrape failed for {scrape_date}: {e}", exc_info=True)
            stats['status'] = 'failed'
            stats['error'] = str(e)
            await self._log_scrape(scrape_date, stats, 0)

        return stats

    async def _upsert_meeting(self, meeting_date: date, meeting: Dict) -> int:
        """創建或更新賽事日程"""
        venue_code = meeting.get('venueCode', '')
        
        # 檢查是否已存在
        result = await self.db.execute(
            text("SELECT id FROM race_meetings WHERE meeting_date = :date"),
            {'date': meeting_date}
        )
        existing = result.fetchone()

        meeting_data = {
            'meeting_date': meeting_date,
            'venue_code': venue_code,
            'venue_name_en': meeting.get('venueName', ''),
            'venue_name_ch': '',
            'total_races': len(meeting.get('races', [])),
            'status': 'completed' if meeting.get('status') == 'resulted' else 'scheduled',
        }

        if existing:
            # 更新
            await self.db.execute(
                text("""
                    UPDATE race_meetings 
                    SET venue_code = :venue_code,
                        venue_name_en = :venue_name_en,
                        total_races = :total_races,
                        status = :status,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {'id': existing[0], **meeting_data}
            )
            meeting_id = existing[0]
        else:
            # 插入
            result = await self.db.execute(
                text("""
                    INSERT INTO race_meetings 
                    (meeting_date, venue_code, venue_name_en, venue_name_ch, total_races, status)
                    VALUES (:meeting_date, :venue_code, :venue_name_en, :venue_name_ch, :total_races, :status)
                    RETURNING id
                """),
                meeting_data
            )
            meeting_id = result.fetchone()[0]

        await self.db.commit()
        return meeting_id

    async def _upsert_race(self, meeting_id: int, race: Dict, results: Any) -> int:
        """創建或更新單場賽事"""
        race_no = race.get('no')
        
        # 從賽果中獲取額外信息
        race_meta = results.race_metadata.get(str(race_no), {}) if hasattr(results, 'race_metadata') else {}

        # 檢查是否已存在
        result = await self.db.execute(
            text("SELECT id FROM races WHERE meeting_id = :mid AND race_no = :rno"),
            {'mid': meeting_id, 'rno': race_no}
        )
        existing = result.fetchone()

        race_data = {
            'meeting_id': meeting_id,
            'race_no': race_no,
            'race_name_en': race.get('nameEn', ''),
            'race_name_ch': race.get('nameCh', ''),
            'race_class': race_meta.get('race_class', ''),
            'distance': race.get('distance', 0),
            'going': race_meta.get('going', ''),
            'track': 'TURF',
            'prize_money': race.get('prize', 0),
            'status': 'completed' if race.get('status') == 'resulted' else 'pending',
            'result_time': '',
        }

        if existing:
            await self.db.execute(
                text("""
                    UPDATE races SET
                        race_name_en = :race_name_en,
                        race_name_ch = :race_name_ch,
                        race_class = :race_class,
                        distance = :distance,
                        going = :going,
                        track = :track,
                        prize_money = :prize_money,
                        status = :status,
                        result_time = :result_time,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {'id': existing[0], **race_data}
            )
            race_id = existing[0]
        else:
            result = await self.db.execute(
                text("""
                    INSERT INTO races 
                    (meeting_id, race_no, race_name_en, race_name_ch, race_class, distance, 
                     going, track, prize_money, status, result_time)
                    VALUES (:meeting_id, :race_no, :race_name_en, :race_name_ch, :race_class, :distance,
                            :going, :track, :prize_money, :status, :result_time)
                    RETURNING id
                """),
                race_data
            )
            race_id = result.fetchone()[0]

        await self.db.commit()
        return race_id

    async def _upsert_runner(self, race_id: int, runner: Dict, race_results: List) -> Optional[int]:
        """創建或更新參賽馬匹"""
        horse_no = runner.get('no')
        if not horse_no:
            return None

        # 從賽果中找對應的馬
        result_data = None
        for r in race_results:
            if hasattr(r, 'horse_number') and r.horse_number == horse_no:
                result_data = r
                break

        # 先處理馬匹基本信息
        horse_id = await self._get_or_create_horse(runner)

        # 獲取模型計算結果
        win_odds = runner.get('winOdds', {}).get('current', 0)
        model_prob = runner.get('model', {}).get('winProb', 0)
        market_prob = 1 / win_odds if win_odds > 0 else 0
        ev_value = (model_prob * win_odds) - 1 if win_odds > 0 else 0
        is_value_bet = ev_value > 0 and model_prob > 0.02

        # 檢查是否已存在
        result = await self.db.execute(
            text("SELECT id FROM race_runners WHERE race_id = :rid AND horse_no = :hno"),
            {'rid': race_id, 'hno': horse_no}
        )
        existing = result.fetchone()

        runner_data = {
            'race_id': race_id,
            'horse_id': horse_id,
            'horse_no': horse_no,
            'barrier': runner.get('draw', 0),
            'jockey_code': runner.get('jockey', {}).get('code', ''),
            'jockey_name_en': runner.get('jockey', {}).get('nameEn', ''),
            'jockey_name_ch': '',
            'trainer_code': runner.get('trainer', {}).get('code', ''),
            'trainer_name_en': runner.get('trainer', {}).get('nameEn', ''),
            'trainer_name_ch': '',
            'actual_weight': runner.get('actualWt', 0),
            'declared_horse_weight': runner.get('declaredHorseWt', 0),
            'rating': runner.get('currentRating', 0),
            'last_6_runs': '',
            'final_position': result_data.position if result_data else 0,
            'finish_time': result_data.finish_time if result_data else '',
            'length_behind': 0,
            'win_odds': win_odds,
            'model_probability': model_prob,
            'market_probability': market_prob,
            'ev_value': ev_value,
            'kelly_fraction': ev_value / win_odds if win_odds > 0 and ev_value > 0 else 0,
            'is_value_bet': is_value_bet,
        }

        if existing:
            await self.db.execute(
                text("""
                    UPDATE race_runners SET
                        horse_id = :horse_id,
                        barrier = :barrier,
                        jockey_code = :jockey_code,
                        jockey_name_en = :jockey_name_en,
                        trainer_code = :trainer_code,
                        trainer_name_en = :trainer_name_en,
                        actual_weight = :actual_weight,
                        declared_horse_weight = :declared_horse_weight,
                        rating = :rating,
                        final_position = :final_position,
                        win_odds = :win_odds,
                        model_probability = :model_probability,
                        market_probability = :market_probability,
                        ev_value = :ev_value,
                        kelly_fraction = :kelly_fraction,
                        is_value_bet = :is_value_bet,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {'id': existing[0], **runner_data}
            )
            runner_id = existing[0]
        else:
            result = await self.db.execute(
                text("""
                    INSERT INTO race_runners 
                    (race_id, horse_id, horse_no, barrier, jockey_code, jockey_name_en, jockey_name_ch,
                     trainer_code, trainer_name_en, trainer_name_ch, actual_weight, declared_horse_weight,
                     rating, last_6_runs, final_position, finish_time, length_behind, win_odds,
                     model_probability, market_probability, ev_value, kelly_fraction, is_value_bet)
                    VALUES (:race_id, :horse_id, :horse_no, :barrier, :jockey_code, :jockey_name_en, :jockey_name_ch,
                            :trainer_code, :trainer_name_en, :trainer_name_ch, :actual_weight, :declared_horse_weight,
                            :rating, :last_6_runs, :final_position, :finish_time, :length_behind, :win_odds,
                            :model_probability, :market_probability, :ev_value, :kelly_fraction, :is_value_bet)
                    RETURNING id
                """),
                runner_data
            )
            runner_id = result.fetchone()[0]

        await self.db.commit()
        return runner_id

    async def _get_or_create_horse(self, runner: Dict) -> int:
        """獲取或創建馬匹記錄"""
        horse_name = runner.get('nameEn', '')
        if not horse_name:
            return 0

        # 嘗試按名稱查找
        result = await self.db.execute(
            text("SELECT id FROM horses WHERE horse_name_en = :name"),
            {'name': horse_name}
        )
        existing = result.fetchone()

        if existing:
            return existing[0]

        # 創建新馬匹
        result = await self.db.execute(
            text("""
                INSERT INTO horses (horse_code, horse_name_en, horse_name_ch)
                VALUES (:code, :name_en, :name_ch)
                RETURNING id
            """),
            {
                'code': runner.get('code', ''),
                'name_en': horse_name,
                'name_ch': runner.get('nameCh', ''),
            }
        )
        horse_id = result.fetchone()[0]
        await self.db.commit()
        return horse_id

    async def _log_scrape(self, scrape_date: date, stats: Dict, duration: float):
        """記錄爬蟲日誌"""
        await self.db.execute(
            text("""
                INSERT INTO scrape_logs 
                (scrape_date, status, meetings_scraped, races_scraped, runners_scraped, 
                 error_message, duration_seconds)
                VALUES (:scrape_date, :status, :meetings_scraped, :races_scraped, :runners_scraped,
                        :error_message, :duration_seconds)
            """),
            {
                'scrape_date': scrape_date,
                'status': stats['status'],
                'meetings_scraped': stats['meetings'],
                'races_scraped': stats['races'],
                'runners_scraped': stats['runners'],
                'error_message': stats['error'],
                'duration_seconds': int(duration),
            }
        )
        await self.db.commit()

    async def backfill_history(self, start_date: date, end_date: date):
        """回填歷史數據"""
        current = start_date
        while current <= end_date:
            try:
                await self.scrape_date(current)
            except Exception as e:
                logger.error(f"Failed to scrape {current}: {e}")
            current += timedelta(days=1)