import type {
  RaceMeeting,
  OddsPool,
  PoolInvestment,
  QuantAnalysis,
} from './types';

// In production (Vercel), point to Render backend directly.
// In development, use Vite proxy (see vite.config.ts).
const API_BASE = import.meta.env.VITE_API_BASE || 
  (import.meta.env.PROD 
    ? 'https://hk-racing-quant.onrender.com/api' 
    : '/api');

// ═══ Cold-start detection ═══
let coldStartDetected = false;

export function isColdStarting(): boolean {
  return coldStartDetected;
}

export function clearColdStart(): void {
  coldStartDetected = false;
}

// ═══ Generic Fetch Helper ═══

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000); // 60s for cold start

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    });

    if (res.status === 503 || res.status === 502) {
      coldStartDetected = true;
      throw new Error('SERVER_COLD_START');
    }

    coldStartDetected = false;

    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`API ${res.status}: ${text}`);
    }
    return res.json();
  } catch (err: any) {
    if (err.name === 'AbortError') {
      coldStartDetected = true;
      throw new Error('SERVER_COLD_START');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

// ═══ Live Data API (via backend proxy — no CORS issues) ═══

export async function getRaceMeetings(date?: string, venue_code?: string): Promise<RaceMeeting[]> {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (venue_code) params.set('venue_code', venue_code);
  const qs = params.toString();
  return fetchAPI<RaceMeeting[]>(`/live/meetings${qs ? '?' + qs : ''}`);
}

export async function getRaceOdds(
  race_no: number,
  odds_types: string[] = ['WIN', 'PLA'],
  date?: string,
  venue_code?: string,
): Promise<{ pools: OddsPool[]; timestamp: number }> {
  const params = new URLSearchParams({
    race_no: String(race_no),
    odds_types: odds_types.join(','),
  });
  if (date) params.set('date', date);
  if (venue_code) params.set('venue_code', venue_code);
  return fetchAPI(`/live/odds?${params}`);
}

// ═══ Live Quant Analysis (computed on backend) ═══

export interface LiveAnalysisResponse {
  meeting_id: string;
  venue_code: string;
  date: string;
  race_no: number;
  race_name_en: string;
  race_name_ch: string;
  distance: number;
  going: string;
  race_class: string;
  total_runners: number;
  runners: RunnerAnalysis[];
  pace_forecast: PaceForecast;
  smart_money_alerts: SmartMoneyAlert[];
  hidden_signals: HiddenSignal[];
  value_bet_count: number;
  timestamp: number;
}

export interface RunnerAnalysis {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
  barrier: number;
  weight: number;
  jockey: string;
  win_odds: number;
  p_true: number;
  p_market: number;
  ev: number;
  edge: number;
  kelly_fraction: number;
  is_value_bet: boolean;
  pace_style: string;
  rating: number;
  last6run?: string;
}

export interface PaceForecast {
  pace_type: string;
  front_runners: number[];
  mid_field: number[];
  closers: number[];
  description: string;
}

export interface SmartMoneyAlert {
  horse_no: number;
  horse_name: string;
  alert_type: string;
  severity: string;
  description: string;
}

export interface HiddenSignal {
  horse_no: number;
  horse_name: string;
  signal_type: string;
  severity: string;
  category: string;
  title_en: string;
  title_ch: string;
  description: string;
  confidence: number;
}

export async function getLiveAnalysis(
  race_no: number,
  date?: string,
  venue_code?: string,
): Promise<LiveAnalysisResponse> {
  const params = new URLSearchParams({ race_no: String(race_no) });
  if (date) params.set('date', date);
  if (venue_code) params.set('venue_code', venue_code);
  return fetchAPI(`/live/analyze?${params}`);
}

// ═══ Pre-Race Analysis (no odds required) ═══

export interface PreRaceAnalysisResponse {
  meeting_id: string;
  venue_code: string;
  date: string;
  race_no: number;
  race_name_en: string;
  race_name_ch: string;
  distance: number;
  going: string;
  race_class: string;
  total_runners: number;
  status: 'odds_not_available' | 'odds_partial';
  runners: PreRaceRunner[];
  pace_forecast: PreRacePace;
  hidden_signals: PreRaceSignal[];
  timestamp: number;
}

export interface PreRaceRunner {
  horse_no: number;
  horse_name: string;
  horse_name_ch: string;
  barrier: number;
  weight: number;
  jockey: string;
  jockey_ch: string;
  trainer: string;
  trainer_ch: string;
  win_prob: number;
  win_prob_rank: number;
  pace_style: string;
  rating: number;
  last6run: string;
  strong_contender: boolean;
  barrier_versatile: boolean;
  superhorse: boolean;
}

export interface PreRacePace {
  pace_type: string;
  front_runners: number[];
  mid_field: number[];
  closers: number[];
  description: string;
  front_count: number;
  impact: string;
}

export interface PreRaceSignal {
  horse_no: number;
  horse_name: string;
  signal_type: string;
  severity: string;
  category: string;
  title_en: string;
  title_ch: string;
  description: string;
  confidence: number;
}

export async function getPreRaceAnalysis(
  race_no: number,
  date?: string,
  venue_code?: string,
): Promise<PreRaceAnalysisResponse> {
  const params = new URLSearchParams({ race_no: String(race_no) });
  if (date) params.set('date', date);
  if (venue_code) params.set('venue_code', venue_code);
  return fetchAPI(`/pre/analyze?${params}`);
}

// ═══ Historical Results ═══

export async function getHistoricalResults(date: string): Promise<any> {
  return fetchAPI(`/live/results?date=${date}`);
}

// ═══ Client-side Quant Engine (fallback when backend unavailable) ═══

const TAKEOUT_RATE = 0.175;
const MIN_PROB = 0.005;

function softmax(scores: number[]): number[] {
  const clipped = scores.map(s => Math.max(-50, Math.min(0, s - Math.max(...scores))));
  const exps = clipped.map(s => Math.exp(s));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => Math.max(MIN_PROB, e / sum));
}

export function computeLocalAnalysis(
  runners: any[],
  odds_pools: OddsPool[],
): QuantAnalysis {
  const winPool = odds_pools.find(p => p.oddsType === 'WIN');
  const winOddsMap: Record<number, number> = {};
  if (winPool) {
    for (const node of winPool.oddsNodes) {
      const no = parseInt(node.combString);
      if (!isNaN(no)) winOddsMap[no] = parseFloat(node.oddsValue) || 0;
    }
  }

  const scores = runners.map(r => {
    let score = 60;
    score += (15 - (r.barrierDrawNumber || 7)) * 1.5;
    score += ((r.handicapWeight || 126) - 115) * 0.8;
    return score;
  });

  const p_true_arr = softmax(scores);
  const p_market_arr = runners.map(r => {
    const odds = r.winOdds || winOddsMap[r.no] || 100;
    const raw = 1 / odds;
    return raw / (1 - TAKEOUT_RATE);
  });

  return {
    race_no: 0,
    runners: [],
    pace_forecast: {
      pace_type: 'moderate',
      front_runners: [],
      mid_field: [],
      closers: [],
      description: '本地計算（僅供參考）',
    },
    smart_money_alerts: [],
  };
}
