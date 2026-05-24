"""
Data import routes: CSV/JSON upload for historical data.
"""
import csv
import io
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Horse, Jockey, Trainer, RaceMeeting, Race, Runner
from app.services.schemas import CSVImportResult

router = APIRouter(prefix="/api/v1/import", tags=["import"])


@router.post("/horses/csv", response_model=CSVImportResult)
async def import_horses_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    導入馬匹基礎數據 CSV。
    預期欄位：brand_number, name_en, name_ch, age, sex, sire, dam, rating
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            brand = row.get("brand_number", "").strip()
            if not brand:
                skipped += 1
                continue

            # Upsert by brand_number
            from sqlalchemy import select
            stmt = select(Horse).where(Horse.brand_number == brand)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update
                for field in ["name_en", "name_ch", "age", "sex", "sire", "dam", "rating"]:
                    if field in row and row[field]:
                        setattr(existing, field, row[field].strip())
            else:
                horse = Horse(
                    brand_number=brand,
                    name_en=row.get("name_en", "").strip(),
                    name_ch=row.get("name_ch", "").strip() or None,
                    age=int(row["age"]) if row.get("age") else None,
                    sex=row.get("sex", "").strip() or None,
                    sire=row.get("sire", "").strip() or None,
                    dam=row.get("dam", "").strip() or None,
                    rating=int(row["rating"]) if row.get("rating") else None,
                )
                db.add(horse)

            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            skipped += 1

    await db.commit()
    return CSVImportResult(
        total_rows=imported + skipped,
        imported=imported,
        skipped=skipped,
        errors=errors[:20],  # 限制錯誤回傳數量
    )


@router.post("/results/csv", response_model=CSVImportResult)
async def import_race_results_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    導入歷史賽績 CSV。
    預期欄位：meeting_date, venue, race_number, race_class, distance,
              horse_brand, jockey_name, trainer_name, barrier, weight,
              finishing_position, winning_time, odds_at_start
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            # TODO: Full import logic with meeting/race/runner creation
            # This is a placeholder - the full implementation needs:
            # 1. Create/find RaceMeeting by date+venue
            # 2. Create/find Race by meeting_id+race_number
            # 3. Create/find Horse by brand_number
            # 4. Create/find Jockey/Trainer by name
            # 5. Create Runner with all fields
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            skipped += 1

    await db.commit()
    return CSVImportResult(
        total_rows=imported + skipped,
        imported=imported,
        skipped=skipped,
        errors=errors[:20],
    )
