import { useState, useEffect, useCallback } from 'react';
import type { RaceMeeting, FeatureWeights } from '../utils/types';
import { getLiveAnalysis, computeLocalAnalysis } from '../utils/api';
import { DEFAULT_WEIGHTS } from '../utils/types';
import { pct, evColor, paceTag } from '../utils/helpers';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Calculator, Sliders, RefreshCw } from 'lucide-react';

interface RunnerRow {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
  barrier: number;
  weight: number;
  jockey: string;
  jockey_ch?: string;
  trainer: string;
  trainer_ch?: string;
  win_odds: number;
  p_true: number;
  p_market: number;
  ev: number;
  edge: number;
  kelly_fraction: number;
  is_value_bet: boolean;
  pace_style: 'front' | 'mid' | 'closer';
  rating: number;
  last6run?: string;
  hot_favourite?: boolean;
  odds_drop?: number;
}

interface AnalysisData {
  race_no: number;
  runners: RunnerRow[];
  pace_forecast: {
    pace_type: string;
    front_runners: number[];
    mid_field: number[];
    closers: number[];
    description: string;
  };
  smart_money_alerts: any[];
  value_bet_count?: number;
  timestamp?: number;
}

interface Props {
  meeting: RaceMeeting | null;
  raceNo: number;
}

