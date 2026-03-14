import { useState, useEffect } from 'react';
import { submitPrediction, predictGame } from '../api';
import AIAnalysis from './AIAnalysis';

function useCountdown(gameDate, gameTime) {
  const [timeLeft, setTimeLeft] = useState('');
  const [isLocked, setIsLocked] = useState(false);

  useEffect(() => {
    if (!gameTime || !gameDate) return;

    function update() {
      try {
        const gameStr = `${gameDate}T${gameTime}:00`;
        const gameMs = new Date(gameStr).getTime();
        const lockMs = gameMs - 60 * 60 * 1000;
        const now = Date.now();

        if (now >= lockMs) {
          setIsLocked(true);
          setTimeLeft('Locked');
          return;
        }

        const diff = lockMs - now;
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        setTimeLeft(h > 0 ? `${h}h ${m}m` : `${m}m`);
      } catch {
        setTimeLeft('');
      }
    }

    update();
    const t = setInterval(update, 60000);
    return () => clearInterval(t);
  }, [gameDate, gameTime]);

  return { timeLeft, isLocked };
}

export default function GameCard({ game: initialGame, teamNames, onPredictionSubmit, onWatchSim }) {
  const [game, setGame] = useState(initialGame);
  const [expanded, setExpanded] = useState(false);
  const [predWinner, setPredWinner] = useState(null);
  const [predAwayScore, setPredAwayScore] = useState('');
  const [predHomeScore, setPredHomeScore] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [predicting, setPredicting] = useState(false);
  const { timeLeft, isLocked } = useCountdown(game.game_date, game.game_time);
  const [submitted, setSubmitted] = useState(!!game.user_prediction);

  const awayName = teamNames[game.away_team_id] || game.away_team_id;
  const homeName = teamNames[game.home_team_id] || game.home_team_id;

  const hasPred = game.has_prediction;
  const awayPct = hasPred ? (game.final_away_win_pct * 100).toFixed(0) : null;
  const homePct = hasPred ? (game.final_home_win_pct * 100).toFixed(0) : null;
  const favored = hasPred && game.final_away_win_pct > 0.5 ? 'away' : 'home';

  async function handlePredict(e) {
    e.stopPropagation();
    setPredicting(true);
    try {
      const res = await predictGame(game.game_id, game.game_date);
      if (res.game_id) setGame(res);
    } catch (err) {
      console.error('Prediction failed:', err);
    }
    setPredicting(false);
  }

  async function handleSubmit() {
    if (!predWinner) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await submitPrediction({
        gameId: game.game_id,
        gameDate: game.game_date,
        predictedWinner: predWinner,
        predictedAwayScore: predAwayScore ? parseInt(predAwayScore) : undefined,
        predictedHomeScore: predHomeScore ? parseInt(predHomeScore) : undefined,
      });
      if (res.status === 'submitted') {
        setSubmitted(true);
        onPredictionSubmit?.();
      } else if (res.detail) {
        setSubmitError(res.detail);
      }
    } catch (e) {
      setSubmitError(e.message || 'Failed to submit prediction');
    }
    setSubmitting(false);
  }

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 overflow-hidden hover:border-slate-600 transition-colors">
      {/* Spring Training badge */}
      {game.game_type === 'S' && (
        <div className="bg-green-900/40 border-b border-green-700/30 px-4 py-1 text-center">
          <span className="text-green-400 text-xs font-medium tracking-wider uppercase">Spring Training</span>
        </div>
      )}

      {/* Main row */}
      <div
        className="p-4 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center justify-between">
          {/* Away team */}
          <div className="flex-1">
            <div className={`text-lg font-bold ${hasPred && favored === 'away' ? 'text-amber-400' : 'text-white'}`}>
              {game.away_team_id}
            </div>
            <div className="text-xs text-slate-400">{awayName}</div>
            <div className="text-xs text-slate-500 mt-1">{game.away_starter_name}</div>
          </div>

          {/* Center */}
          <div className="flex-1 mx-4">
            {hasPred ? (
              <>
                <div className="flex justify-between text-xs mb-1">
                  <span className={favored === 'away' ? 'text-amber-400 font-bold' : 'text-slate-400'}>{awayPct}%</span>
                  <span className="text-slate-500">
                    {game.game_time} ET
                    {timeLeft && !isLocked && <span className="text-amber-500/70 text-xs ml-1 countdown-pulse">({timeLeft})</span>}
                    {isLocked && !submitted && <span className="text-red-400/70 text-xs ml-1">🔒</span>}
                  </span>
                  <span className={favored === 'home' ? 'text-amber-400 font-bold' : 'text-slate-400'}>{homePct}%</span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden flex">
                  <div className="bg-amber-500/80 transition-all" style={{ width: `${awayPct}%` }} />
                  <div className="bg-blue-500/60 transition-all" style={{ width: `${homePct}%` }} />
                </div>
                <div className="text-center text-xs text-slate-500 mt-1">
                  Proj: {game.mc_avg_away_runs.toFixed(1)} - {game.mc_avg_home_runs.toFixed(1)}
                </div>
              </>
            ) : (
              <div className="text-center">
                <div className="text-slate-400 text-sm font-medium">vs</div>
                <div className="text-slate-500 text-sm">
                  {game.game_time} ET
                  {timeLeft && !isLocked && <span className="text-amber-500/70 text-xs ml-1 countdown-pulse">({timeLeft})</span>}
                </div>
              </div>
            )}
          </div>

          {/* Home team */}
          <div className="flex-1 text-right">
            <div className={`text-lg font-bold ${hasPred && favored === 'home' ? 'text-amber-400' : 'text-white'}`}>
              {game.home_team_id}
            </div>
            <div className="text-xs text-slate-400">{homeName}</div>
            <div className="text-xs text-slate-500 mt-1">{game.home_starter_name}</div>
          </div>
        </div>

        {/* Prediction badge */}
        {submitted && (
          <div className="mt-2 text-center">
            <span className="text-xs px-2 py-1 bg-green-500/20 text-green-400 rounded-full">✓ Prediction submitted</span>
          </div>
        )}
      </div>

      {/* Expanded panel */}
      {expanded && (
        <div className="border-t border-slate-700 p-4 bg-slate-900/50">
          {/* Prediction form — always first */}
          {!submitted ? (
            <div className="space-y-3">
              <div className="text-sm text-slate-300 font-medium">Your Prediction</div>

              <div className="flex gap-2">
                <button
                  onClick={(e) => { e.stopPropagation(); setPredWinner('away'); }}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    predWinner === 'away'
                      ? 'bg-amber-500/30 text-amber-400 border border-amber-500/50'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {game.away_team_id} wins
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setPredWinner('home'); }}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    predWinner === 'home'
                      ? 'bg-blue-500/30 text-blue-400 border border-blue-500/50'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {game.home_team_id} wins
                </button>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="number" min="0" max="30"
                  placeholder={game.away_team_id}
                  value={predAwayScore}
                  onChange={(e) => setPredAwayScore(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-20 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-center text-white text-sm focus:border-amber-500 focus:outline-none"
                />
                <span className="text-slate-500 text-sm">-</span>
                <input
                  type="number" min="0" max="30"
                  placeholder={game.home_team_id}
                  value={predHomeScore}
                  onChange={(e) => setPredHomeScore(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-20 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-center text-white text-sm focus:border-amber-500 focus:outline-none"
                />
                <span className="text-xs text-slate-500 ml-2">(optional)</span>
              </div>

              {submitError && (
                <div className="text-xs text-red-400 bg-red-500/10 rounded-lg p-2">{submitError}</div>
              )}

              <button
                onClick={(e) => { e.stopPropagation(); handleSubmit(); }}
                disabled={!predWinner || submitting || isLocked}
                className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 font-bold rounded-lg transition-colors text-sm"
              >
                {isLocked ? '🔒 Prediction Window Closed' : submitting ? 'Submitting...' : 'Lock In Prediction'}
              </button>
            </div>
          ) : (
            <div className="text-center text-sm text-slate-400 mb-4">
              Prediction locked. Good luck!
            </div>
          )}

          {/* Tools section — engine prediction + live sim */}
          <div className="mt-4 pt-4 border-t border-slate-700/50">
            {hasPred ? (
              <>
                <div className="grid grid-cols-3 gap-4 text-center mb-4">
                  <div>
                    <div className="text-xs text-slate-500">Quick Sim</div>
                    <div className="font-mono text-white">{game.quick_away_score} - {game.quick_home_score}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Avg Total</div>
                    <div className="font-mono text-white">{game.mc_avg_total_runs.toFixed(1)} runs</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Venue</div>
                    <div className="text-sm text-slate-300 truncate">{game.venue}</div>
                  </div>
                </div>

                {(game.away_starter_fallback || game.home_starter_fallback) && (
                  <div className="text-xs text-yellow-500/70 mb-3">
                    ⚠ Starter data:
                    {game.away_starter_fallback && ` ${game.away_team_id} (${game.away_starter_fallback})`}
                    {game.home_starter_fallback && ` ${game.home_team_id} (${game.home_starter_fallback})`}
                  </div>
                )}

                <AIAnalysis game={game} />
              </>
            ) : (
              <div className="text-xs text-slate-500 mb-3 text-center">{game.venue}</div>
            )}

            <div className="flex gap-2 mt-3">
              {!hasPred && (
                <button
                  onClick={handlePredict}
                  disabled={predicting}
                  className="flex-1 py-2 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors disabled:opacity-50"
                >
                  {predicting ? (
                    <span className="flex items-center justify-center gap-1.5">
                      <span className="spinner inline-block w-3 h-3 border-2 border-amber-400/30 border-t-amber-400 rounded-full"></span>
                      Running engine...
                    </span>
                  ) : (
                    'Engine Prediction'
                  )}
                </button>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); onWatchSim?.(game.away_team_id, game.home_team_id); }}
                className="flex-1 py-2 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors"
              >
                Watch Live Sim
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
