"""
Scraper API Routes — 手動觸發數據抓取
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.scraper.hkjc_scraper import HKJCScraper

router = APIRouter(prefix="/api/v1/scraper", tags=["scraper"])
logger = logging.getLogger(__name__)


@router.get("/racecard")
async def scrape_racecard(
    date: str = Query(..., description="賽事日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """
    手動抓取指定日期的排位表數據
    """
    try:
        scraper = HKJCScraper()
        
        # Parse date
        from datetime import datetime
        race_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        # TODO: 調用 scraper 並存入數據庫
        # 這裡需要實現從 ScrapedRaceCard → DB Models 的轉換
        
        logger.info(f"Scraping race card for {date}")
        
        # 臨時返回，完整版需要實現數據轉換
        return {
            "success": True,
            "date": date,
            "message": "Scraper initialized - full implementation requires data mapping",
            "next_steps": "Implement ScrapedRaceCard -> DB Models conversion in app/scraper/service.py"
        }
        
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@router.get("/status")
async def scraper_status():
    """
    檢查爬蟲狀態
    """
    return {
        "status": "available",
        "available_endpoints": [
            "/api/v1/scraper/racecard?date=YYYY-MM-DD",
            "/api/v1/scraper/results?date=YYYY-MM-DD",
            "/api/v1/scraper/odds?race_id=xxx",
        ],
        "note": "Full scraping logic requires implementing ScrapedRaceCard -> DB Models mapping"
    }
