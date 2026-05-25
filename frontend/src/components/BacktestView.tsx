import { useState, useEffect, useCallback } from 'react';
import { getHistoricalResults, getRaceMeetings, getLiveAnalysis } from '../utils/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { History, TrendingUp, TrendingDown, Target, Loader2, CalendarDays, RefreshCw } from 'lucide-react';

interface RaceResult {
  position: number;
  horse_no: number;
  horse_name: string;
  jockey: string;
  barrier: number;
  win_odds: number;
  lbw: string;
  running_positions: string;
}

interface BacktestRunner {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
  win_odds: number;
  p_true: number;
  ev: number;
  edge: number;
  kelly_fraction: number;
  is_value_bet: boolean;
}

interface BacktestRace {
  race_no: number;
  race_name: string;
  predicted: BacktestRunner[];
  result: RaceResult[];
  hit: boolean;  // did a value bet win?
  profit: number; // P&L
  stakes: { horse_no: number; stake: number; odds: number }[];
}

export default function BacktestView() {
  const [date, setDate] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [backtestRaces, setBacktestRaces] = useState<BacktestRace[]>([]);
  const [bankroll, setBankroll] = useState(1000);

  // Default to yesterday
  useEffect(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    setDate(d.toISOString().split('T')[0]);
  }, []);

  const runBacktest = useCallback(async () => {
    if (!date) return;
    setLoading(true);
    setError('');
    setBacktestRaces([]);

    try {
      // 1. Fetch race results
      const resultsData = await getHistoricalResults(date);
      const raceKeys = Object.keys(resultsData.races || {});
      if (raceKeys.length === 0) {
        setError('該日無賽果資料');
        setLoading(false);
        return;
      }

      // 2. For each completed race, fetch what our model would have predicted
      const venueCode = resultsData.venue || '';
      const races: BacktestRace[] = [];
      let failedAnalysis = 0;

      for (const raceNoStr of raceKeys.sort((a, b) => parseInt(a) - parseInt(b))) {
        await new Promise(resolve => setTimeout(resolve, 100));
        const raceNo = parseInt(raceNoStr);
        const resultRunners: RaceResult[] = resultsData.races[raceNoStr] || [];
        const winner = resultRunners.find(r => r.position === 1);

        // Try to get analysis for this race
        try {
          const analysis = await getLiveAnalysis(raceNo, date, venueCode);
          const valueBets = analysis.runners.filter(r => r.is_value_bet);

          // Calculate stakes using ⅓ Kelly
          const stakes = valueBets.map(r => ({
            horse_no: r.horse_no,
            stake: Math.round(bankroll * r.kelly_fraction / 100),
            odds: r.win_odds,
          }));
          const totalStake = stakes.reduce((s, b) => s + b.stake, 0);

          // Calculate profit
          let profit = -totalStake; // start with loss
          if (winner) {
            const winningBet = stakes.find(s => s.horse_no === winner.horse_no);
            if (winningBet) {
              profit += winningBet.stake * winningBet.odds;
            }
          }

          races.push({
            race_no: raceNo,
            race_name: analysis.race_name_ch || analysis.race_name_en || `第${raceNo}場`,
            predicted: analysis.runners,
            result: resultRunners,
            hit: stakes.some(s => s.horse_no === winner?.horse_no),
            profit,
            stakes,
          });
        } catch {
          // Analysis not available for this historical race (API only provides future/current data)
          failedAnalysis++;
          races.push({
            race_no: raceNo,
            race_name: `第${raceNo}場`,
            predicted: [],
            result: resultRunners,
            hit: false,
            profit: 0,
            stakes: [],
          });
        }
      }

      setBacktestRaces(races.sort((a, b) => a.race_no - b.race_no));
      
      // Show warning if some races couldn't be analyzed
      if (failedAnalysis > 0) {
        setError(`⚠️ 注意：${failedAnalysis}場賽事無法獲取模型預測（歷史賽事只顯示賽果，不包含當時的賠率與模型數據）`);
      }
    } catch (e: any) {
      setError(e.message || '回測失敗');
    } finally {
      setLoading(false);
    }
  }, [date, bankroll]);

  // Summary stats
  const totalProfit = backtestRaces.reduce((s, r) => s + r.profit, 0);
  const totalBets = backtestRaces.filter(r => r.stakes.length > 0).length;
  const wins = backtestRaces.filter(r => r.hit).length;
  const hitRate = totalBets > 0 ? (wins / totalBets * 100) : 0;
  const valueBetCount = backtestRaces.reduce((s, r) => s + r.stakes.length, 0);

  const chartData = backtestRaces
    .filter(r => r.stakes.length > 0)
    .map(r => ({
      name: `R${r.race_no}`,
      profit: r.profit,
      hit: r.hit,
    }));

  const cumulativeData = chartData.reduce((acc: { name: string; cumProfit: number }[], r, i) => {
    const prev = acc.length > 0 ? acc[acc.length - 1].cumProfit : 0;
    acc.push({ name: r.name, cumProfit: prev + r.profit });
    return acc;
  }, []);

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <History className="w-5 h-5 text-[var(--accent-cyan)]" />
          歷史回測
        </h2>
      </div>

      {/* Date + Bankroll input */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-[var(--accent-cyan)]" />
            <input
              type="text"
              value={date}
              onChange={e => setDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              style={{
                padding: '10px 14px',
                backgroundColor: '#1e293b',
                border: '1px solid #475569',
                borderRadius: '8px',
                color: '#f1f5f9',
                fontSize: '14px',
                width: '140px',
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--text-muted)]">本金</span>
            <input
              type="number"
              value={bankroll}
              onChange={e => setBankroll(Math.max(0, parseInt(e.target.value) || 0))}
              className="w-24 px-2 py-1.5 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg text-[var(--text-primary)] font-mono text-sm focus:outline-none focus:border-[var(--accent-cyan)]"
            />
          </div>
          <button
            onClick={runBacktest}
            disabled={loading || !date}
            className="px-4 py-1.5 bg-[var(--accent-cyan)] text-white text-sm rounded-lg hover:opacity-90 transition disabled:opacity-50 flex items-center gap-1"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            執行回測
          </button>
        </div>
        {/* Quick date presets */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--text-muted)]">快捷：</span>
          {['2026-05-24', '2026-05-21', '2026-05-18'].map(d => (
            <button
              key={d}
              onClick={() => setDate(d)}
              style={{
                padding: '4px 12px',
                backgroundColor: date === d ? '#06b6d4' : '#334155',
                color: 'white',
                fontSize: '12px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {d.slice(5)}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="text-center py-8">
          <Loader2 className="w-8 h-8 text-[var(--accent-cyan)] animate-spin mx-auto mb-2" />
          <p className="text-sm text-[var(--text-muted)]">正在載入賽果並比對模型預測...</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">每場賽事需獨立分析，請稍候</p>
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Summary stats */}
      {backtestRaces.length > 0 && !loading && (
        <>
          <div className="grid grid-cols-5 gap-2">
            <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
              <div className="text-lg font-bold text-[var(--accent-cyan)]">{backtestRaces.length}</div>
              <div className="text-[10px] text-[var(--text-muted)]">總場次</div>
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
              <div className="text-lg font-bold text-[var(--accent-yellow)]">{valueBetCount}</div>
              <div className="text-[10px] text-[var(--text-muted)]">價值投注數</div>
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
              <div className="text-lg font-bold text-[var(--accent-green)]">{hitRate.toFixed(0)}%</div>
              <div className="text-[10px] text-[var(--text-muted)]">命中率</div>
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
              <div className={`text-lg font-bold ${totalProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(0)}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">總盈虧</div>
            </div>
            <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
              <div className={`text-lg font-bold ${totalProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                {bankroll > 0 ? (totalProfit / bankroll * 100).toFixed(1) : '0'}%
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">回報率</div>
            </div>
          </div>

          {/* Per-race chart */}
          {chartData.length > 0 && (
            <div>
              <h3 className="text-xs font-bold text-[var(--text-secondary)] mb-2">每場盈虧</h3>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} barCategoryGap={4}>
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                    <Tooltip
                      contentStyle={{ background: '#1a2332', border: '1px solid #2a3a52', borderRadius: 6 }}
                      labelStyle={{ color: '#e2e8f0' }}
                      formatter={(value: number) => [`$${value}`, '盈虧']}
                    />
                    <Bar dataKey="profit" radius={[3, 3, 0, 0]}>
                      {chartData.map((entry, i) => (
                        <Cell key={i} fill={entry.profit >= 0 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Cumulative chart */}
          {cumulativeData.length > 1 && (
            <div>
              <h3 className="text-xs font-bold text-[var(--text-secondary)] mb-2">累計盈虧</h3>
              <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={cumulativeData} barCategoryGap={4}>
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                    <Tooltip
                      contentStyle={{ background: '#1a2332', border: '1px solid #2a3a52', borderRadius: 6 }}
                      labelStyle={{ color: '#e2e8f0' }}
                      formatter={(value: number) => [`$${value}`, '累計']}
                    />
                    <Bar dataKey="cumProfit" radius={[3, 3, 0, 0]}>
                      {cumulativeData.map((entry, i) => (
                        <Cell key={i} fill={entry.cumProfit >= 0 ? '#06b6d4' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Per-race detail */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold text-[var(--text-secondary)]">逐場結果</h3>
            {backtestRaces.map(race => {
              const winner = race.result.find(r => r.position === 1);
              return (
                <div
                  key={race.race_no}
                  className="p-3 bg-[var(--bg-secondary)] rounded-lg"
                  style={{
                    borderLeft: `4px solid ${race.hit ? '#10b981' : race.stakes.length > 0 ? '#ef4444' : '#64748b'}`,
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm">第{race.race_no}場</span>
                      <span className="text-xs text-[var(--text-muted)]">{race.race_name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      {race.stakes.length > 0 && (
                        <>
                          <span className={`text-sm font-bold ${race.profit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                            {race.profit >= 0 ? '+' : ''}${race.profit.toFixed(0)}
                          </span>
                          {race.hit ? (
                            <Target className="w-4 h-4 text-[var(--accent-green)]" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-[var(--accent-red)]" />
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  {/* Winner info */}
                  {winner && (
                    <div className="text-xs text-[var(--text-muted)]">
                      冠軍：#{winner.horse_no} {winner.horse_name}
                      {winner.win_odds > 0 && ` (${winner.win_odds}倍)`}
                      {winner.barrier > 0 && ` · 檔${winner.barrier}`}
                      {winner.jockey && ` · ${winner.jockey}`}
                    </div>
                  )}

                  {/* Value bets for this race */}
                  {race.stakes.length > 0 ? (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {race.stakes.map(s => {
                        const isWinner = s.horse_no === winner?.horse_no;
                        const pred = race.predicted.find(p => p.horse_no === s.horse_no);
                        return (
                          <span
                            key={s.horse_no}
                            className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                              isWinner
                                ? 'bg-green-500/20 text-green-400'
                                : 'bg-red-500/10 text-red-400'
                            }`}
                          >
                            #{s.horse_no} ${s.stake}@{s.odds.toFixed(1)}
                            {pred && ` EV${pred.ev > 0 ? '+' : ''}${pred.ev.toFixed(1)}`}
                            {isWinner ? ' ✓命中' : ' ✗'}
                          </span>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-[10px] text-[var(--text-muted)] mt-1">模型未偵測到價值投注</div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