export default function ModelCalculator({ meeting, raceNo }: Props) {
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [weights, setWeights] = useState<FeatureWeights>({ ...DEFAULT_WEIGHTS });
  const [showWeights, setShowWeights] = useState(false);

  const loadAnalysis = useCallback(async () => {
    if (!meeting || !raceNo) return;
    setLoading(true);
    setError('');
    try {
      // Try backend first
      const data = await getLiveAnalysis(raceNo, meeting.date, meeting.venueCode);
      setAnalysis({
        race_no: data.race_no,
        runners: data.runners.map(r => ({
          ...r,
          pace_style: r.pace_style as 'front' | 'mid' | 'closer',
        })),
        pace_forecast: data.pace_forecast,
        smart_money_alerts: data.smart_money_alerts,
        value_bet_count: data.value_bet_count,
        timestamp: data.timestamp,
      });
    } catch (backendErr: any) {
      console.warn('Backend analysis failed, using local fallback:', backendErr.message);
      setError('Backend unavailable — using local calculation');
      // Fallback: client-side computation
      const race = meeting.races?.find((r: any) => r.no === raceNo);
      if (race?.runners) {
        const localResult = computeLocalAnalysis(race.runners, [], weights);
        setAnalysis({
          race_no: raceNo,
          runners: localResult.runners.map(r => ({
            ...r,
            horse_name_ch: '',
            jockey_ch: '',
            trainer_ch: '',
          })),
          pace_forecast: localResult.pace_forecast,
          smart_money_alerts: localResult.smart_money_alerts,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [meeting, raceNo, weights]);

  useEffect(() => { loadAnalysis(); }, [loadAnalysis]);

  const race = meeting?.races?.find((r: any) => r.no === raceNo);
  if (!race && !analysis) return <div className="card text-[var(--text-muted)]">Select a race to analyze</div>;

  const chartData = analysis?.runners.map(r => ({
    name: `#${r.horse_no}`,
    p_true: r.p_true,
    p_market: r.p_market,
    ev: r.ev,
  })) || [];

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Calculator className="w-5 h-5 text-[var(--accent-cyan)]" />
            Quant Model — Race {raceNo}
            {loading && <RefreshCw className="w-4 h-4 animate-spin text-[var(--text-muted)]" />}
          </h2>
          <div className="flex items-center gap-2">
            {error && <span className="text-[10px] text-[var(--accent-yellow)]">{error}</span>}
            <button
              onClick={() => setShowWeights(!showWeights)}
              className="flex items-center gap-1 text-sm text-[var(--text-muted)] hover:text-[var(--accent-blue)] transition-colors"
            >
              <Sliders className="w-4 h-4" />
              Weights
            </button>
          </div>
        </div>

        {showWeights && (
          <div className="mb-4 p-3 bg-[var(--bg-secondary)] rounded-lg space-y-2">
            <p className="text-xs text-[var(--text-muted)] mb-2">
              Adjust feature weights. Increase wet_track on rainy days.
            </p>
            {Object.entries(weights).map(([key, val]) => (
              <div key={key} className="flex items-center gap-3">
                <label className="text-xs text-[var(--text-secondary)] w-36 capitalize">
                  {key.replace(/_/g, ' ')}
                </label>
                <input
                  type="range" min="0" max="3" step="0.1" value={val}
                  onChange={e => setWeights(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))}
                  className="flex-1 accent-[var(--accent-cyan)]"
                />
                <span className="text-xs font-mono text-[var(--accent-cyan)] w-8">{val.toFixed(1)}</span>
              </div>
            ))}
            <div className="flex gap-2 mt-2">
              <button onClick={() => setWeights({ ...DEFAULT_WEIGHTS })} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                Reset Defaults
              </button>
              <button onClick={() => setWeights(prev => ({ ...prev, wet_track: 2.0 }))} className="text-xs text-[var(--accent-blue)] hover:underline">
                🌧️ Rainy Day Preset
              </button>
            </div>
          </div>
        )}

        {analysis?.pace_forecast && (
          <div className="flex items-center gap-3 text-sm mb-3">
            <span className="text-[var(--text-muted)]">Pace:</span>
            <span className={`tag ${analysis.pace_forecast.pace_type === 'fast' ? 'tag-red' : analysis.pace_forecast.pace_type === 'slow' ? 'tag-green' : 'tag-yellow'}`}>
              {analysis.pace_forecast.pace_type.toUpperCase()}
            </span>
            <span className="text-[var(--text-secondary)]">{analysis.pace_forecast.description}</span>
          </div>
        )}

        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barCategoryGap={2}>
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `${v}%`} />
              <Tooltip
                contentStyle={{ background: '#1a2332', border: '1px solid #2a3a52', borderRadius: 6 }}
                labelStyle={{ color: '#e2e8f0' }}
                formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name === 'p_true' ? 'P_true' : 'P_market']}
              />
              <Bar dataKey="p_true" name="P_true" fill="#06b6d4" radius={[2, 2, 0, 0]} />
              <Bar dataKey="p_market" name="P_market" fill="#3b82f6" radius={[2, 2, 0, 0]} opacity={0.6} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Horse</th>
              <th>Dr</th>
              <th>Wt</th>
              <th>Jockey</th>
              <th>Odds</th>
              <th>P_true</th>
              <th>P_mkt</th>
              <th>EV</th>
              <th>Edge</th>
              <th>Kelly%</th>
              <th>Pace</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody>
            {analysis?.runners.map(r => {
              const pt = paceTag(r.pace_style);
              return (
                <tr key={r.horse_no} className={r.is_value_bet ? 'signal-flash' : ''}>
                  <td className="font-mono">{r.horse_no}</td>
                  <td>
                    <span className="font-semibold">{r.horse_name}</span>
                    {r.hot_favourite && <span className="ml-1 text-[10px] text-[var(--accent-yellow)]">★</span>}
                    {r.odds_drop && r.odds_drop > 0 && <span className="ml-1 text-[10px] odds-dropping">▼</span>}
                  </td>
                  <td className="font-mono">{r.barrier}</td>
                  <td className="font-mono">{r.weight}</td>
                  <td className="text-[var(--text-secondary)]">{r.jockey}</td>
                  <td className="font-mono font-bold">{r.win_odds.toFixed(1)}</td>
                  <td className="font-mono" style={{ color: 'var(--accent-cyan)' }}>{pct(r.p_true)}</td>
                  <td className="font-mono" style={{ color: 'var(--accent-blue)' }}>{pct(r.p_market)}</td>
                  <td className="font-mono font-bold" style={{ color: evColor(r.ev) }}>
                    {r.ev > 0 ? '+' : ''}{pct(r.ev)}
                  </td>
                  <td className="font-mono" style={{ color: r.edge > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                    {r.edge > 0 ? '+' : ''}{pct(r.edge)}
                  </td>
                  <td className="font-mono">{r.kelly_fraction > 0 ? `${r.kelly_fraction.toFixed(1)}%` : '—'}</td>
                  <td><span className={`tag ${pt.cls}`}>{pt.label}</span></td>
                  <td>{r.is_value_bet && <span className="tag tag-green">+EV</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
