import { useState, useEffect } from 'react';
import type { RaceMeeting } from './utils/types';
import RaceOverview from './components/RaceOverview';
import ModelCalculator from './components/ModelCalculator';
import ValueBetSignals from './components/ValueBetSignals';
import { computeLocalAnalysis, getLiveAnalysis } from './utils/api';
import { Activity } from 'lucide-react';

interface AnalysisData {
  runners: any[];
  pace_forecast: any;
  smart_money_alerts: any[];
  value_bet_count?: number;
}

export default function App() {
  const [selectedMeeting, setSelectedMeeting] = useState<RaceMeeting | null>(null);
  const [selectedRaceNo, setSelectedRaceNo] = useState<number>(1);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);

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
                香港賽馬量化分析系統 · Value Bet Detector
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

      <main className="max-w-[1800px] mx-auto p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-3 space-y-4">
          <div className="sticky top-4">
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Panel A · Race Dashboard
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
            Panel B · Quant Model
          </div>
          <ModelCalculator meeting={selectedMeeting} raceNo={selectedRaceNo} />
        </div>

        <div className="lg:col-span-4 space-y-4">
          <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Panel C · +EV Signals
          </div>
          <ValueBetSignals
            meeting={selectedMeeting}
            raceNo={selectedRaceNo}
            analysis={analysis}
          />
        </div>
      </main>

      <footer className="border-t border-[var(--border)] py-3 px-6 text-center text-xs text-[var(--text-muted)]">
        HK Racing Quant v0.1 · Data via backend proxy from HKJC GraphQL API · For educational purposes only · Not financial advice
      </footer>
    </div>
  );
}
