export function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString('en-HK', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return isoStr;
  }
}

export function formatCurrency(val: number | string | undefined): string {
  if (val === undefined || val === null) return '—';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toFixed(0);
}

export function pct(val: number): string {
  return `${val.toFixed(1)}%`;
}

export function evColor(ev: number): string {
  if (ev > 0.15) return 'var(--accent-green)';
  if (ev > 0.05) return 'var(--accent-cyan)';
  if (ev < -0.1) return 'var(--accent-red)';
  return 'var(--text-secondary)';
}

export function paceTag(style: 'front' | 'mid' | 'closer'): { label: string; cls: string } {
  switch (style) {
    case 'front': return { label: '前領', cls: 'tag-red' };
    case 'mid': return { label: '跟前', cls: 'tag-yellow' };
    case 'closer': return { label: '後上', cls: 'tag-blue' };
  }
}

export function severityColor(s: 'low' | 'medium' | 'high'): string {
  switch (s) {
    case 'high': return 'var(--accent-red)';
    case 'medium': return 'var(--accent-yellow)';
    case 'low': return 'var(--accent-cyan)';
  }
}

// 跑馬地短途檔位優勢表 (1200m C跑道)
const HV_1200_BARRIER_ADVANTAGE: Record<number, number> = {
  1: 14.2, 2: 12.8, 3: 11.5, 4: 10.1, 5: 8.7,
  6: 7.3, 7: 6.0, 8: 4.8, 9: 3.7, 10: 2.8,
  11: 2.1, 12: 1.5,
};

export function getBarrierAdvantage(barrier: number, venue: string, distance: number): number {
  if (venue === 'HV' && distance <= 1200) {
    return HV_1200_BARRIER_ADVANTAGE[barrier] || 1.0;
  }
  return 0; // No special advantage
}
