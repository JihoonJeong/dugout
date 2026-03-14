import { useState } from 'react';

export default function ResultCard({ result, teamNames }) {
  const awayName = teamNames[result.away_team_id] || result.away_team_id;
  const homeName = teamNames[result.home_team_id] || result.home_team_id;

  const up = result.user_prediction;
  const enginePct = (result.engine_away_win_pct * 100).toFixed(0);
  const sb = result.score_breakdown;
  const hasLinescore = result.away_innings?.length > 0;

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 overflow-hidden">
      {/* Spring Training badge */}
      {result.game_type === 'S' && (
        <div className="bg-green-900/40 border-b border-green-700/30 px-4 py-1 text-center">
          <span className="text-green-400 text-xs font-medium tracking-wider uppercase">Spring Training</span>
        </div>
      )}

      <div className="p-4">
        {/* Score header */}
        <div className="flex items-center justify-between mb-2">
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

        {/* Linescore */}
        {hasLinescore && (
          <div className="bg-slate-900/60 rounded-lg p-2 mb-3 overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left py-0.5 pr-2 w-10"></th>
                  {result.away_innings.map((_, i) => (
                    <th key={i} className="text-center px-1 min-w-[20px]">{i + 1}</th>
                  ))}
                  <th className="text-center px-1.5 border-l border-slate-700 font-bold">R</th>
                  <th className="text-center px-1.5 font-bold">H</th>
                  <th className="text-center px-1.5 font-bold">E</th>
                </tr>
              </thead>
              <tbody>
                <tr className={result.actual_winner === 'away' ? 'text-white' : 'text-slate-400'}>
                  <td className="text-left pr-2 font-bold">{result.away_team_id}</td>
                  {result.away_innings.map((runs, i) => (
                    <td key={i} className={`text-center px-1 ${runs > 0 ? 'text-amber-400' : ''}`}>{runs}</td>
                  ))}
                  <td className="text-center px-1.5 border-l border-slate-700 font-bold">{result.actual_away_score}</td>
                  <td className="text-center px-1.5">{result.away_hits}</td>
                  <td className="text-center px-1.5">{result.away_errors}</td>
                </tr>
                <tr className={result.actual_winner === 'home' ? 'text-white' : 'text-slate-400'}>
                  <td className="text-left pr-2 font-bold">{result.home_team_id}</td>
                  {result.home_innings.map((runs, i) => (
                    <td key={i} className={`text-center px-1 ${runs > 0 ? 'text-amber-400' : ''}`}>{runs}</td>
                  ))}
                  <td className="text-center px-1.5 border-l border-slate-700 font-bold">{result.actual_home_score}</td>
                  <td className="text-center px-1.5">{result.home_hits}</td>
                  <td className="text-center px-1.5">{result.home_errors}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* Decisions: W/L/SV */}
        {(result.winning_pitcher || result.losing_pitcher) && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs mb-3">
            {result.winning_pitcher && (
              <span><span className="text-green-400 font-medium">W</span> <span className="text-slate-300">{result.winning_pitcher}</span></span>
            )}
            {result.losing_pitcher && (
              <span><span className="text-red-400 font-medium">L</span> <span className="text-slate-300">{result.losing_pitcher}</span></span>
            )}
            {result.save_pitcher && (
              <span><span className="text-blue-400 font-medium">SV</span> <span className="text-slate-300">{result.save_pitcher}</span></span>
            )}
          </div>
        )}

        {/* Scoring plays */}
        {result.scoring_plays?.length > 0 && (
          <ScoringPlays plays={result.scoring_plays} />
        )}

        {/* Box score */}
        {(result.away_batters?.length > 0 || result.home_batters?.length > 0) && (
          <BoxScore result={result} />
        )}

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
    </div>
  );
}

