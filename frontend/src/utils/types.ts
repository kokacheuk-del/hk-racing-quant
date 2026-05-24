// ═══ HKJC Data Types ═══

export interface RaceMeeting {
  id: string;
  venueCode: string;
  date: string;
  status: string;
  totalNumberOfRace: number;
  currentNumberOfRace: number;
  dateOfWeek: string;
  meetingType: string;
  totalInvestment?: number;
  races: Race[];
}

export interface Race {
  id: string;
  no: number;
  status: string;
  raceName_en: string;
  raceName_ch: string;
  postTime: string;
  distance: number;
  go_en: string;
  go_ch: string;
  raceClass_en: string;
  raceClass_ch: string;
  ratingType: string;
  wageringFieldSize: number;
  raceCourse: {
    description_en: string;
    description_ch: string;
    displayCode: string;
  };
  raceTrack: {
    description_en: string;
    description_ch: string;
  };
  runners: Runner[];
}

export interface Runner {
  id: string;
  no: number;
  status: string;
  name_en: string;
  name_ch: string;
  horse: { id: string; code: string };
  color: string;
  barrierDrawNumber: number;
  handicapWeight: number;
  currentWeight?: number;
  currentRating?: number;
  internationalRating?: number;
  gearInfo?: string;
  last6run?: string;
  saddleClothNo?: number;
  trumpCard?: boolean;
  priority?: boolean;
  finalPosition?: number;
  deadHeat?: boolean;
  winOdds?: number;
  jockey: { code: string; name_en: string; name_ch: string };
  trainer: { code: string; name_en: string; name_ch: string };
}

// ═══ Odds Types ═══

export interface OddsPool {
  id: string;
  oddsType: string;
  status: string;
  sellStatus: string;
  lastUpdateTime: string;
  name_en?: string;
  name_ch?: string;
  guarantee?: number;
  minTicketCost?: number;
  oddsNodes: OddsNode[];
  cWinSelections?: CWinSelection[];
}

export interface OddsNode {
  combString: string;
  oddsValue: string;
  hotFavourite: boolean;
  oddsDropValue: string | null;
  bankerOdds?: { combString: string; oddsValue: string }[];
}

export interface CWinSelection {
  composite: boolean;
  name_ch: string;
  name_en: string;
  starters: number;
}

export interface PoolInvestment {
  id: string;
  oddsType: string;
  status: string;
  sellStatus: string;
  investment: string;
  mergedPoolId?: string;
  lastUpdateTime: string;
  leg?: { number: number; races: number[] };
}

// ═══ Quant Analysis Types ═══

export interface QuantAnalysis {
  race_no: number;
  runners: RunnerAnalysis[];
  pace_forecast: PaceForecast;
  smart_money_alerts: SmartMoneyAlert[];
}

export interface RunnerAnalysis {
  horse_no: number;
  horse_name: string;
  barrier: number;
  weight: number;
  jockey: string;
  trainer: string;
  win_odds: number;
  p_true: number;
  p_market: number;
  ev: number;
  edge: number;
  kelly_fraction: number;
  is_value_bet: boolean;
  pace_style: 'front' | 'mid' | 'closer';
  rating: number;
}

export interface PaceForecast {
  pace_type: 'slow' | 'moderate' | 'fast';
  front_runners: number[];
  mid_field: number[];
  closers: number[];
  description: string;
}

export interface SmartMoneyAlert {
  horse_no: number;
  horse_name: string;
  alert_type: 'odds_drop' | 'pool_surge';
  severity: 'low' | 'medium' | 'high';
  description: string;
  old_odds?: number;
  new_odds?: number;
  pool_change?: number;
}

// ═══ UI State Types ═══

export interface FeatureWeights {
  barrier_advantage: number;
  jockey_win_rate: number;
  trainer_win_rate: number;
  horse_form: number;
  weight_factor: number;
  pace_suitability: number;
  wet_track: number;
  distance_suitability: number;
}

export const DEFAULT_WEIGHTS: FeatureWeights = {
  barrier_advantage: 1.0,
  jockey_win_rate: 1.2,
  trainer_win_rate: 1.0,
  horse_form: 1.1,
  weight_factor: 0.9,
  pace_suitability: 1.0,
  wet_track: 0.8,
  distance_suitability: 1.0,
};

// ═══ Venue Helpers ═══

export const VENUE_MAP: Record<string, { en: string; ch: string; short: string }> = {
  ST: { en: 'Sha Tin', ch: '沙田', short: 'STV' },
  HV: { en: 'Happy Valley', ch: '跑馬地', short: 'HV' },
  S1: { en: 'Sha Tin (Simulcast)', ch: '沙田(轉播)', short: 'S1' },
  S2: { en: 'Sha Tin (Simulcast 2)', ch: '沙田(轉播2)', short: 'S2' },
};

export const GOING_MAP: Record<string, { color: string; label: string }> = {
  FIRM: { color: '#ef4444', label: 'Firm' },
  GOOD_TO_FIRM: { color: '#f97316', label: 'G→F' },
  GOOD: { color: '#10b981', label: 'Good' },
  GOOD_TO_YIELDING: { color: '#06b6d4', label: 'G→Y' },
  YIELDING: { color: '#3b82f6', label: 'Yielding' },
  YIELDING_TO_SOFT: { color: '#8b5cf6', label: 'Y→S' },
  SOFT: { color: '#a855f7', label: 'Soft' },
  SLOW: { color: '#ec4899', label: 'Slow' },
  HEAVY: { color: '#dc2626', label: 'Heavy' },
};
