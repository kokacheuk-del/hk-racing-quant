import { useState, useEffect, useCallback } from 'react';
import type { RaceMeeting } from '../utils/types';
import { getRaceMeetings, isColdStarting, clearColdStart } from '../utils/api';
import { formatTime } from '../utils/helpers';
import { VENUE_MAP, GOING_MAP } from '../utils/types';
import { Activity, MapPin, Clock, ServerCrash, Loader2, Calendar } from 'lucide-react';

interface Props {
  onSelectRace: (meeting: RaceMeeting, raceNo: number) => void;
  selectedMeeting?: RaceMeeting | null;
  selectedRaceNo?: number;
}

export default function RaceOverview({ onSelectRace, selectedMeeting, selectedRaceNo }: Props) {
  const [meetings, setMeetings] = useState<RaceMeeting[]>([]);
  const [activeDate, setActiveDate] = useState<string>('');
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [coldStart, setColdStart] = useState(false);

  const loadMeetings = useCallback(async (date?: string) => {
    setLoading(true);
    setError('');
    setColdStart(false);
    try {
      const data = await getRaceMeetings(date || undefined);
      setMeetings(data);
      if (data.length > 0) {
        setActiveDate(data[0].date);
        if (!selectedMeeting) {
          // Auto-select first race of first meeting
          const firstRaceNo = data[0].races?.[0]?.no || 1;
          onSelectRace(data[0], firstRaceNo);
        }
      }
    } catch (e: any) {
      if (e.message === 'SERVER_COLD_START' || isColdStarting()) {
        setColdStart(true);
        setError('');
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }, [onSelectRace, selectedMeeting]);

  // Load today's meetings on mount
  useEffect(() => {
    loadMeetings();
    // Set date picker to today
    const today = new Date().toISOString().split('T')[0];
    setSelectedDate(today);
  }, []);

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setSelectedDate(newDate);
    loadMeetings(newDate);
  };

  const meeting = meetings[0];

  if (loading) {
    return (
      <div className="card flex items-center justify-center h-64">
        <div className="text-[var(--text-muted)] flex items-center gap-2">
          <Activity className="w-4 h-4 animate-spin" /> 載入中...
        </div>
      </div>
    );
  }

  if (coldStart) {
    return (
      <div className="card h-64 flex items-center justify-center">
        <div className="text-center space-y-3">
          <Loader2 className="w-8 h-8 text-[var(--accent-cyan)] animate-spin mx-auto" />
          <p className="text-[var(--accent-cyan)] font-semibold">正在喚醒伺服器</p>
          <p className="text-[var(--text-muted)] text-sm">免費伺服器休眠中，首次啟動需 30-50 秒</p>
          <button
            onClick={() => { clearColdStart(); loadMeetings(selectedDate); }}
            className="mt-2 px-4 py-1.5 rounded-lg bg-[var(--accent-cyan)] text-white text-sm hover:opacity-90 transition"
          >
            重新嘗試
          </button>
        </div>
      </div>
    );
  }

  if (error || !meeting) {
    return (
      <div className="card h-64 flex items-center justify-center">
        <div className="text-center">
          <ServerCrash className="w-6 h-6 text-[var(--accent-red)] mx-auto mb-2" />
          <p className="text-[var(--accent-red)] mb-2">該日無賽事資料</p>
          <p className="text-[var(--text-muted)] text-xs">請選擇其他日期測試</p>
          {/* Date picker also shown here for convenience */}
          <div className="mt-3 flex items-center justify-center gap-2">
            <Calendar className="w-4 h-4 text-[var(--accent-cyan)]" />
            <input
              type="date"
              value={selectedDate}
              onChange={handleDateChange}
              className="px-2 py-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-cyan)]"
            />
          </div>
          <button
            onClick={() => loadMeetings(selectedDate)}
            className="mt-3 text-[var(--accent-blue)] text-sm hover:underline"
          >
            重新載入
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
                {meeting.date} · {meeting.totalNumberOfRace || meeting.races?.length || 0} 場賽事
              </p>
            </div>
          </div>
          <span className="tag tag-blue">{meeting.status}</span>
        </div>

        {/* Date picker for testing */}
        <div className="flex items-center gap-2 mb-3 p-2 bg-[var(--bg-secondary)] rounded-lg">
          <Calendar className="w-4 h-4 text-[var(--accent-cyan)]" />
          <span className="text-xs text-[var(--text-muted)]">選擇賽日測試：</span>
          <input
            type="date"
            value={selectedDate}
            onChange={handleDateChange}
            className="flex-1 px-3 py-2 bg-[var(--bg-primary)] border border-[var(--border)] rounded-lg text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-cyan)] focus:ring-1 focus:ring-[var(--accent-cyan)] cursor-pointer"
          />
          <button
            onClick={() => loadMeetings(selectedDate)}
            disabled={loading}
            className="px-2 py-1 bg-[var(--accent-cyan)] text-white text-xs rounded hover:opacity-90 disabled:opacity-50 transition"
          >
            {loading ? '...' : '載入'}
          </button>
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
                <span className="text-xs opacity-70">第{race.no}場</span>
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
                第{race.no}場: {race.raceName_en}
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
              {race.raceCourse?.description_en} · {race.wageringFieldSize} 參賽馬
            </div>
          </div>
        );
      })()}

      {meetings.length > 1 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">
            <Clock className="w-4 h-4 inline mr-1" /> 所有賽日
          </h3>
          <div className="flex gap-3 flex-wrap">
            {meetings.map(m => {
              const v = VENUE_MAP[m.venueCode] || { en: m.venueCode };
              return (
                <button
                  key={m.id}
                  onClick={() => { setActiveDate(m.date); loadMeetings(m.date); setSelectedDate(m.date); }}
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
