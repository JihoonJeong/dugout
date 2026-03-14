import { useState, useEffect } from 'react';
import { getMyStats } from '../api';

export default function MyStats({ onClose }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMyStats()
      .then(data => { setStats(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-6 text-center text-slate-400">
        Loading stats...
      </div>
    );
  }

  if (!stats || stats.total_predictions === 0) {
    return (
      <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">My Stats</h2>
          {onClose && (
            <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">✕</button>
          )}
        </div>
        <p className="text-slate-400 text-center">No predictions yet. Start picking today's games!</p>
      </div>
    );
  }

  const s = stats;

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-white">My Stats</h2>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">✕</button>
        )}
      </div>

      {/* Main stats */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <StatBox
          label="Win Accuracy"
          value={`${(s.win_accuracy * 100).toFixed(0)}%`}
          detail={`${s.wins_correct}/${s.wins_total}`}
          color="amber"
        />
        <StatBox
          label="Avg Score"
          value={s.avg_points.toFixed(1)}
          detail={`of 100 pts`}
          color="blue"
        />
        <StatBox
          label="Exact Scores"
          value={s.exact_scores}
          detail={`of ${s.total_scored}`}
          color="purple"
        />
      </div>

      {/* Points breakdown */}
      <div className="bg-slate-900/50 rounded-lg p-3 mb-4">
        <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Points Breakdown</div>
        <div className="space-y-2">
          <PointsBar label="Winner" points={s.total_winner_points} maxPossible={s.total_scored * 50} color="bg-green-500" />
          <PointsBar label="Score Accuracy" points={s.total_score_points} maxPossible={s.total_scored * 40} color="bg-blue-500" />
          <PointsBar label="Calibration" points={s.total_calibration_points} maxPossible={s.total_scored * 10} color="bg-cyan-500" />
        </div>
        <div className="flex justify-between mt-2 pt-2 border-t border-slate-700">
          <span className="text-sm text-slate-300">Total</span>
          <span className="text-sm font-bold text-amber-400">{s.total_points.toFixed(0)} pts</span>
        </div>
      </div>

      {/* vs Engine */}
      {s.engine_total > 0 && (
        <div className="bg-slate-900/50 rounded-lg p-3">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">You vs Engine</div>
          <div className="flex items-center justify-between">
            <div className="text-center">
              <div className={`text-xl font-bold ${s.win_accuracy >= s.engine_accuracy ? 'text-green-400' : 'text-white'}`}>
                {(s.win_accuracy * 100).toFixed(0)}%
              </div>
              <div className="text-xs text-slate-400">You</div>
            </div>
            <div className="text-slate-600 text-sm">vs</div>
            <div className="text-center">
              <div className={`text-xl font-bold ${s.engine_accuracy > s.win_accuracy ? 'text-green-400' : 'text-white'}`}>
                {(s.engine_accuracy * 100).toFixed(0)}%
              </div>
              <div className="text-xs text-slate-400">Engine</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, detail, color }) {
  const colorMap = {
    amber: 'text-amber-400',
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    green: 'text-green-400',
  };
  return (
    <div className="bg-slate-900/50 rounded-lg p-3 text-center">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colorMap[color] || 'text-white'}`}>{value}</div>
      <div className="text-xs text-slate-500">{detail}</div>
    </div>
  );
}

function PointsBar({ label, points, maxPossible, color }) {
  const pct = maxPossible > 0 ? (points / maxPossible) * 100 : 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-slate-400">{label}</span>
        <span className="text-slate-300">{points.toFixed(0)}</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  );
}
