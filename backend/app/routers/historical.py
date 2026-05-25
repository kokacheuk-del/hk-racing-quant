"""
Historical Data API - 歷史賽事數據查詢接口
"""
import logging
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

router = APIRouter(prefix="/api/historical", tags=["historical"])
logger = logging.getLogger(__name__)


@router.get("/meetings")
async def get_historical_meetings(
    start_date: str = Query(..., description="開始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="結束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """獲取指定日期範圍的賽事日程"""
    try:
        if end_date:
            result = await db.execute(
                text("""
                    SELECT id, meeting_date, venue_code, venue_name_en, 
                           total_races, status, created_at, updated_at
                    FROM race_meetings
                    WHERE meeting_date BETWEEN :start AND :end
                    ORDER BY meeting_date DESC
                """),
                {'start': start_date, 'end': end_date}
            )
        else:
            result = await db.execute(
                text("""
                    SELECT id, meeting_date, venue_code, venue_name_en, 
                           total_races, status, created_at, updated_at
                    FROM race_meetings
                    WHERE meeting_date = :start
                    ORDER BY meeting_date DESC
                """),
                {'start': start_date}
            )

        rows = result.fetchall()
        columns = result.keys()

        return {
            'success': True,
            'count': len(rows),
            'data': [dict(zip(columns, row)) for row in rows]
        }

    except Exception as e:
        logger.error(f"Error getting historical meetings: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/races")
async def get_historical_races(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """獲取指定日期的所有賽事"""
    try:
        result = await db.execute(
            text("""
                SELECT r.id, r.meeting_id, r.race_no, r.race_name_en, r.race_name_ch,
                       r.race_class, r.distance, r.going, r.track, r.prize_money, r.status,
                       rm.meeting_date, rm.venue_code
                FROM races r
                JOIN race_meetings rm ON rm.id = r.meeting_id
                WHERE rm.meeting_date = :date
                ORDER BY r.race_no
            """),
            {'date': date}
        )

        rows = result.fetchall()
        columns = result.keys()

        return {
            'success': True,
            'count': len(rows),
            'data': [dict(zip(columns, row)) for row in rows]
        }

    except Exception as e:
        logger.error(f"Error getting historical races: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/race/{race_id}/runners")
async def get_race_runners(
    race_id: int,
    db: AsyncSession = Depends(get_db),
):
    """獲取指定賽事的所有參賽馬匹詳情"""
    try:
        result = await db.execute(
            text("""
                SELECT rr.id, rr.race_id, rr.horse_no, rr.barrier,
                       rr.jockey_name_en, rr.trainer_name_en,
                       rr.actual_weight, rr.declared_horse_weight, rr.rating,
                       rr.final_position, rr.win_odds,
                       rr.model_probability, rr.market_probability,
                       rr.ev_value, rr.kelly_fraction, rr.is_value_bet,
                       h.horse_name_en, h.horse_name_ch
                FROM race_runners rr
                JOIN horses h ON h.id = rr.horse_id
                WHERE rr.race_id = :race_id
                ORDER BY rr.final_position, rr.horse_no
            """),
            {'race_id': race_id}
        )

        rows = result.fetchall()
        columns = result.keys()

        return {
            'success': True,
            'count': len(rows),
            'data': [dict(zip(columns, row)) for row in rows]
        }

    except Exception as e:
        logger.error(f"Error getting race runners: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/backtest")
async def get_backtest_data(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """獲取完整的回測數據（包含所有賽事和參賽馬匹）"""
    try:
        # 1. 獲取該日的賽事
        races_result = await db.execute(
            text("""
                SELECT r.id, r.race_no, r.race_name_en, r.race_name_ch,
                       r.race_class, r.distance, r.going
                FROM races r
                JOIN race_meetings rm ON rm.id = r.meeting_id
                WHERE rm.meeting_date = :date
                ORDER BY r.race_no
            """),
            {'date': date}
        )

        race_rows = races_result.fetchall()
        race_columns = races_result.keys()

        if not race_rows:
            return {
                'success': True,
                'date': date,
                'venue': '',
                'races': {},
                'total_races': 0,
            }

        # 2. 獲取賽事信息
        meeting_result = await db.execute(
            text("""
                SELECT venue_code
                FROM race_meetings
                WHERE meeting_date = :date
                LIMIT 1
            """),
            {'date': date}
        )
        meeting_row = meeting_result.fetchone()
        venue = meeting_row[0] if meeting_row else ''

        # 3. 獲取每場賽事的參賽馬匹
        races_dict = {}
        for race_row in race_rows:
            race_data = dict(zip(race_columns, race_row))
            race_id = race_data['id']
            race_no = race_data['race_no']

            # 獲取參賽馬匹
            runners_result = await db.execute(
                text("""
                    SELECT rr.horse_no, rr.final_position, rr.win_odds,
                           rr.model_probability, rr.market_probability,
                           rr.ev_value, rr.kelly_fraction, rr.is_value_bet,
                           h.horse_name_en
                    FROM race_runners rr
                    JOIN horses h ON h.id = rr.horse_id
                    WHERE rr.race_id = :race_id
                    ORDER BY rr.final_position
                """),
                {'race_id': race_id}
            )

            runner_rows = runners_result.fetchall()
            runner_columns = runners_result.keys()

            races_dict[str(race_no)] = [
                dict(zip(runner_columns, row)) for row in runner_rows
            ]

        return {
            'success': True,
            'date': date,
            'venue': venue,
            'races': races_dict,
            'total_races': len(race_rows),
        }

    except Exception as e:
        logger.error(f"Error getting backtest data: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/scrape")
async def trigger_scrape(
    date: str = Query(..., description="要抓取的日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """手動觸發指定日期的數據抓取"""
    try:
        from datetime import date as date_type
        from app.services.historical_scraper import HistoricalDataScraper

        scrape_date = date_type.fromisoformat(date)
        scraper = HistoricalDataScraper(db)
        stats = await scraper.scrape_date(scrape_date)

        return {
            'success': True,
            'date': date,
            **stats
        }

    except Exception as e:
        logger.error(f"Error triggering scrape: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/stats/summary")
async def get_historical_summary(
    db: AsyncSession = Depends(get_db),
):
    """獲取歷史數據統計摘要"""
    try:
        # 總賽事數
        result = await db.execute(text("SELECT COUNT(*) FROM race_meetings"))
        total_meetings = result.fetchone()[0]

        # 總場數
        result = await db.execute(text("SELECT COUNT(*) FROM races"))
        total_races = result.fetchone()[0]

        # 總馬匹數
        result = await db.execute(text("SELECT COUNT(*) FROM horses"))
        total_horses = result.fetchone()[0]

        # 有數據的日期範圍
        result = await db.execute(
            text("SELECT MIN(meeting_date), MAX(meeting_date) FROM race_meetings")
        )
        min_date, max_date = result.fetchone()

        # +EV 命中率統計
        result = await db.execute(
            text("""
                SELECT 
                    COUNT(*) as total_value_bets,
                    SUM(CASE WHEN final_position = 1 THEN 1 ELSE 0 END) as wins
                FROM race_runners
                WHERE is_value_bet = true
            """)
        )
        vb_total, vb_wins = result.fetchone()

        hit_rate = (vb_wins / vb_total * 100) if vb_total > 0 else 0

        return {
            'success': True,
            'summary': {
                'total_meetings': total_meetings,
                'total_races': total_races,
                'total_horses': total_horses,
                'date_range': {
                    'from': min_date.isoformat() if min_date else None,
                    'to': max_date.isoformat() if max_date else None,
                },
                'value_bets': {
                    'total': vb_total,
                    'wins': vb_wins,
                    'hit_rate': round(hit_rate, 2),
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting historical summary: {e}")
        raise HTTPException(500, detail=str(e))