import { useState, useEffect } from 'react';
import type { RaceMeeting } from './utils/types';
import RaceOverview from './components/RaceOverview';
import ModelCalculator from './components/ModelCalculator';
import ValueBetSignals from './components/ValueBetSignals';
import BetCalculator from './components/BetCalculator';
import BacktestView from './components/BacktestView';
import { computeLocalAnalysis, getLiveAnalysis } from './utils/api';
import { Activity, Calculator, History, Eye } from 'lucide-react';

interface AnalysisData {
  runners: any[];
  pace_forecast: any;
  smart_money_alerts: any[];
  hidden_signals?: any[];
  value_bet_count?: number;
}

type TabMode = 'live' | 'backtest';

export default function App() {
  const [selectedMeeting, setSelectedMeeting] = useState<RaceMeeting | null>(null);
  const [selectedRaceNo, setSelectedRaceNo] = useState<number>(1);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [tab, setTab] = useState<TabMode>('live');

  const handleSelectRace = (meeting: RaceMeeting, raceNo: number) => {
    setSelectedMeeting(meeting);
    setSelectedRaceNo(raceNo);
  };

  // Load analysis when meeting/race changes
  useEffect(() => {
    if (!selectedMeeting || !selectedRaceNo) return;

    const loadAnalysis = async () => {
      try {
        const data = await getLiveAnalysis(selectedRaceNo, selectedMeeting.date, selectedMeeting.venueCode);
        setAnalysis({
          runners: data.runners,
          pace_forecast: data.pace_forecast,
          smart_money_alerts: data.smart_money_alerts,
          hidden_signals: (data as any).hidden_signals || [],
          value_bet_count: data.value_bet_count,
        });
      } catch {
        // Fallback: client-side
        const race = selectedMeeting.races?.find((r: any) => r.no === selectedRaceNo);
        if (race?.runners) {
          const result = computeLocalAnalysis(race.runners, []);
          setAnalysis({
            runners: result.runners,
            pace_forecast: result.pace_forecast,
            smart_money_alerts: result.smart_money_alerts,
          });
        }
      }
    };

    loadAnalysis();
  }, [selectedMeeting, selectedRaceNo]);

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="bg-[var(--bg-secondary)] border-b border-[var(--border)] px-6 py-3">
        <div className="flex items-center justify-between max-w-[1800px] mx-auto">
          <div className="flex items-center gap-3">
            <Activity className="w-6 h-6 text-[var(--accent-cyan)]" />
            <div>
              <h1 className="text-lg font-bold tracking-tight">HK Racing Quant</h1>
              <p className="text-[10px] text-[var(--text-muted)] -mt-0.5">
                香港賽馬量化分析系統 · +EV Value Bet Detector
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
            <span>API: <span className={analysis ? 'text-[var(--accent-green)]' : 'text-[var(--accent-yellow)]'}>●</span></span>
            <span>Takeout: 17.5%</span>
            <span>Kelly: ⅓</span>
          </div>
        </div>
      </header>

      {/* Tab bar */}
      <div className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <div className="max-w-[1800px] mx-auto flex gap-0">
          <button
            onClick={() => setTab('live')}
            className={`flex items-center gap-2 px-6 py-2.5 text-sm font-medium border-b-2 transition ${
              tab === 'live'
                ? 'border-[var(--accent-cyan)] text-[var(--accent-cyan)]'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <Eye className="w-4 h-4" /> 即時分析
          </button>
          <button
            onClick={() => setTab('backtest')}
            className={`flex items-center gap-2 px-6 py-2.5 text-sm font-medium border-b-2 transition ${
              tab === 'backtest'
                ? 'border-[var(--accent-cyan)] text-[var(--accent-cyan)]'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <History className="w-4 h-4" /> 歷史回測
          </button>
        </div>
      </div>

      {tab === 'live' ? (
        <main className="max-w-[1800px] mx-auto p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-3 space-y-4">
            <div className="sticky top-4">
              <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
                Panel A · 賽事面板
              </div>
              <RaceOverview
                onSelectRace={handleSelectRace}
                selectedMeeting={selectedMeeting}
                selectedRaceNo={selectedRaceNo}
              />
            </div>
          </div>

          <div className="lg:col-span-5 space-y-4">
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Panel B · 量化模型
            </div>
            <ModelCalculator meeting={selectedMeeting} raceNo={selectedRaceNo} />
          </div>

          <div className="lg:col-span-4 space-y-4">
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Panel C · +EV 信號 & 投注
            </div>
            <ValueBetSignals
              meeting={selectedMeeting}
              raceNo={selectedRaceNo}
              analysis={analysis}
            />
            <BetCalculator
              runners={analysis?.runners || []}
              raceNo={selectedRaceNo}
            />
          </div>
        </main>
      ) : (
        <main className="max-w-[1200px] mx-auto p-4">
          <BacktestView />
        </main>
      )}

      <footer className="border-t border-[var(--border)] py-3 px-6 text-center text-xs text-[var(--text-muted)]">
        HK Racing Quant v0.3 · Data via backend proxy from HKJC GraphQL API · For educational purposes only · Not financial advice
      </footer>
    </div>
  );
}
