export default function Diamond({ runners = [] }) {
  const runnerBases = new Set(runners.map(r => r.base));

  const basePos = {
    '1B': { cx: 145, cy: 80 },
    '2B': { cx: 95, cy: 30 },
    '3B': { cx: 45, cy: 80 },
  };

  return (
    <svg viewBox="0 0 190 140" className="w-full max-w-[180px]">
      {/* 필드 */}
      <polygon
        points="95,10 175,90 95,130 15,90"
        fill="none"
        stroke="#166534"
        strokeWidth="2"
      />

      {/* 베이스라인 */}
      <line x1="95" y1="130" x2="175" y2="90" stroke="#166534" strokeWidth="1.5" />
      <line x1="175" y1="90" x2="95" y2="10" stroke="#166534" strokeWidth="1.5" />
      <line x1="95" y1="10" x2="15" y2="90" stroke="#166534" strokeWidth="1.5" />
      <line x1="15" y1="90" x2="95" y2="130" stroke="#166534" strokeWidth="1.5" />

      {/* 홈 */}
      <polygon points="95,126 90,130 95,135 100,130" fill="#e2e8f0" />

      {/* 베이스 */}
      {Object.entries(basePos).map(([base, pos]) => (
        <g key={base}>
          <rect
            x={pos.cx - 7} y={pos.cy - 7}
            width={14} height={14}
            transform={`rotate(45 ${pos.cx} ${pos.cy})`}
            fill={runnerBases.has(base) ? '#f59e0b' : '#334155'}
            stroke={runnerBases.has(base) ? '#fbbf24' : '#475569'}
            strokeWidth="1.5"
          />
        </g>
      ))}
    </svg>
  );
}
