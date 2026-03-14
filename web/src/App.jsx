import { useState, useEffect, useRef, useCallback } from 'react';
import { getManagerId } from './api';
import ManagerSetup from './components/ManagerSetup';
import DailyHome from './components/DailyHome';
import GameSetup from './components/GameSetup';
import GameHeader from './components/GameHeader';
import MatchupPanel from './components/MatchupPanel';
import DecisionPanel from './components/DecisionPanel';
import LineScore from './components/LineScore';
import PlayLog from './components/PlayLog';
import SpeedControl from './components/SpeedControl';
import { createGame, advanceGame, sendDecision, getBoxScore, getLog } from './api';

export default function App() {
  // Manager registration
  const [hasManager, setHasManager] = useState(!!getManagerId());

  // Top-level mode: daily | sim
  const [mode, setMode] = useState('daily');

  // Sim mode state
  const [screen, setScreen] = useState('setup'); // setup | game | gameover
  const [gameId, setGameId] = useState(null);
  const [gameConfig, setGameConfig] = useState(null);
  const [state, setState] = useState(null);
  const [boxScore, setBoxScore] = useState(null);
  const [plays, setPlays] = useState([]);
  const [decisionData, setDecisionData] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(500);
  const intervalRef = useRef(null);

  const handleStart = useCallback(async (config) => {
    setGameConfig(config);
    const res = await createGame(config);
    setGameId(res.game_id);
    setState(res.state);
    setScreen('game');
    setPlays([]);
    setBoxScore(null);
    setDecisionData(null);
    if (config.mode === 'spectate') {
      setIsPlaying(true);
    }
  }, []);

  const doAdvance = useCallback(async () => {
    if (!gameId || decisionData) return;

    const res = await advanceGame(gameId);
    setState(res.state);

    if (res.decision_required) {
      setDecisionData(res);
      setIsPlaying(false);
      return;
    }

    if (res.play_result) {
      setPlays(prev => [...prev, {
        inning: res.state.inning,
        half: res.state.half,
        event: res.play_result,
        description: res.play_description || res.play_result,
        runs_scored: 0,
      }]);
    }

    if (res.is_game_over) {
      setIsPlaying(false);
      setScreen('gameover');
      const box = await getBoxScore(gameId);
      setBoxScore(box);
      const log = await getLog(gameId);
      setPlays(log);
    }
  }, [gameId, decisionData]);

  const handleDecision = useCallback(async (action) => {
    if (!gameId) return;
    const res = await sendDecision(gameId, action, 'user decision');
    setState(res.state);
    setDecisionData(null);

    if (res.is_game_over) {
      setIsPlaying(false);
      setScreen('gameover');
      const box = await getBoxScore(gameId);
      setBoxScore(box);
      const log = await getLog(gameId);
      setPlays(log);
    } else if (gameConfig?.mode === 'spectate') {
      setIsPlaying(true);
    }
  }, [gameId, gameConfig]);

  // Auto-play loop
  useEffect(() => {
    if (isPlaying && !decisionData && screen === 'game') {
      intervalRef.current = setInterval(doAdvance, speed);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isPlaying, speed, decisionData, screen, doAdvance]);

  // Fetch box score periodically during game
  useEffect(() => {
    if (!gameId || screen === 'setup') return;
    const t = setInterval(async () => {
      const box = await getBoxScore(gameId);
      setBoxScore(box);
    }, 2000);
    return () => clearInterval(t);
  }, [gameId, screen]);

  // Manager registration
  if (!hasManager) {
    return <ManagerSetup onComplete={() => setHasManager(true)} />;
  }

  // Daily mode
  if (mode === 'daily') {
    return <DailyHome onNavigateToGame={() => setMode('sim')} />;
  }

  // Sim mode
  if (screen === 'setup') {
    return (
      <GameSetup
        onStart={handleStart}
        onBack={() => setMode('daily')}
      />
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <GameHeader
        state={state}
        awayId={gameConfig?.awayTeamId}
        homeId={gameConfig?.homeTeamId}
      />

      <div className="flex-1 max-w-2xl mx-auto w-full px-4 py-4 space-y-4">
        <MatchupPanel state={state} />

        {/* Controls */}
        <div className="flex items-center justify-between">
          <SpeedControl
            speed={speed}
            onSpeedChange={setSpeed}
            isPlaying={isPlaying}
            onToggle={() => setIsPlaying(p => !p)}
          />
          {!isPlaying && screen === 'game' && !decisionData && (
            <button
              onClick={doAdvance}
              className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
            >
              Next Play
            </button>
          )}
        </div>

        <LineScore
          boxScore={boxScore}
          awayId={gameConfig?.awayTeamId}
          homeId={gameConfig?.homeTeamId}
        />

        <PlayLog plays={plays} />

        {/* Game Over */}
        {screen === 'gameover' && boxScore && (
          <div className="bg-slate-800/80 rounded-xl border border-amber-500/30 p-6 text-center">
            <div className="text-2xl font-bold text-white mb-2">Final</div>
            <div className="font-mono text-4xl text-amber-400 score-glow mb-4">
              {boxScore.score.away} — {boxScore.score.home}
            </div>
            <div className="text-slate-300 mb-4">
              Winner: {boxScore.winner === 'away' ? gameConfig?.awayTeamId : gameConfig?.homeTeamId}
            </div>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => { setScreen('setup'); setGameId(null); }}
                className="px-6 py-2 bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold rounded-lg transition-colors"
              >
                New Game
              </button>
              <button
                onClick={() => { setMode('daily'); setScreen('setup'); setGameId(null); }}
                className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
              >
                Daily Picks
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Decision Panel */}
      {decisionData && (
        <DecisionPanel
          options={decisionData.decision_options}
          aiRecommendation={decisionData.ai_recommendation}
          onDecide={handleDecision}
          mode={gameConfig?.mode}
        />
      )}
    </div>
  );
}
