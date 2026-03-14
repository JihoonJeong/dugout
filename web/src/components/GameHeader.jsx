import Diamond from './Diamond';

function OutDots({ outs }) {
  return (
    <div className="flex gap-1.5">
      {[0, 1, 2].map(i => (
        <div key={i} className={`w-3 h-3 rounded-full border ${
          i < outs ? 'bg-amber-500 border-amber-400' : 'bg-slate-700 border-slate-600'
        }`} />
      ))}
    </div>
  );
}

export default function GameHeader({ state, awayId, homeId }) {
  if (!state) return null;

  const isTop = state.half === 'top';

  return (
    <div className="bg-slate-800/90 border-b border-slate-700 px-6 py-4">
      <div className="flex items-center justify-between max-w-4xl mx-auto">
        {/* Away */}
        <div className="text-center min-w-[80px]">
          <div className={`font-mono text-sm tracking-wider ${isTop ? 'text-amber-400' : 'text-slate-400'}`}>
            {awayId}
          </div>
          <div className="font-mono text-4xl font-bold text-white score-glow">
            {state.score.away}
          </div>
        </div>

        {/* Center: inning + diamond + outs */}
        <div className="flex flex-col items-center gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">{isTop ? '▲' : '▼'}</span>
            <span className="font-mono text-lg text-white">{state.inning}</span>
          </div>
          <Diamond runners={state.runners} />
          <OutDots outs={state.outs} />
        </div>

        {/* Home */}
        <div className="text-center min-w-[80px]">
          <div className={`font-mono text-sm tracking-wider ${!isTop ? 'text-amber-400' : 'text-slate-400'}`}>
            {homeId}
          </div>
          <div className="font-mono text-4xl font-bold text-white score-glow">
            {state.score.home}
          </div>
        </div>
      </div>
    </div>
  );
}
