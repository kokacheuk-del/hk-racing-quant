// ============================================
// Historical Data API - 歷史數據接口
// ============================================

const API_BASE = import.meta.env.VITE_API_BASE || 
  (import.meta.env.PROD ? 'https://hk-racing-quant.onrender.com/api' : '/api');

export interface HistoricalRace {
  id: number;
  race_no: number;
  race_name_en: string;
  race_name_ch: string;
  race_class: string;
  distance: number;
  going: string;
  status: string;
}

export interface HistoricalRunner {
  horse_no: number;
  horse_name_en: string;
  horse_name_ch: string;
  final_position: number;
  win_odds: number;
  barrier: number;
  jockey_name_en: string;
  trainer_name_en: string;
  actual_weight: number;
  rating: number;
  model_probability: number;
  market_probability: number;
  ev_value: number;
  kelly_fraction: number;
  is_value_bet: boolean;
}

export interface BacktestResult {
  success: boolean;
  date: string;
  venue: string;
  races: Record<string, HistoricalRunner[]>;
  total_races: number;
}

export interface ScrapeResult {
  success: boolean;
  date: string;
  meetings: number;
  races: number;
  runners: number;
  status: string;
  error?: string;
}

/**
 * 獲取指定日期的回測數據（從歷史數據庫）
 */
export async function getHistoricalBacktest(date: string): Promise<BacktestResult> {
  const res = await fetch(`${API_BASE}/historical/backtest?date=${date}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to get historical backtest`);
  }
  return res.json();
}

/**
 * 手動觸發數據抓取
 */
export async function triggerScrape(date: string): Promise<ScrapeResult> {
  const res = await fetch(`${API_BASE}/historical/scrape?date=${date}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to trigger scrape`);
  }
  return res.json();
}

/**
 * 獲取歷史數據統計摘要
 */
export async function getHistoricalSummary(): Promise<any> {
  const res = await fetch(`${API_BASE}/historical/stats/summary`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to get summary`);
  }
  return res.json();
}

/**
 * 檢查某個日期是否有歷史數據
 */
export async function checkHistoricalDataExists(date: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/historical/meetings?start_date=${date}&end_date=${date}`);
    if (!res.ok) return false;
    const data = await res.json();
    return data.count > 0;
  } catch {
    return false;
  }
}