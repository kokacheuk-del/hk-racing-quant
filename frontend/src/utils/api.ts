import type {
  RaceMeeting,
  OddsPool,
  PoolInvestment,
  QuantAnalysis,
  FeatureWeights,
  RunnerAnalysis,
  PaceForecast,
  SmartMoneyAlert,
} from './types';

// In production (Vercel), point to Render backend directly.
// In development, use Vite proxy (see vite.config.ts).
const API_BASE = import.meta.env.VITE_API_BASE || '/api';

// ═══ Generic Fetch Helper ═══

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ═══ Live Data API (via backend proxy — no CORS issues) ═══

export async function getActiveMeetings(): Promise<RaceMeeting[]> {
  return fetchAPI<RaceMeeting[]>('/live/meetings');
}

export async function getRaceMeetings(date?: string, venueCode?: string): Promise<RaceMeeting[]> {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (venueCode) params.set('venue_code', venueCode);
  const qs = params.toString();
  return fetchAPI<RaceMeeting[]>(`/live/meetings${qs ? '?' + qs : ''}`);
}

export async function getRaceOdds(
  raceNo: number,
  oddsTypes: string[] = ['WIN', 'PLA'],
  date?: string,
  venueCode?: string,
): Promise<{ pools: OddsPool[]; timestamp: number }> {
  const params = new URLSearchParams({
    race_no: String(raceNo),
    odds_types: oddsTypes.join(','),
  });
  if (date) params.set('date', date);
  if (venueCode) params.set('venue_code', venueCode);
  return fetchAPI(`/live/odds?${params}`);
}

export async function getRacePools(
  raceNo: number,
  oddsTypes: string[] = ['WIN', 'PLA'],
  date?: string,
  venueCode?: string,
): Promise<{ pools: PoolInvestment[]; timestamp: number }> {
  const params = new URLSearchParams({
    race_no: String(raceNo),
    odds_types: oddsTypes.join(','),
  });
  if (date) params.set('date', date);
  if (venueCode) params.set('venue_code', venueCode);
  return fetchAPI(`/live/pools?${params}`);
}

// ═══ Live Quant Analysis (computed on backend) ═══

interface LiveAnalysisResponse {
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
  value_bet_count: number;
  timestamp: number;
}

export async function getLiveAnalysis(
  raceNo: number,
  date?: string,
  venueCode?: string,
): Promise<LiveAnalysisResponse> {
  const params = new URLSearchParams({ race_no: String(raceNo) });
  if (date) params.set('date', date);
  if (venueCode) params.set('venue_code', venueCode);
  return fetchAPI(`/live/analyze?${params}`);
}

// ═══ Historical Results ═══

export async function getHistoricalResults(date: string): Promise<any> {
  return fetchAPI(`/live/results?date=${date}`);
}

// ═══ Client-side Quant Engine (fallback when backend unavailable) ═══

const TAKEOUT_RATE = 0.175;
const MIN_PROB = 0.005;
const EV_THRESHOLD = 0.05;
const EDGE_THRESHOLD = 0.10;
const P_TRUE_THRESHOLD = 0.04;
const KELLY_FRACTION = 1 / 3;

function softmax(scores: number[]): number[] {
  const clipped = scores.map(s => Math.max(-50, Math.min(0, s - Math.max(...scores))));
  const exps = clipped.map(s => Math.exp(s));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map(e => Math.max(MIN_PROB, e / sum));
}

