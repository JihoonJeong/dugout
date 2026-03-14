import { useState } from 'react';
import { ChevronDown, ChevronUp, ScrollText } from 'lucide-react';

const EVENT_COLORS = {
  HR: 'text-red-400',
  '3B': 'text-yellow-400',
  '2B': 'text-green-400',
  '1B': 'text-blue-400',
  BB: 'text-cyan-400',
  IBB: 'text-cyan-300',
  HBP: 'text-orange-400',
  K: 'text-slate-500',
  GO: 'text-slate-500',
  FO: 'text-slate-500',
};

export default function PlayLog({ plays }) {
  const [expanded, setExpanded] = useState(false);

  if (!plays || plays.length === 0) return null;

  const visible = expanded ? plays : plays.slice(-8);

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm text-slate-300 hover:text-white transition-colors"
      >
        <div className="flex items-center gap-2">
          <ScrollText size={14} />
          <span>Play Log ({plays.length})</span>
        </div>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      <div className={`border-t border-slate-700 px-4 py-2 space-y-1 ${expanded ? 'max-h-96 overflow-y-auto' : ''}`}>
        {visible.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs py-0.5">
            <span className="text-slate-500 font-mono w-8 shrink-0">
              {p.inning}{p.half === 'top' ? 'T' : 'B'}
            </span>
            <span className={`font-mono w-6 text-center font-bold ${EVENT_COLORS[p.event] || 'text-slate-400'}`}>
              {p.event}
            </span>
            <span className="text-slate-300 truncate">{p.description}</span>
            {p.runs_scored > 0 && (
              <span className="text-amber-400 font-bold ml-auto shrink-0">+{p.runs_scored}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
