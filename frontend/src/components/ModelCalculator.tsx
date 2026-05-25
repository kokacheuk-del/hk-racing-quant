import { useState, useEffect, useCallback } from 'react';
import type { RaceMeeting, FeatureWeights } from '../utils/types';
import { getLiveAnalysis, getPreRaceAnalysis, computeLocalAnalysis, type LiveAnalysisResponse } from '../utils/api';
import { DEFAULT_WEIGHTS } from '../utils/types';
import { pct, evColor, paceTag } from '../utils/helpers';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Calculator, Sliders, RefreshCw, AlertCircle, Timer } from 'lucide-react';

interface RunnerRow {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
  barrier: number;
  weight: number;
  jockey: string;
  jockey_ch?: string;
  trainer?: string;
  trainer_ch?: string;
  win_odds: number;
  p_true: number;
  p_market?: number;
  ev?: number;
  edge?: number;
  kelly_fraction?: number;
  is_value_bet?: boolean;
  pace_style: 'front' | 'mid' | 'closer';
  rating: number;
  last6run?: string;
  hot_favourite?: boolean;
  odds_drop?: number;
  strong_contender?: boolean;
  barrier_versatile?: boolean;
  superhorse?: boolean;
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
    impact?: string;
  };
  smart_money_alerts: any[];
  value_bet_count?: number;
  timestamp?: number;
}

type AnalysisMode = 'live' | 'pre-race' | 'fallback';

interface Props {
  meeting: RaceMeeting | null;
  raceNo: number;
}

