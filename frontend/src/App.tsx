import { useState, useEffect, useCallback, useRef } from 'react';
import type { RaceMeeting } from './utils/types';
import RaceOverview from './components/RaceOverview';
import ModelCalculator from './components/ModelCalculator';
import ValueBetSignals from './components/ValueBetSignals';
import BetCalculator from './components/BetCalculator';
import BacktestView from './components/BacktestView';
import { computeLocalAnalysis, getLiveAnalysis } from './utils/api';
import { Activity, Eye, History, BarChart3, Zap, Wallet, Timer } from 'lucide-react';

interface AnalysisData {
  runners: any[];
  pace_forecast: any;
  smart_money_alerts: any[];
  hidden_signals?: any[];
  value_bet_count?: number;
}

type TopTab = 'live' | 'backtest';
type MobilePanel = 'race' | 'model' | 'signals' | 'bet';

export default function App() {
  const [selectedMeeting, setSelectedMeeting] = useState<RaceMeeting | null>(null);
  const [selectedRaceNo, setSelectedRaceNo] = useState<number>(1);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [topTab, setTopTab] = useState<TopTab>('live');
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>('race');
  const [lastRefresh, setLastRefresh] = useState<number>(0);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleSelectRace = (meeting: RaceMeeting, raceNo: number) => {
    setSelectedMeeting(meeting);
    setSelectedRaceNo(raceNo);
  };

  // Load analysis when meeting/race changes
  const loadAnalysis = useCallback(async () => {
    if (!selectedMeeting || !selectedRaceNo) return;
    try {
      const data = await getLiveAnalysis(selectedRaceNo, selectedMeeting.date, selectedMeeting.venueCode);
      setAnalysis({
        runners: data.runners,
        pace_forecast: data.pace_forecast,
        smart_money_alerts: data.smart_money_alerts,
        hidden_signals: (data as any).hidden_signals || [],
        value_bet_count: data.value_bet_count,
      });
      setLastRefresh(Date.now());
    } catch {
      // Fallback to client-side calculation if API fails
      const race = selectedMeeting.races?.find((r: any) => r.no === selectedRaceNo);
      if (race?.runners) {
        const result = computeLocalAnalysis(race.runners, []);
        setAnalysis({
          runners: result.runners,
          pace_forecast: result.pace_forecast,
          smart_money_alerts: result.smart_money_alerts,
        });
      }
      setLastRefresh(Date.now());
    }
  }, [selectedMeeting, selectedRaceNo]);

  useEffect(() => {
    loadAnalysis();
  }, [loadAnalysis]);

  // Auto-refresh every 30s when a meeting is selected
  useEffect(() => {
    if (selectedMeeting) {
    refreshTimerRef.current = setInterval(() => {
      // 只在賽事狀態是 RUNNING 時才刷新
      const currentRace = selectedMeeting.races?.find(r => r.no === selectedRaceNo);
      if (currentRace?.status === 'RUNNING' || currentRace?.status === 'STARTED') {
        loadAnalysis();
      }
    }, 60000);  // 1分鐘
  }
    return () => {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    };
  }, [selectedMeeting, loadAnalysis]);

  const secondsSinceRefresh = lastRefresh > 0 ? Math.floor((Date.now() - lastRefresh) / 1000) : 0;

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="bg-[var(--bg-secondary)] border-b border-[var(--border)] px-4 sm:px-6 py-3">
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
          <div className="flex items-center gap-2 sm:gap-4 text-xs text-[var(--text-muted)]">
            {lastRefresh > 0 && selectedMeeting && (
              <span className="hidden sm:flex items-center gap-1">
                <Timer className="w-3 h-3" />
                {secondsSinceRefresh < 60 ? `${secondsSinceRefresh}s前更新` : '更新中...'}
              </span>
            )}
            <span>API: <span className={analysis ? 'text-[var(--accent-green)]' : 'text-[var(--accent-yellow)]'}>●</span></span>
            <span className="hidden sm:inline">Takeout: 17.5%</span>
            <span className="hidden sm:inline">Kelly: ⅓</span>
          </div>
        </div>
      </header>

      {/* Top tab bar */}
      <div className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <div className="max-w-[1800px] mx-auto flex gap-0">
          <button
            onClick={() => setTopTab('live')}
            className={`flex items-center gap-2 px-4 sm:px-6 py-2.5 text-sm font-medium border-b-2 transition ${
              topTab === 'live'
                ? 'border-[var(--accent-cyan)] text-[var(--accent-cyan)]'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <Eye className="w-4 h-4" /> 即時分析
          </button>
          <button
            onClick={() => setTopTab('backtest')}
            className={`flex items-center gap-2 px-4 sm:px-6 py-2.5 text-sm font-medium border-b-2 transition ${
              topTab === 'backtest'
                ? 'border-[var(--accent-cyan)] text-[var(--accent-cyan)]'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <History className="w-4 h-4" /> 歷史回測
          </button>
        </div>
      </div>

      {topTab === 'live' ? (
        <>
          {/* Desktop: 3-column layout */}
          <main className="hidden lg:block max-w-[1800px] mx-auto p-4 grid grid-cols-12 gap-4">
            <div className="col-span-3 space-y-4">
              <div className="sticky top-4">
                <RaceOverview
                  onSelectRace={handleSelectRace}
                  selectedMeeting={selectedMeeting}
                  selectedRaceNo={selectedRaceNo}
                />
              </div>
            </div>
            <div className="col-span-5 space-y-4">
              <ModelCalculator meeting={selectedMeeting} raceNo={selectedRaceNo} />
            </div>
            <div className="col-span-4 space-y-4">
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

          {/* Mobile: tab-based single panel */}
          <main className="lg:hidden">
            {/* Mobile panel content */}
            <div className="p-3">
              {mobilePanel === 'race' && (
                <RaceOverview
                  onSelectRace={handleSelectRace}
                  selectedMeeting={selectedMeeting}
                  selectedRaceNo={selectedRaceNo}
                />
              )}
              {mobilePanel === 'model' && (
                <ModelCalculator meeting={selectedMeeting} raceNo={selectedRaceNo} />
              )}
              {mobilePanel === 'signals' && (
                <ValueBetSignals
                  meeting={selectedMeeting}
                  raceNo={selectedRaceNo}
                  analysis={analysis}
                />
              )}
              {mobilePanel === 'bet' && (
                <BetCalculator
                  runners={analysis?.runners || []}
                  raceNo={selectedRaceNo}
                />
              )}
            </div>

            {/* Mobile bottom tab bar */}
            <div className="fixed bottom-0 left-0 right-0 bg-[var(--bg-secondary)] border-t border-[var(--border)] z-50">
              <div className="grid grid-cols-4">
                {[
                  { key: 'race' as MobilePanel, icon: BarChart3, label: '賽事' },
                  { key: 'model' as MobilePanel, icon: Zap, label: '模型' },
                  { key: 'signals' as MobilePanel, icon: Eye, label: '信號' },
                  { key: 'bet' as MobilePanel, icon: Wallet, label: '投注' },
                ].map(tab => (
                  <button
                    key={tab.key}
                    onClick={() => setMobilePanel(tab.key)}
                    className={`flex flex-col items-center gap-0.5 py-2 transition ${
                      mobilePanel === tab.key
                        ? 'text-[var(--accent-cyan)]'
                        : 'text-[var(--text-muted)]'
                    }`}
                  >
                    <tab.icon className="w-5 h-5" />
                    <span className="text-[10px] font-medium">{tab.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </main>
        </>
      ) : (
        <main className="max-w-[1200px] mx-auto p-4">
          <BacktestView />
        </main>
      )}

      <footer className="border-t border-[var(--border)] py-3 px-6 text-center text-xs text-[var(--text-muted)] mb-14 lg:mb-0">
        HK Racing Quant v0.5 · Data via backend proxy from HKJC GraphQL API · For educational purposes only · Not financial advice
      </footer>
    </div>
  );
}
