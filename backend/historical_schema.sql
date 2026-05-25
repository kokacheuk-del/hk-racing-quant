-- ============================================
-- HK Racing Quant - Historical Database Schema
-- ============================================

-- 1. 賽事日程表（每天一條記錄）
CREATE TABLE IF NOT EXISTS race_meetings (
    id SERIAL PRIMARY KEY,
    meeting_date DATE NOT NULL UNIQUE,
    venue_code VARCHAR(10) NOT NULL, -- 'ST' / 'HV'
    venue_name_en VARCHAR(50),
    venue_name_ch VARCHAR(50),
    total_races INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'scheduled', -- scheduled / completed / abandoned
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_race_meetings_date ON race_meetings(meeting_date);

-- 2. 單場賽事表
CREATE TABLE IF NOT EXISTS races (
    id SERIAL PRIMARY KEY,
    meeting_id INTEGER REFERENCES race_meetings(id) ON DELETE CASCADE,
    race_no INTEGER NOT NULL,
    race_name_en VARCHAR(200),
    race_name_ch VARCHAR(200),
    race_class VARCHAR(20), -- Class 1, 2, 3, 4, 5
    distance INTEGER, -- 1000, 1200, 1400, 1600, 1800, 2000, 2400
    going VARCHAR(20), -- GOOD, GOOD TO YIELDING, YIELDING, etc.
    track VARCHAR(50), -- TURF / ALL WEATHER
    prize_money DECIMAL(15, 2),
    status VARCHAR(20) DEFAULT 'pending', -- pending / completed
    result_time VARCHAR(20), -- 最終時間
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(meeting_id, race_no)
);

CREATE INDEX IF NOT EXISTS idx_races_meeting_id ON races(meeting_id);

-- 3. 馬匹基本信息表
CREATE TABLE IF NOT EXISTS horses (
    id SERIAL PRIMARY KEY,
    horse_code VARCHAR(20) UNIQUE, -- HKJC horse ID
    horse_name_en VARCHAR(100) NOT NULL,
    horse_name_ch VARCHAR(100),
    country_of_origin VARCHAR(50),
    birth_year INTEGER,
    color VARCHAR(50),
    sex VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_horses_code ON horses(horse_code);
CREATE INDEX IF NOT EXISTS idx_horses_name_en ON horses(horse_name_en);

-- 4. 參賽馬匹詳情表（每場賽事的每匹馬）
CREATE TABLE IF NOT EXISTS race_runners (
    id SERIAL PRIMARY KEY,
    race_id INTEGER REFERENCES races(id) ON DELETE CASCADE,
    horse_id INTEGER REFERENCES horses(id),
    horse_no INTEGER NOT NULL, -- 馬號
    barrier INTEGER, -- 檔位
    jockey_code VARCHAR(20),
    jockey_name_en VARCHAR(100),
    jockey_name_ch VARCHAR(100),
    trainer_code VARCHAR(20),
    trainer_name_en VARCHAR(100),
    trainer_name_ch VARCHAR(100),
    actual_weight INTEGER, -- 負磅
    declared_horse_weight INTEGER, -- 馬體重
    rating INTEGER, -- 評分
    last_6_runs VARCHAR(50), -- 近績
    
    -- 賽果
    final_position INTEGER, -- 最終名次 (0 = 未出閘 / 未完成)
    finish_time VARCHAR(20),
    length_behind DECIMAL(8, 2),
    win_odds DECIMAL(8, 2), -- 最終勝賠率
    
    -- 模型計算字段（用於回測）
    model_probability DECIMAL(6, 4), -- 模型預測勝率
    market_probability DECIMAL(6, 4), -- 賠率隱含勝率
    ev_value DECIMAL(8, 4), -- +EV 值
    kelly_fraction DECIMAL(6, 4), -- Kelly 比例
    is_value_bet BOOLEAN DEFAULT FALSE, -- 是否為價值投注
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(race_id, horse_no)
);

CREATE INDEX IF NOT EXISTS idx_race_runners_race_id ON race_runners(race_id);
CREATE INDEX IF NOT EXISTS idx_race_runners_horse_id ON race_runners(horse_id);
CREATE INDEX IF NOT EXISTS idx_race_runners_position ON race_runners(final_position);

-- 5. 賠率歷史表（可選，用於分析賠率變化）
CREATE TABLE IF NOT EXISTS odds_history (
    id SERIAL PRIMARY KEY,
    race_id INTEGER REFERENCES races(id) ON DELETE CASCADE,
    horse_no INTEGER NOT NULL,
    win_odds DECIMAL(8, 2) NOT NULL,
    odds_time TIMESTAMP NOT NULL,
    source VARCHAR(50), -- 'HKJC' / 'Model'
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_odds_history_race_id ON odds_history(race_id);
CREATE INDEX IF NOT EXISTS idx_odds_history_time ON odds_history(odds_time);

-- 6. 系統日誌表（記錄爬蟲執行情況）
CREATE TABLE IF NOT EXISTS scrape_logs (
    id SERIAL PRIMARY KEY,
    scrape_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL, -- success / failed / partial
    meetings_scraped INTEGER DEFAULT 0,
    races_scraped INTEGER DEFAULT 0,
    runners_scraped INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scrape_logs_date ON scrape_logs(scrape_date);

-- ============================================
-- 視圖：便於查詢
-- ============================================

-- 完整賽事結果視圖
CREATE OR REPLACE VIEW v_race_results AS
SELECT 
    rm.meeting_date,
    rm.venue_code,
    r.race_no,
    r.race_name_en,
    r.race_name_ch,
    r.race_class,
    r.distance,
    r.going,
    rr.horse_no,
    rr.barrier,
    h.horse_name_en,
    h.horse_name_ch,
    rr.jockey_name_en,
    rr.trainer_name_en,
    rr.final_position,
    rr.win_odds,
    rr.model_probability,
    rr.market_probability,
    rr.ev_value,
    rr.is_value_bet
FROM race_meetings rm
JOIN races r ON r.meeting_id = rm.id
JOIN race_runners rr ON rr.race_id = r.id
JOIN horses h ON h.id = rr.horse_id
WHERE r.status = 'completed'
ORDER BY rm.meeting_date DESC, r.race_no, rr.final_position;

-- ============================================
-- 函數：更新時間戳
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 為需要的表添加觸發器
DROP TRIGGER IF EXISTS update_race_meetings_updated_at ON race_meetings;
CREATE TRIGGER update_race_meetings_updated_at BEFORE UPDATE ON race_meetings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_races_updated_at ON races;
CREATE TRIGGER update_races_updated_at BEFORE UPDATE ON races
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_horses_updated_at ON horses;
CREATE TRIGGER update_horses_updated_at BEFORE UPDATE ON horses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_race_runners_updated_at ON race_runners;
CREATE TRIGGER update_race_runners_updated_at BEFORE UPDATE ON race_runners
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();