export default function ModelCalculator({ meeting, raceNo }: Props) {
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<AnalysisMode>('live');
  const [weights, setWeights] = useState<FeatureWeights>({ ...DEFAULT_WEIGHTS });
  const [showWeights, setShowWeights] = useState(false);

  const loadAnalysis = useCallback(async () => {
    if (!meeting || !raceNo) return;
    setLoading(true);
    setError('');
    setMode('live');
    try {
      // Try live analysis (with odds) first
      const data: LiveAnalysisResponse = await getLiveAnalysis(raceNo, meeting.date, meeting.venueCode);
      
      // Check if odds are actually available (not all 0 or 100 default)
      const totalOdds = data.runners.reduce((sum, r) => sum + r.win_odds, 0);
      const avgOdds = totalOdds / data.runners.length;
      
      // If avg odds is 100, it means all odds are default (not available yet)
      // Switch to pre-race analysis
      if (avgOdds >= 99) {
        const preData = await getPreRaceAnalysis(raceNo, meeting.date, meeting.venueCode);
        setMode('pre-race');
        setAnalysis({
          race_no: preData.race_no,
          runners: preData.runners.map(r => ({
            horse_no: r.horse_no,
            horse_name: r.horse_name,
            horse_name_ch: r.horse_name_ch,
            barrier: r.barrier,
            weight: r.weight,
            jockey: r.jockey,
            jockey_ch: r.jockey_ch,
            trainer: r.trainer,
            trainer_ch: r.trainer_ch,
            win_odds: 0,
            p_true: r.win_prob,
            pace_style: r.pace_style as 'front' | 'mid' | 'closer',
            rating: r.rating,
            last6run: r.last6run,
            strong_contender: r.strong_contender,
            barrier_versatile: r.barrier_versatile,
            superhorse: r.superhorse,
          })),
          pace_forecast: {
            pace_type: preData.pace_forecast.pace_type,
            front_runners: preData.pace_forecast.front_runners,
            mid_field: preData.pace_forecast.mid_field,
            closers: preData.pace_forecast.closers,
            description: preData.pace_forecast.description,
            impact: preData.pace_forecast.impact,
          },
          smart_money_alerts: [],
          timestamp: preData.timestamp,
        });
        return;
      }

      // Normal live analysis with odds
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
      console.warn('Backend analysis failed, trying pre-race then local fallback:', backendErr.message);
      
      // Try pre-race analysis first
      try {
        const preData = await getPreRaceAnalysis(raceNo, meeting.date, meeting.venueCode);
        setMode('pre-race');
        setAnalysis({
          race_no: preData.race_no,
          runners: preData.runners.map(r => ({
            horse_no: r.horse_no,
            horse_name: r.horse_name,
            horse_name_ch: r.horse_name_ch,
            barrier: r.barrier,
            weight: r.weight,
            jockey: r.jockey,
            jockey_ch: r.jockey_ch,
            trainer: r.trainer,
            trainer_ch: r.trainer_ch,
            win_odds: 0,
            p_true: r.win_prob,
            pace_style: r.pace_style as 'front' | 'mid' | 'closer',
            rating: r.rating,
            last6run: r.last6run,
            strong_contender: r.strong_contender,
            barrier_versatile: r.barrier_versatile,
            superhorse: r.superhorse,
          })),
          pace_forecast: {
            pace_type: preData.pace_forecast.pace_type,
            front_runners: preData.pace_forecast.front_runners,
            mid_field: preData.pace_forecast.mid_field,
            closers: preData.pace_forecast.closers,
            description: preData.pace_forecast.description,
            impact: preData.pace_forecast.impact,
          },
          smart_money_alerts: [],
          timestamp: preData.timestamp,
        });
        return;
      } catch {
        // Fallback to local calculation
        setMode('fallback');
        setError('Backend unavailable — using local calculation');
        const race = meeting.races?.find((r: any) => r.no === raceNo);
        if (race?.runners) {
          const localResult = computeLocalAnalysis(race.runners, []);
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
      }
    } finally {
      setLoading(false);
    }
  }, [meeting, raceNo, weights]);

  useEffect(() => { loadAnalysis(); }, [loadAnalysis]);

  const race = meeting?.races?.find((r: any) => r.no === raceNo);
  if (!race && !analysis) return <div className="card text-[var(--text-muted)]">選擇賽事開始分析</div>;

  const chartData = analysis?.runners.map(r => ({
    name: `#${r.horse_no}`,
    p_true: r.p_true,
    p_market: r.p_market || 0,
    ev: r.ev || 0,
  })) || [];

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Calculator className="w-5 h-5 text-[var(--accent-cyan)]" />
            量化模型 — 第{raceNo}場
            {loading && <RefreshCw className="w-4 h-4 animate-spin text-[var(--text-muted)]" />}
          </h2>
          <div className="flex items-center gap-3">
            {mode === 'pre-race' && (
              <span className="flex items-center gap-1 text-xs text-[var(--accent-yellow)]">
                <AlertCircle className="w-3 h-3" />
                賠率未出 · 僅勝率分析
              </span>
            )}
            {mode === 'fallback' && (
              <span className="text-xs text-[var(--text-muted)]">本地計算</span>
            )}
            <button
              onClick={() => setShowWeights(!showWeights)}
              className="flex items-center gap-1 text-sm text-[var(--text-muted)] hover:text-[var(--accent-blue)] transition-colors"
            >
              <Sliders className="w-4 h-4" />
              權重
            </button>
          </div>
        </div>

        {showWeights && (
          <div className="mb-4 p-3 bg-[var(--bg-secondary)] rounded-lg space-y-2">
            <p className="text-xs text-[var(--text-muted)] mb-2">
              調整特徵權重（調整後會觸發本地重新計算）
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
          </div>
        )}

        {analysis?.pace_forecast && (
          <div className="flex items-center gap-3 text-sm mb-3">
            <span className="text-[var(--text-muted)]">步速：</span>
            <span className={`tag ${analysis.pace_forecast.pace_type === 'fast' ? 'tag-red' : analysis.pace_forecast.pace_type === 'slow' ? 'tag-green' : 'tag-yellow'}`}>
              {analysis.pace_forecast.pace_type.toUpperCase()}
            </span>
            <span className="text-[var(--text-secondary)]">{analysis.pace_forecast.description}</span>
            {analysis.pace_forecast.impact && (
              <span className="text-[var(--accent-cyan)]">→ {analysis.pace_forecast.impact}</span>
            )}
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
                formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name === 'p_true' ? '模型勝率' : '市場勝率']}
              />
              <Bar dataKey="p_true" name="模型勝率" fill="#06b6d4" radius={[2, 2, 0, 0]} />
              {mode === 'live' && (
                <Bar dataKey="p_market" name="市場勝率" fill="#3b82f6" radius={[2, 2, 0, 0]} opacity={0.6} />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>馬匹</th>
              <th>檔</th>
              <th>磅</th>
              <th>騎師</th>
              {mode === 'live' && <th>賠率</th>}
              <th>勝率%</th>
              {mode === 'live' && (
                <>
                  <th>市場%</th>
                  <th>EV%</th>
                  <th>Kelly%</th>
                </>
              )}
              <th>跑法</th>
            </tr>
          </thead>
          <tbody>
            {analysis?.runners.sort((a, b) => a.p_true - b.p_true > 0 ? -1 : 1).map(r => {
              const pt = paceTag(r.pace_style);
              return (
                <tr key={r.horse_no} className={r.is_value_bet ? 'bg-[var(--accent-green)]/5' : ''}>
                  <td className="font-mono">{r.horse_no}</td>
                  <td>
                    <span className="font-semibold">{r.horse_name}</span>
                    {r.superhorse && <span className="ml-1 text-sm" style={{color: '#fbbf24'}} title="超級馬王">👑</span>}
                    {r.strong_contender && <span className="ml-1 text-xs text-[var(--accent-cyan)]" title="穩膽">🏆</span>}
                    {r.barrier_versatile && <span className="ml-1 text-xs text-[var(--accent-green)]" title="檔位無影響">✓</span>}
                  </td>
                  <td className="font-mono">{r.barrier}</td>
                  <td className="font-mono">{r.weight}</td>
                  <td className="text-[var(--text-secondary)] text-xs">{r.jockey}</td>
                  {mode === 'live' && <td className="font-mono font-bold">{r.win_odds.toFixed(1)}</td>}
                  <td className="font-mono text-[var(--accent-cyan)] font-bold">{r.p_true.toFixed(1)}</td>
                  {mode === 'live' && (
                    <>
                      <td className="font-mono text-[var(--accent-blue)]">{r.p_market?.toFixed(1)}</td>
                      <td className="font-mono font-bold" style={{ color: evColor(r.ev || 0) }}>
                        {(r.ev || 0) > 0 ? '+' : ''}{r.ev?.toFixed(1)}
                      </td>
                      <td className="font-mono text-[var(--accent-yellow)]">{r.kelly_fraction?.toFixed(1)}</td>
                    </>
                  )}
                  <td><span className={`tag ${pt.cls} text-xs`}>{pt.label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
