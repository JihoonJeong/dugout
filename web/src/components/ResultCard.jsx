export default function ResultCard({ result, teamNames }) {
  const awayName = teamNames[result.away_team_id] || result.away_team_id;
  const homeName = teamNames[result.home_team_id] || result.home_team_id;

  const up = result.user_prediction;
  const enginePct = (result.engine_away_win_pct * 100).toFixed(0);
  const sb = result.score_breakdown;

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-4">
      {/* Score */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex-1">
          <div className={`text-lg font-bold ${result.actual_winner === 'away' ? 'text-amber-400' : 'text-slate-400'}`}>
            {result.away_team_id}
          </div>
          <div className="text-xs text-slate-500">{awayName}</div>
        </div>

        <div className="text-center mx-4">
          <div className="font-mono text-2xl text-white font-bold">
            {result.actual_away_score} - {result.actual_home_score}
          </div>
          <div className="text-xs text-slate-500">Final</div>
        </div>

        <div className="flex-1 text-right">
          <div className={`text-lg font-bold ${result.actual_winner === 'home' ? 'text-amber-400' : 'text-slate-400'}`}>
            {result.home_team_id}
          </div>
          <div className="text-xs text-slate-500">{homeName}</div>
        </div>
      </div>

      {/* Prediction results */}
      <div className="border-t border-slate-700 pt-3 grid grid-cols-2 gap-3">
        {/* Engine */}
        <div className={`rounded-lg p-2 ${
          result.engine_correct === true
            ? 'bg-green-500/10 border border-green-500/30'
            : result.engine_correct === false
            ? 'bg-red-500/10 border border-red-500/30'
            : 'bg-slate-700/50'
        }`}>
          <div className="text-xs text-slate-400 mb-1">Engine Pick</div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-white">
              {result.engine_pick ? (result.engine_pick === 'away' ? result.away_team_id : result.home_team_id) : '—'}
            </span>
            {result.engine_correct !== null && (
              <span className={`text-xs font-bold ${result.engine_correct ? 'text-green-400' : 'text-red-400'}`}>
                {result.engine_correct ? '✓' : '✗'}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-500">
            {result.engine_pick === 'away' ? enginePct : (100 - parseFloat(enginePct))}% confidence
          </div>
        </div>

        {/* User */}
        <div className={`rounded-lg p-2 ${
          result.user_correct === true
            ? 'bg-green-500/10 border border-green-500/30'
            : result.user_correct === false
            ? 'bg-red-500/10 border border-red-500/30'
            : 'bg-slate-700/50 border border-slate-600/50'
        }`}>
          <div className="text-xs text-slate-400 mb-1">Your Pick</div>
          {up ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-white">
                  {up.predicted_winner === 'away' ? result.away_team_id : result.home_team_id}
                </span>
                <span className={`text-xs font-bold ${result.user_correct ? 'text-green-400' : 'text-red-400'}`}>
                  {result.user_correct ? '✓' : '✗'}
                </span>
              </div>
              {up.predicted_away_score != null && (
                <div className="text-xs text-slate-500">
                  Predicted: {up.predicted_away_score} - {up.predicted_home_score}
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-slate-500">No prediction</div>
          )}
        </div>
      </div>

      {/* Score breakdown */}
      {sb && (
        <div className="mt-3 border-t border-slate-700 pt-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-400 uppercase tracking-wider">Score</span>
            <span className="text-lg font-bold text-amber-400">{sb.total.toFixed(0)} pts</span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div className={`rounded-md p-1.5 ${sb.winner > 0 ? 'bg-green-500/10' : 'bg-slate-700/50'}`}>
              <div className="text-xs text-slate-500">Winner</div>
              <div className={`text-sm font-mono font-bold ${sb.winner > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {sb.winner > 0 ? '+50' : '0'}
              </div>
            </div>
            <div className={`rounded-md p-1.5 ${sb.accuracy > 0 ? 'bg-blue-500/10' : 'bg-slate-700/50'}`}>
              <div className="text-xs text-slate-500">Score</div>
              <div className="text-sm font-mono font-bold text-blue-400">
                +{sb.accuracy.toFixed(0)}
              </div>
            </div>
            <div className={`rounded-md p-1.5 ${sb.exact_bonus > 0 ? 'bg-purple-500/10' : 'bg-slate-700/50'}`}>
              <div className="text-xs text-slate-500">Exact</div>
              <div className={`text-sm font-mono font-bold ${sb.exact_bonus > 0 ? 'text-purple-400' : 'text-slate-600'}`}>
                {sb.exact_bonus > 0 ? '+10' : '—'}
              </div>
            </div>
            <div className={`rounded-md p-1.5 ${sb.calibration > 0 ? 'bg-cyan-500/10' : 'bg-slate-700/50'}`}>
              <div className="text-xs text-slate-500">Cal</div>
              <div className="text-sm font-mono font-bold text-cyan-400">
                +{sb.calibration.toFixed(0)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
