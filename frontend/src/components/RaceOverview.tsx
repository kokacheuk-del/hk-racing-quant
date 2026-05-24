import { useState, useEffect, useCallback } from 'react';
import type { RaceMeeting } from '../utils/types';
import { getRaceMeetings, getActiveMeetings } from '../utils/api';
import { formatTime } from '../utils/helpers';
import { VENUE_MAP, GOING_MAP } from '../utils/types';
import { Activity, MapPin, Clock } from 'lucide-react';

interface Props {
  onSelectRace: (meeting: RaceMeeting, raceNo: number) => void;
  selectedMeeting?: RaceMeeting | null;
  selectedRaceNo?: number;
}

export default function RaceOverview({ onSelectRace, selectedMeeting, selectedRaceNo }: Props) {
  const [meetings, setMeetings] = useState<RaceMeeting[]>([]);
  const [activeDate, setActiveDate] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadMeetings = useCallback(async (date?: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await getRaceMeetings(date || undefined);
      setMeetings(data);
      if (data.length > 0 && !date) {
        setActiveDate(data[0].date);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMeetings(); }, [loadMeetings]);

  const meeting = meetings[0];

  if (loading) {
    return (
      <div className="card flex items-center justify-center h-64">
        <div className="text-[var(--text-muted)] flex items-center gap-2">
          <Activity className="w-4 h-4 animate-spin" /> Loading race data...
        </div>
      </div>
    );
  }

  if (error || !meeting) {
    return (
      <div className="card h-64 flex items-center justify-center">
        <div className="text-center">
          <p className="text-[var(--accent-red)] mb-2">Failed to load race data</p>
          <p className="text-[var(--text-muted)] text-sm">{error}</p>
          <p className="text-[var(--text-muted)] text-xs mt-1">
            Make sure the backend is running: <code>uvicorn app.main:app --port 8000</code>
          </p>
          <button onClick={() => loadMeetings()} className="mt-3 text-[var(--accent-blue)] text-sm hover:underline">
            Retry
          </button>
        </div>
      </div>
    );
  }

  const venue = VENUE_MAP[meeting.venueCode] || { en: meeting.venueCode, ch: '', short: meeting.venueCode };

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <MapPin className="w-5 h-5 text-[var(--accent-cyan)]" />
            <div>
              <h2 className="text-lg font-bold text-[var(--text-primary)]">
                {venue.en} <span className="text-[var(--text-secondary)]">({venue.ch})</span>
              </h2>
              <p className="text-sm text-[var(--text-muted)]">
                {meeting.date} · {meeting.totalNumberOfRace || meeting.races?.length || 0} Races
              </p>
            </div>
          </div>
          <span className="tag tag-blue">{meeting.status}</span>
        </div>

        <div className="flex flex-wrap gap-2">
          {(meeting.races || []).map((race: any) => {
            const isActive = selectedRaceNo === race.no;
            return (
              <button
                key={race.no}
                onClick={() => onSelectRace(meeting, race.no)}
                className={`
                  px-3 py-2 rounded-lg text-sm font-medium transition-all
                  flex flex-col items-center min-w-[72px]
                  ${isActive
                    ? 'bg-[var(--accent-blue)] text-white shadow-lg shadow-blue-500/20'
                    : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]'
                  }
                `}
              >
                <span className="text-xs opacity-70">R{race.no}</span>
                <span className="font-mono">{formatTime(race.postTime)}</span>
                {race.distance && <span className="text-[10px] opacity-60">{race.distance}m</span>}
              </button>
            );
          })}
        </div>
      </div>

      {selectedRaceNo && (() => {
        const race = (meeting.races || []).find((r: any) => r.no === selectedRaceNo);
        if (!race) return null;
        const going = GOING_MAP[race.go_en?.toUpperCase().replace(/\s+/g, '_')];
        return (
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-[var(--accent-cyan)]">
                Race {race.no}: {race.raceName_en}
              </h3>
              <div className="flex items-center gap-2">
                {going && (
                  <span className="tag" style={{ color: going.color, borderColor: going.color, background: `${going.color}20` }}>
                    {going.label}
                  </span>
                )}
                <span className="tag tag-blue">{race.distance}m</span>
                {race.raceClass_en && <span className="tag tag-yellow">{race.raceClass_en}</span>}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">
              {race.raceCourse?.description_en} · {race.wageringFieldSize} runners
            </div>
          </div>
        );
      })()}

      {meetings.length > 1 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">
            <Clock className="w-4 h-4 inline mr-1" /> All Meetings
          </h3>
          <div className="flex gap-3">
            {meetings.map(m => {
              const v = VENUE_MAP[m.venueCode] || { en: m.venueCode };
              return (
                <button
                  key={m.id}
                  onClick={() => { setActiveDate(m.date); loadMeetings(m.date); }}
                  className={`text-xs px-3 py-1.5 rounded border transition-all
                    ${activeDate === m.date
                      ? 'border-[var(--accent-blue)] text-[var(--accent-blue)] bg-[var(--accent-blue)]/10'
                      : 'border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                >
                  {v.en} · {m.date} · {(m.races || []).length}R
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
