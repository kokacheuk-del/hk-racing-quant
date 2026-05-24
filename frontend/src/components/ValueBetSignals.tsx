import { useState, useEffect } from 'react';
import type { RaceMeeting, QuantAnalysis } from '../utils/types';
import { pct, evColor, severityColor } from '../utils/helpers';
import { AlertTriangle, Zap, TrendingDown, DollarSign, RefreshCw, Bell, Eye, Target, Flame, Shield, Activity, Wrench, MapPin, Award } from 'lucide-react';

interface RunnerRow {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
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
  ev_confidence?: string;
  strong_contender?: boolean;
  barrier_versatile?: boolean;
  superhorse?: boolean;
  pace_style: 'front' | 'mid' | 'closer';
  hot_favourite?: boolean;
  odds_drop?: number;
}

interface SmartAlert {
  horse_no: number;
  horse_name: string;
  alert_type: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
  odds_drop_value?: number;
  current_odds?: number;
}

interface HiddenSignal {
  horse_no: number;
  horse_name: string;
  signal_type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  title_en: string;
  title_ch: string;
  description: string;
  confidence: number;
  edge_boost: number;
}

interface Props {
  meeting: RaceMeeting | null;
  raceNo: number;
  analysis: {
    runners: RunnerRow[];
    pace_forecast: any;
    smart_money_alerts: SmartAlert[];
    hidden_signals?: HiddenSignal[];
    value_bet_count?: number;
  } | null;
}

const CATEGORY_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  gear:      { icon: Wrench,   color: '#f59e0b', label: '裝備' },
  weight:    { icon: Activity, color: '#3b82f6', label: '負磅' },
  jockey:    { icon: Award,    color: '#8b5cf6', label: '騎師' },
  barrier:   { icon: MapPin,   color: '#10b981', label: '檔位' },
  rating:    { icon: Target,   color: '#06b6d4', label: '評分' },
  smart_money: { icon: DollarSign, color: '#ef4444', label: '聰明錢' },
  conghua:   { icon: Flame,    color: '#f97316', label: '從化' },
  reliability: { icon: Shield, color: '#06b6d4', label: '穩膽/馬王' },
};

const SEVERITY_GLOW: Record<string, string> = {
  critical: '0 0 20px rgba(239, 68, 68, 0.6), 0 0 40px rgba(239, 68, 68, 0.3)',
  high:     '0 0 15px rgba(245, 158, 11, 0.5), 0 0 30px rgba(245, 158, 11, 0.2)',
  medium:   '0 0 10px rgba(59, 130, 246, 0.4)',
  low:      '0 0 5px rgba(100, 116, 139, 0.3)',
};

const SEVERITY_BORDER: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f59e0b',
  medium:   '#3b82f6',
  low:      '#64748b',
};