export function computeLocalAnalysis(
  runners: any[],
  oddsPools: OddsPool[],
  weights: FeatureWeights = { barrier_advantage: 1, jockey_win_rate: 1.2, trainer_win_rate: 1, horse_form: 1.1, weight_factor: 0.9, pace_suitability: 1, wet_track: 0.8, distance_suitability: 1 },
): QuantAnalysis {
  const winPool = oddsPools.find(p => p.oddsType === 'WIN');
  const winOddsMap: Record<number, number> = {};
  if (winPool) {
    for (const node of winPool.oddsNodes) {
      const no = parseInt(node.combString);
      if (!isNaN(no)) winOddsMap[no] = parseFloat(node.oddsValue) || 0;
    }
  }

  const scores = runners.map(r => {
    let score = 60;
    score += (15 - r.barrierDrawNumber) * 1.5 * weights.barrier_advantage;
    score += (r.handicapWeight - 115) * 0.8 * weights.weight_factor;
    const form = r.last6run || '';
    const positions = form.split('').filter((c: string) => /[1-9]/.test(c)).map(Number);
    if (positions.length > 0) {
      const avgPos = positions.reduce((a: number, b: number) => a + b, 0) / positions.length;
      score += (7 - avgPos) * 3 * weights.horse_form;
    }
    score += 5 * weights.jockey_win_rate;
    score += 3 * weights.trainer_win_rate;
    return score;
  });

  const pTrueArr = softmax(scores);

  const pMarketArr = runners.map(r => {
    const odds = r.winOdds || winOddsMap[r.no] || 100;
    const raw = 1 / odds;
    return raw / (1 - TAKEOUT_RATE);
  });
  const pMarketSum = pMarketArr.reduce((a, b) => a + b, 0);
  const pMarketNorm = pMarketArr.map(p => p / pMarketSum);

  const frontRunners: number[] = [];
  const midField: number[] = [];
  const closers: number[] = [];
  runners.forEach(r => {
    if (r.barrierDrawNumber <= 4) frontRunners.push(r.no);
    else if (r.handicapWeight >= 125) midField.push(r.no);
    else closers.push(r.no);
  });

  const paceType = frontRunners.length >= 3 ? 'fast' : frontRunners.length >= 2 ? 'moderate' : 'slow';

  const runnerAnalyses = runners.map((r, i) => {
    const odds = r.winOdds || winOddsMap[r.no] || 100;
    const pTrue = pTrueArr[i];
    const pMarket = pMarketNorm[i];
    const ev = pTrue * (odds - 1) - (1 - pTrue);
    const edge = pTrue - pMarket;
    const kelly = pTrue > 0 && odds > 1
      ? Math.max(0, (pTrue * (odds - 1) - (1 - pTrue)) / (odds - 1)) * KELLY_FRACTION
      : 0;
    const isValueBet = ev > EV_THRESHOLD && edge > EDGE_THRESHOLD && pTrue > P_TRUE_THRESHOLD;

    return {
      horse_no: r.no,
      horse_name: r.name_en,
      barrier: r.barrierDrawNumber,
      weight: r.handicapWeight,
      jockey: r.jockey?.name_en || '',
      trainer: r.trainer?.name_en || '',
      win_odds: odds,
      p_true: Math.round(pTrue * 10000) / 100,
      p_market: Math.round(pMarket * 10000) / 100,
      ev: Math.round(ev * 10000) / 100,
      edge: Math.round(edge * 10000) / 100,
      kelly_fraction: Math.round(kelly * 10000) / 100,
      is_value_bet: isValueBet,
      pace_style: frontRunners.includes(r.no) ? 'front' as const
        : midField.includes(r.no) ? 'mid' as const : 'closer' as const,
      rating: Math.round(scores[i]),
    };
  });

  const alerts: SmartMoneyAlert[] = [];
  if (winPool) {
    for (const node of winPool.oddsNodes) {
      const no = parseInt(node.combString);
      const drop = parseFloat(node.oddsDropValue || '0');
      if (drop > 0.5) {
        const runner = runners.find(r => r.no === no);
        alerts.push({
          horse_no: no,
          horse_name: runner?.name_en || `#${no}`,
          alert_type: 'odds_drop',
          severity: drop > 2 ? 'high' : drop > 1 ? 'medium' : 'low',
          description: `賠率急跌 ${drop.toFixed(1)}`,
        });
      }
      if (node.hotFavourite) {
        const runner = runners.find(r => r.no === no);
        alerts.push({
          horse_no: no,
          horse_name: runner?.name_en || `#${no}`,
          alert_type: 'pool_surge',
          severity: 'medium',
          description: '熱門馬',
        });
      }
    }
  }

  return {
    race_no: 0,
    runners: runnerAnalyses,
    pace_forecast: {
      pace_type: paceType,
      front_runners: frontRunners,
      mid_field: midField,
      closers: closers,
      description: paceType === 'fast' ? '快步速 — 後上馬有利' : paceType === 'slow' ? '慢步速 — 前領馬有利' : '正常步速',
    },
    smart_money_alerts: alerts,
  };
}