function BoxScore({ result }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-slate-900/40 rounded-lg p-2.5 mb-3">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="text-xs text-slate-400 uppercase tracking-wider">Box Score</span>
        <span className="text-xs text-slate-500">{expanded ? 'collapse' : 'expand'}</span>
      </div>

      {expanded && (
        <div className="mt-3 space-y-4 overflow-x-auto">
          {/* Away batters */}
          <div>
            <div className="text-xs text-slate-400 font-medium mb-1">{result.away_team_id} Batting</div>
            <BatterTable batters={result.away_batters} />
          </div>

          {/* Away pitchers */}
          {result.away_pitchers?.length > 0 && (
            <div>
              <div className="text-xs text-slate-400 font-medium mb-1">{result.away_team_id} Pitching</div>
              <PitcherTable pitchers={result.away_pitchers} />
            </div>
          )}

          {/* Home batters */}
          <div>
            <div className="text-xs text-slate-400 font-medium mb-1">{result.home_team_id} Batting</div>
            <BatterTable batters={result.home_batters} />
          </div>

          {/* Home pitchers */}
          {result.home_pitchers?.length > 0 && (
            <div>
              <div className="text-xs text-slate-400 font-medium mb-1">{result.home_team_id} Pitching</div>
              <PitcherTable pitchers={result.home_pitchers} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BatterTable({ batters }) {
  return (
    <table className="w-full text-xs font-mono">
      <thead>
        <tr className="text-slate-500 border-b border-slate-700/50">
          <th className="text-left py-1 pr-2">Name</th>
          <th className="text-center px-1">Pos</th>
          <th className="text-center px-1">AB</th>
          <th className="text-center px-1">R</th>
          <th className="text-center px-1">H</th>
          <th className="text-center px-1">RBI</th>
          <th className="text-center px-1">BB</th>
          <th className="text-center px-1">K</th>
        </tr>
      </thead>
      <tbody>
        {batters.map((b, i) => (
          <tr key={i} className="border-b border-slate-800/50">
            <td className="text-left py-0.5 pr-2 text-slate-300 truncate max-w-[120px]">{b.name}</td>
            <td className="text-center px-1 text-slate-500">{b.pos}</td>
            <td className="text-center px-1 text-slate-300">{b.ab}</td>
            <td className={`text-center px-1 ${b.r > 0 ? 'text-amber-400' : 'text-slate-400'}`}>{b.r}</td>
            <td className={`text-center px-1 ${b.h > 0 ? 'text-white' : 'text-slate-400'}`}>{b.h}</td>
            <td className={`text-center px-1 ${b.rbi > 0 ? 'text-amber-400' : 'text-slate-400'}`}>{b.rbi}</td>
            <td className={`text-center px-1 ${b.bb > 0 ? 'text-blue-400' : 'text-slate-400'}`}>{b.bb}</td>
            <td className={`text-center px-1 ${b.k > 0 ? 'text-red-400' : 'text-slate-400'}`}>{b.k}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PitcherTable({ pitchers }) {
  return (
    <table className="w-full text-xs font-mono">
      <thead>
        <tr className="text-slate-500 border-b border-slate-700/50">
          <th className="text-left py-1 pr-2">Name</th>
          <th className="text-center px-1">IP</th>
          <th className="text-center px-1">H</th>
          <th className="text-center px-1">R</th>
          <th className="text-center px-1">ER</th>
          <th className="text-center px-1">BB</th>
          <th className="text-center px-1">K</th>
          <th className="text-center px-1">HR</th>
        </tr>
      </thead>
      <tbody>
        {pitchers.map((p, i) => (
          <tr key={i} className="border-b border-slate-800/50">
            <td className="text-left py-0.5 pr-2 text-slate-300 truncate max-w-[120px]">{p.name}</td>
            <td className="text-center px-1 text-slate-300">{p.ip}</td>
            <td className={`text-center px-1 ${p.h > 0 ? 'text-white' : 'text-slate-400'}`}>{p.h}</td>
            <td className={`text-center px-1 ${p.r > 0 ? 'text-amber-400' : 'text-slate-400'}`}>{p.r}</td>
            <td className={`text-center px-1 ${p.er > 0 ? 'text-amber-400' : 'text-slate-400'}`}>{p.er}</td>
            <td className={`text-center px-1 ${p.bb > 0 ? 'text-blue-400' : 'text-slate-400'}`}>{p.bb}</td>
            <td className={`text-center px-1 ${p.k > 0 ? 'text-green-400' : 'text-slate-400'}`}>{p.k}</td>
            <td className={`text-center px-1 ${p.hr > 0 ? 'text-red-400' : 'text-slate-400'}`}>{p.hr}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ScoringPlays({ plays }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? plays : plays.slice(0, 3);

  return (
    <div className="bg-slate-900/40 rounded-lg p-2.5 mb-3">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="text-xs text-slate-400 uppercase tracking-wider">Scoring Plays</span>
        {plays.length > 3 && (
          <span className="text-xs text-slate-500">{expanded ? 'collapse' : `+${plays.length - 3} more`}</span>
        )}
      </div>
      <div className="mt-2 space-y-1.5">
        {shown.map((play, i) => {
          const isHR = play.event === 'Home Run';
          return (
            <div key={i} className="text-xs flex gap-2">
              <span className="text-slate-500 shrink-0 w-14 text-right">
                {play.half === 'top' ? '▲' : '▼'} {play.inning}
              </span>
              <span className={`${isHR ? 'text-amber-400' : 'text-slate-300'}`}>
                {isHR && '💣 '}{play.description}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
