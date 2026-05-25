import { useState, useMemo } from 'react';
import { pct, evColor } from '../utils/helpers';
import { Wallet, Coins, TrendingUp, AlertTriangle, Info, AlertCircle } from 'lucide-react';

interface RunnerRow {
  horse_no: number;
  horse_name: string;
  horse_name_ch?: string;
  win_odds: number;
  p_true: number;
  p_market?: number;
  ev?: number;
  edge?: number;
  kelly_fraction?: number;
  is_value_bet?: boolean;
  ev_confidence?: string;
  strong_contender?: boolean;
  superhorse?: boolean;
}

interface Props {
  runners: RunnerRow[];
  raceNo: number;
}

export default function BetCalculator({ runners, raceNo }: Props) {
  const [bankroll, setBankroll] = useState<number>(1000);
  const [mode, setMode] = useState<'value' | 'all' | 'kelly'>('value');
  const [showInfo, setShowInfo] = useState(false);

  // Check if odds are available (pre-race mode)
  const totalOdds = useMemo(() => runners.reduce((sum, r) => sum + r.win_odds, 0), [runners]);
  const hasOdds = runners.length > 0 && totalOdds > 0;

  // Filter runners based on mode (only if odds available)
  const filteredRunners = useMemo(() => {
    if (!hasOdds) return [];
    switch (mode) {
      case 'value':
        return runners.filter(r => r.is_value_bet);
      case 'all':
        return runners.filter(r => (r.kelly_fraction || 0) > 0);
      case 'kelly':
        return runners.filter(r => (r.kelly_fraction || 0) > 0.5); // Kelly > 0.5%
    }
  }, [runners, mode, hasOdds]);

  // Calculate stakes (only if odds available)
  const stakes = useMemo(() => {
    if (!hasOdds) return [];
    return filteredRunners.map(r => {
      const kellyPct = (r.kelly_fraction || 0) / 100;
      const stake = Math.round(bankroll * kellyPct);
      const potentialReturn = stake * r.win_odds;
      const expectedProfit = stake * ((r.ev || 0) / 100);
      return {
        ...r,
        stake,
        potentialReturn: Math.round(potentialReturn),
        expectedProfit: Math.round(expectedProfit * 100) / 100,
      };
    });
  }, [filteredRunners, bankroll, hasOdds]);

  const totalStake = stakes.reduce((sum, s) => sum + s.stake, 0);
  const totalExpectedProfit = stakes.reduce((sum, s) => sum + s.expectedProfit, 0);
  const bankrollPct = bankroll > 0 ? (totalStake / bankroll * 100) : 0;

  if (runners.length === 0) {
    return null;
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Wallet className="w-5 h-5 text-[var(--accent-cyan)]" />
          投注計算器 — 第{raceNo}場
        </h2>
        <button
          onClick={() => setShowInfo(!showInfo)}
          className="text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition"
        >
          <Info className="w-4 h-4" />
        </button>
      </div>

      {showInfo && (
        <div className="p-3 bg-[var(--bg-secondary)] rounded-lg text-xs text-[var(--text-secondary)] space-y-1">
          <p>📐 <b>Kelly 公式</b>：f* = (p×b - q) / b，其中 p = P_true，b = 賠率-1，q = 1-p</p>
          <p>🔒 使用 <b>⅓ Kelly</b>（保守版），降低注碼波動</p>
          <p>⚠️ 僅下注 +EV 馬匹，長期期望值為正不代表每場必贏</p>
          <p>💡 建議本金為你願意完全虧損的金額，賽馬投注有風險</p>
        </div>
      )}

      {!hasOdds ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <AlertCircle className="w-8 h-8 text-[var(--accent-yellow)] mb-2" />
          <p className="text-[var(--text-secondary)]">賠率尚未公佈</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            賽前約 30 分鐘開始受注，請稍後再來
          </p>
          <p className="text-xs text-[var(--accent-cyan)] mt-2">
            👆 此時可參考「量化模型」的勝率排名
          </p>
        </div>
      ) : (
        <>
          {/* Bankroll input */}
          <div className="flex items-center gap-3">
            <label className="text-sm text-[var(--text-secondary)] whitespace-nowrap flex items-center gap-1">
              <Coins className="w-4 h-4 text-[var(--accent-yellow)]" />
              本金 (HKD)
            </label>
            <input
              type="number"
              value={bankroll}
              onChange={e => setBankroll(Math.max(0, parseInt(e.target.value) || 0))}
              className="flex-1 px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg text-[var(--text-primary)] font-mono text-sm focus:outline-none focus:border-[var(--accent-cyan)]"
              min={0}
              step={100}
            />
            <div className="flex gap-1">
              {[500, 1000, 2000, 5000].map(v => (
                <button
                  key={v}
                  onClick={() => setBankroll(v)}
                  className={`text-xs px-2 py-1 rounded transition ${
                    bankroll === v
                      ? 'bg-[var(--accent-cyan)] text-white'
                      : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  ${v}
                </button>
              ))}
            </div>
          </div>

          {/* Mode selector */}
          <div className="flex gap-2">
            {[
              { key: 'value' as const, label: '+EV 價值投注' },
              { key: 'kelly' as const, label: 'Kelly > 0.5%' },
              { key: 'all' as const, label: '所有正 Kelly' },
            ].map(m => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                className={`flex-1 text-xs py-2 rounded-lg transition ${
                  mode === m.key
                    ? 'bg-[var(--accent-cyan)] text-white font-bold'
                    : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {/* Summary */}
          {stakes.length > 0 ? (
            <>
              <div className="grid grid-cols-4 gap-2">
                <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-[var(--accent-cyan)]">{stakes.length}</div>
                  <div className="text-[10px] text-[var(--text-muted)]">下注馬數</div>
                </div>
                <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-[var(--accent-yellow)]">${totalStake}</div>
                  <div className="text-[10px] text-[var(--text-muted)]">總下注額</div>
                </div>
                <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
                  <div className={`text-lg font-bold ${totalExpectedProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                    {totalExpectedProfit >= 0 ? '+' : ''}${totalExpectedProfit.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)]">期望利潤</div>
                </div>
                <div className="bg-[var(--bg-secondary)] rounded-lg p-2 text-center">
                  <div className={`text-lg font-bold ${bankrollPct > 20 ? 'text-[var(--accent-red)]' : bankrollPct > 10 ? 'text-[var(--accent-yellow)]' : 'text-[var(--accent-green)]'}`}>
                    {bankrollPct.toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)]">本金佔比</div>
                </div>
              </div>

              {/* Risk warning */}
              {bankrollPct > 15 && (
                <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/20 rounded-lg text-xs text-red-400">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  總下注佔本金 {bankrollPct.toFixed(1)}%，建議控制在 15% 以下以分散風險
                </div>
              )}

              {/* Stake table */}
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>馬匹</th>
                      <th>賠率</th>
                      <th>Kelly%</th>
                      <th>建議注碼</th>
                      <th>潛在回報</th>
                      <th>期望利潤</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stakes
                      .sort((a, b) => b.kelly_fraction! - a.kelly_fraction!)
                      .map(s => (
                        <tr key={s.horse_no}>
                          <td className="font-mono">{s.horse_no}</td>
                          <td>
                            <span className="font-semibold">{s.horse_name}</span>
                            {s.superhorse && <span className="ml-1 text-xs" style={{ color: '#fbbf24' }}>👑</span>}
                            {s.ev_confidence === 'low' && <span className="ml-1 text-[10px] text-[var(--accent-red)]">⚠低信度</span>}
                          </td>
                          <td className="font-mono font-bold">{s.win_odds.toFixed(1)}</td>
                          <td className="font-mono text-[var(--accent-yellow)]">{s.kelly_fraction!.toFixed(1)}%</td>
                          <td className="font-mono font-bold text-[var(--accent-cyan)]">${s.stake}</td>
                          <td className="font-mono">${s.potentialReturn}</td>
                          <td className={`font-mono ${s.expectedProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                            {s.expectedProfit >= 0 ? '+' : ''}${s.expectedProfit.toFixed(1)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-[var(--border)]">
                      <td colSpan={3} className="text-right text-sm font-bold text-[var(--text-secondary)]">合計</td>
                      <td className="font-mono font-bold text-[var(--accent-cyan)]">${totalStake}</td>
                      <td className="font-mono text-[var(--text-muted)]">—</td>
                      <td className={`font-mono font-bold ${totalExpectedProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                        {totalExpectedProfit >= 0 ? '+' : ''}${totalExpectedProfit.toFixed(1)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Scenario analysis */}
              <div className="p-3 bg-[var(--bg-secondary)] rounded-lg space-y-2">
                <h3 className="text-xs font-bold text-[var(--text-secondary)] flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" /> 情景分析
                </h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-[var(--text-muted)]">最佳情景（最高回報命中）：</span>
                    <span className="text-[var(--accent-green)] font-bold ml-1">
                      +${Math.max(...stakes.map(s => s.potentialReturn - totalStake), 0)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">最差情景（全輸）：</span>
                    <span className="text-[var(--accent-red)] font-bold ml-1">-${totalStake}</span>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">EV 期望回報（長期均值）：</span>
                    <span className={`font-bold ml-1 ${totalExpectedProfit >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                      {totalExpectedProfit >= 0 ? '+' : ''}${totalExpectedProfit.toFixed(1)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">至少一匹命中概率：</span>
                    <span className="text-[var(--accent-cyan)] font-bold ml-1">
                      {(stakes.reduce((acc, s) => acc + s.p_true / 100, 0) * 100).toFixed(1)}%
                      <span className="text-[var(--text-muted)] font-normal ml-1">（近似）</span>
                    </span>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-4 text-[var(--text-muted)] text-sm">
              此場暫無符合條件的投注建議
            </div>
          )}
        </>
      )}
    </div>
  );
}
