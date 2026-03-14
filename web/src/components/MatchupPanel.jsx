export default function MatchupPanel({ state }) {
  if (!state) return null;
  const { current_batter: b, current_pitcher: p } = state;

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Pitcher */}
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Pitching</div>
          <div className="text-white font-medium">{p.name}</div>
          <div className="text-sm text-slate-400 mt-1 space-y-0.5">
            <div>{p.hand}HP · {p.is_starter ? 'SP' : 'RP'}</div>
            <div className="font-mono">{p.pitch_count}p · {p.innings_pitched.toFixed(1)}IP</div>
          </div>
        </div>

        {/* Batter */}
        <div className="text-right">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">At Bat</div>
          <div className="text-white font-medium">{b.name}</div>
          <div className="text-sm text-slate-400 mt-1 space-y-0.5">
            <div>{b.hand === 'S' ? 'Switch' : b.hand + 'HB'} · #{b.batting_order}</div>
            <div className="font-mono">{b.pa} PA</div>
          </div>
        </div>
      </div>
    </div>
  );
}