export default function ValueBetSignals({ meeting, raceNo, analysis }: Props) {
  const valueBets = analysis?.runners.filter(r => r.is_value_bet) || [];
  const alerts = analysis?.smart_money_alerts || [];
  const hiddenSignals = analysis?.hidden_signals || [];
  const sortedBets = [...valueBets].sort((a, b) => b.ev - a.ev);

  // Group signals by horse
  const signalsByHorse: Record<number, HiddenSignal[]> = {};
  for (const s of hiddenSignals) {
    if (!signalsByHorse[s.horse_no]) signalsByHorse[s.horse_no] = [];
    signalsByHorse[s.horse_no].push(s);
  }

  // Horses with most / strongest signals
  const signalScore = (signals: HiddenSignal[]) =>
    signals.reduce((acc, s) => acc + s.edge_boost * s.confidence, 0);

  const topSignalHorses = Object.entries(signalsByHorse)
    .map(([no, sigs]) => ({ no: Number(no), signals: sigs, score: signalScore(sigs) }))
    .sort((a, b) => b.score - a.score);

  const criticalCount = hiddenSignals.filter(s => s.severity === 'critical').length;
  const highCount = hiddenSignals.filter(s => s.severity === 'high').length;

  return (
    <div className="space-y-4">
      {/* ── 暗號燈號面板 ── */}
      <div className="card" style={criticalCount > 0 ? { boxShadow: SEVERITY_GLOW.critical } : {}}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Eye className="w-5 h-5" style={{ color: criticalCount > 0 ? '#ef4444' : '#f59e0b' }} />
            暗號燈號
            {criticalCount > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 animate-pulse">
                🔴 CRITICAL ×{criticalCount}
              </span>
            )}
          </h2>
          <div className="flex gap-2 text-xs">
            {Object.entries(CATEGORY_CONFIG).map(([cat, cfg]) => {
              const count = hiddenSignals.filter(s => s.category === cat).length;
              if (count === 0) return null;
              return (
                <span key={cat} className="flex items-center gap-1" style={{ color: cfg.color }}>
                  <cfg.icon className="w-3 h-3" />
                  {count}
                </span>
              );
            })}
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
            <div className="text-xl font-bold" style={{ color: criticalCount > 0 ? '#ef4444' : '#64748b' }}>
              {criticalCount}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">Critical</div>
          </div>
          <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
            <div className="text-xl font-bold" style={{ color: highCount > 0 ? '#f59e0b' : '#64748b' }}>
              {highCount}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">High</div>
          </div>
          <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
            <div className="text-xl font-bold text-[var(--accent-blue)]">
              {hiddenSignals.filter(s => s.severity === 'medium').length}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">Medium</div>
          </div>
          <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
            <div className="text-xl font-bold text-[var(--accent-cyan)]">
              {topSignalHorses.length}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">有暗號馬</div>
          </div>
        </div>

        {/* Signal cards grouped by horse */}
        {topSignalHorses.length > 0 ? (
          <div className="space-y-3">
            {topSignalHorses.map(({ no, signals, score }) => {
              const worst = signals.reduce((w, s) =>
                ['critical','high','medium','low'].indexOf(s.severity) < ['critical','high','medium','low'].indexOf(w) ? s.severity : w, 'low' as string);
              const runner = analysis?.runners.find(r => r.horse_no === no);
              const totalBoost = signals.reduce((a, s) => a + s.edge_boost, 0);

              return (
                <div
                  key={no}
                  className="rounded-lg p-3 transition-all"
                  style={{
                    borderLeft: `4px solid ${SEVERITY_BORDER[worst]}`,
                    background: worst === 'critical'
                      ? 'linear-gradient(135deg, rgba(239,68,68,0.1), rgba(239,68,68,0.02))'
                      : worst === 'high'
                      ? 'linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02))'
                      : 'var(--bg-secondary)',
                    boxShadow: SEVERITY_GLOW[worst as keyof typeof SEVERITY_GLOW],
                  }}
                >
                  {/* Horse header */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xl font-bold font-mono" style={{ color: SEVERITY_BORDER[worst] }}>
                        #{no}
                      </span>
                      <div>
                        <div className="font-bold text-sm">
                          {signals[0]?.horse_name}
                          {runner?.horse_name_ch && (
                            <span className="text-[var(--text-muted)] ml-1 text-xs">({runner.horse_name_ch})</span>
                          )}
                        </div>
                        {runner && (
                          <div className="text-[10px] text-[var(--text-muted)]">
                            J: {runner.jockey} · Dr: {runner.barrier} · Wt: {runner.weight} · Odds: {runner.win_odds.toFixed(1)}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-bold" style={{ color: totalBoost > 0 ? '#10b981' : '#ef4444' }}>
                        {totalBoost > 0 ? '+' : ''}{totalBoost.toFixed(1)}pt boost
                      </div>
                      <div className="text-[10px] text-[var(--text-muted)]">{signals.length} 個信號</div>
                    </div>
                  </div>

                  {/* Individual signals */}
                  <div className="space-y-1.5">
                    {signals.map((sig, i) => {
                      const catCfg = CATEGORY_CONFIG[sig.category] || CATEGORY_CONFIG.gear;
                      const CatIcon = catCfg.icon;
                      return (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <CatIcon className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: catCfg.color }} />
                          <div className="flex-1">
                            <span className="font-bold" style={{ color: SEVERITY_BORDER[sig.severity] }}>
                              {sig.title_ch}
                            </span>
                            <span className="text-[var(--text-muted)] ml-1.5">{sig.description}</span>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <div className="w-12 h-1.5 bg-[var(--bg-primary)] rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${sig.confidence * 100}%`,
                                  background: SEVERITY_BORDER[sig.severity],
                                }}
                              />
                            </div>
                            <span className="text-[10px] text-[var(--text-muted)] w-8 text-right">
                              {Math.round(sig.confidence * 100)}%
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-4">
            <Eye className="w-6 h-6 text-[var(--text-muted)] mx-auto mb-1" />
            <p className="text-[var(--text-muted)] text-sm">此場暫無暗號信號</p>
          </div>
        )}
      </div>

      {/* ── +EV Signal Board ── */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Zap className="w-5 h-5 text-[var(--value-bet)]" />
            +EV Signal Board
          </h2>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="bg-[var(--bg-secondary)] rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-[var(--value-bet)]">{valueBets.length}</div>
            <div className="text-xs text-[var(--text-muted)]">Value Bets</div>
          </div>
          <div className="bg-[var(--bg-secondary)] rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-[var(--smart-money)]">{alerts.length}</div>
            <div className="text-xs text-[var(--text-muted)]">Smart Money</div>
          </div>
          <div className="bg-[var(--bg-secondary)] rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-[var(--accent-cyan)]">
              {valueBets.length > 0
                ? `${Math.max(...valueBets.map(b => b.kelly_fraction)).toFixed(1)}%`
                : '0%'}
            </div>
            <div className="text-xs text-[var(--text-muted)]">Max Kelly%</div>
          </div>
        </div>
      </div>

      {sortedBets.length > 0 && (
        <div className="space-y-3">
          {sortedBets.map(bet => {
            const horseSignals = signalsByHorse[bet.horse_no] || [];
            const totalBoost = horseSignals.reduce((a, s) => a + s.edge_boost, 0);
            return (
              <div key={bet.horse_no} className="card signal-flash border-[var(--value-bet)]/30">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-bold font-mono text-[var(--value-bet)]">
                      #{bet.horse_no}
                    </span>
                    <div>
                      <div className="font-bold">
                        {bet.horse_name}
                        {bet.horse_name_ch && <span className="text-[var(--text-muted)] ml-1 text-sm">({bet.horse_name_ch})</span>}
                      </div>
                      <div className="text-xs text-[var(--text-muted)]">
                        J: {bet.jockey} · Dr: {bet.barrier} · Wt: {bet.weight}
                        {totalBoost > 0 && (
                          <span className="ml-2 text-[#f59e0b]">🔥 +{totalBoost.toFixed(1)}pt 暗號加成</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <span className="tag tag-green text-base px-3 py-1">
                    +EV {pct(bet.ev)}
                  </span>
                </div>

                <div className="grid grid-cols-5 gap-2 text-center">
                  <div>
                    <div className="text-lg font-bold font-mono text-[var(--accent-cyan)]">{pct(bet.p_true)}</div>
                    <div className="text-[10px] text-[var(--text-muted)]">P_true</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-[var(--accent-blue)]">{pct(bet.p_market)}</div>
                    <div className="text-[10px] text-[var(--text-muted)]">P_market</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono">{bet.win_odds.toFixed(1)}</div>
                    <div className="text-[10px] text-[var(--text-muted)]">Win Odds</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-[var(--accent-green)]">+{pct(bet.edge)}</div>
                    <div className="text-[10px] text-[var(--text-muted)]">Edge</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold font-mono text-[var(--accent-yellow)]">{bet.kelly_fraction.toFixed(1)}%</div>
                    <div className="text-[10px] text-[var(--text-muted)]">Kelly (⅓)</div>
                  </div>
                </div>

                {/* Signal badges for this horse */}
                {horseSignals.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {horseSignals.map((sig, i) => {
                      const catCfg = CATEGORY_CONFIG[sig.category] || CATEGORY_CONFIG.gear;
                      return (
                        <span
                          key={i}
                          className="text-[10px] px-1.5 py-0.5 rounded font-bold"
                          style={{
                            background: `${SEVERITY_BORDER[sig.severity]}20`,
                            color: SEVERITY_BORDER[sig.severity],
                            border: `1px solid ${SEVERITY_BORDER[sig.severity]}40`,
                          }}
                        >
                          {sig.title_ch}
                        </span>
                      );
                    })}
                  </div>
                )}

                <div className="mt-2">
                  <div className="h-2 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.min(bet.kelly_fraction * 5, 100)}%`,
                        background: 'linear-gradient(90deg, var(--accent-green), var(--accent-yellow))',
                      }}
                    />
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
                    Suggested stake: {bet.kelly_fraction.toFixed(1)}% of bankroll (⅓ Kelly)
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {alerts.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-bold flex items-center gap-2 mb-3">
            <Bell className="w-4 h-4 text-[var(--smart-money)]" />
            Smart Money Alerts
          </h3>
          <div className="space-y-2">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className="flex items-center gap-3 p-2 rounded-lg bg-[var(--bg-secondary)]"
                style={{ borderLeft: `3px solid ${severityColor(alert.severity)}` }}
              >
                {alert.alert_type === 'odds_drop' ? (
                  <TrendingDown className="w-4 h-4" style={{ color: severityColor(alert.severity) }} />
                ) : (
                  <DollarSign className="w-4 h-4" style={{ color: severityColor(alert.severity) }} />
                )}
                <div className="flex-1">
                  <div className="text-sm font-semibold">#{alert.horse_no} {alert.horse_name}</div>
                  <div className="text-xs text-[var(--text-muted)]">{alert.description}</div>
                </div>
                <span className={`tag ${alert.severity === 'high' ? 'tag-red' : alert.severity === 'medium' ? 'tag-yellow' : 'tag-blue'}`}>
                  {alert.severity.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {analysis && (
        <div className="card">
          <h3 className="text-sm font-bold text-[var(--text-secondary)] mb-2">
            Full Runner Grid — Race {raceNo}
          </h3>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Horse</th>
                  <th>Dr</th>
                  <th>Odds</th>
                  <th>P_true</th>
                  <th>P_mkt</th>
                  <th>EV</th>
                  <th>Edge</th>
                  <th>Kelly</th>
                  <th>暗號</th>
                </tr>
              </thead>
              <tbody>
                {analysis.runners.map(r => {
                  const horseSigs = signalsByHorse[r.horse_no] || [];
                  return (
                    <tr key={r.horse_no} className={r.is_value_bet ? 'bg-[var(--accent-green)]/5' : ''}>
                      <td className="font-mono">{r.horse_no}</td>
                      <td>
                        {r.horse_name}
                        {r.hot_favourite && <span className="ml-1 text-[10px] text-[var(--accent-yellow)]">★</span>}
                        {r.strong_contender && <span className="ml-1 text-[10px] text-[var(--accent-cyan)]" title="穩膽：勝率高但EV可能為負">🏆</span>}
                        {r.superhorse && <span className="ml-1 text-[10px] font-bold" style={{color: '#fbbf24', textShadow: '0 0 8px rgba(251,191,36,0.5)'}} title="超級馬王：近績極度出色，超越正常分析框架">👑</span>}
                        {r.barrier_versatile && <span className="ml-1 text-[10px] text-[var(--accent-green)] font-medium px-1 py-0.5 rounded" style={{background: 'rgba(16,185,129,0.15)'}} title="檔位無影響：近績多次前四">檔位無影響</span>}
                      </td>
                      <td className="font-mono">{r.barrier}</td>
                      <td className="font-mono font-bold">{r.win_odds.toFixed(1)}</td>
                      <td className="font-mono text-[var(--accent-cyan)]">{pct(r.p_true)}</td>
                      <td className="font-mono text-[var(--accent-blue)]">{pct(r.p_market)}</td>
                      <td className="font-mono font-bold" style={{ color: evColor(r.ev) }}>
                        {r.ev > 0 ? '+' : ''}{pct(r.ev)}
                        {r.ev_confidence === 'low' && <span className="text-[9px] text-[var(--text-muted)] ml-0.5">⚠</span>}
                      </td>
                      <td className="font-mono" style={{ color: r.edge > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                        {r.edge > 0 ? '+' : ''}{pct(r.edge)}
                      </td>
                      <td className="font-mono text-[var(--accent-yellow)]">
                        {r.kelly_fraction > 0 ? `${r.kelly_fraction.toFixed(1)}%` : '—'}
                      </td>
                      <td>
                        {horseSigs.length > 0 ? (
                          <div className="flex gap-0.5">
                            {horseSigs.slice(0, 3).map((sig, i) => (
                              <span
                                key={i}
                                className="w-2 h-2 rounded-full inline-block"
                                style={{ background: SEVERITY_BORDER[sig.severity] }}
                                title={sig.title_ch}
                              />
                            ))}
                            {horseSigs.length > 3 && (
                              <span className="text-[10px] text-[var(--text-muted)]">+{horseSigs.length - 3}</span>
                            )}
                          </div>
                        ) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
