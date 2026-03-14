const SPEEDS = [
  { label: '1x', value: 1000 },
  { label: '2x', value: 500 },
  { label: '5x', value: 200 },
  { label: 'Max', value: 50 },
];

export default function SpeedControl({ speed, onSpeedChange, isPlaying, onToggle }) {
  return (
    <div className="flex items-center gap-3">
      <button
        onClick={onToggle}
        className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
          isPlaying
            ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
            : 'bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30'
        }`}
      >
        {isPlaying ? 'Pause' : 'Play'}
      </button>

      <div className="flex bg-slate-700/50 rounded-lg overflow-hidden border border-slate-600">
        {SPEEDS.map(s => (
          <button
            key={s.label}
            onClick={() => onSpeedChange(s.value)}
            className={`px-3 py-1.5 text-xs font-mono transition-colors ${
              speed === s.value
                ? 'bg-amber-500/20 text-amber-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
