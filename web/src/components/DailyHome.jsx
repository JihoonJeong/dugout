import { useState, useEffect } from 'react';
import { getDailyGames, getYesterdayResults } from '../api';
import GameCard from './GameCard';
import ResultCard from './ResultCard';
import MyStats from './MyStats';
import Settings from './Settings';

const TEAM_NAMES = {
  NYY: 'Yankees', BOS: 'Red Sox', TBR: 'Rays', BAL: 'Orioles', TOR: 'Blue Jays',
  CLE: 'Guardians', MIN: 'Twins', CHW: 'White Sox', KCR: 'Royals', DET: 'Tigers',
  HOU: 'Astros', SEA: 'Mariners', TEX: 'Rangers', LAA: 'Angels', ATH: 'Athletics',
  NYM: 'Mets', PHI: 'Phillies', ATL: 'Braves', MIA: 'Marlins', WSN: 'Nationals',
  CHC: 'Cubs', MIL: 'Brewers', STL: 'Cardinals', PIT: 'Pirates', CIN: 'Reds',
  LAD: 'Dodgers', SDP: 'Padres', SFG: 'Giants', ARI: 'D-backs', COL: 'Rockies',
};

export default function DailyHome({ onNavigateToGame }) {
  const [tab, setTab] = useState('today'); // today | results
  const [games, setGames] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedGame, setSelectedGame] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    loadData();
  }, [tab]);

  async function loadData() {
    setLoading(true);
    try {
      if (tab === 'today') {
        const data = await getDailyGames();
        setGames(data);
      } else {
        const data = await getYesterdayResults();
        setResults(data);
      }
    } catch (e) {
      console.error('Failed to load:', e);
    }
    setLoading(false);
  }

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="bg-slate-800/80 border-b border-slate-700">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-white">
                <span className="text-amber-400">⚾</span> Dugout Daily
              </h1>
              <p className="text-slate-400 text-sm mt-1">{today}</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowSettings(s => !s)}
                className="px-3 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
                title="Settings"
              >
                ⚙
              </button>
              <button
                onClick={onNavigateToGame}
                className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
              >
                Sim Mode →
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
            <button
              onClick={() => setTab('today')}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                tab === 'today'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Today's Games
            </button>
            <button
              onClick={() => setTab('results')}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                tab === 'results'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Yesterday's Results
            </button>
            <button
              onClick={() => setShowStats(s => !s)}
              className={`py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                showStats
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Stats
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 py-6">
        {showSettings && (
          <div className="mb-6">
            <Settings onClose={() => setShowSettings(false)} />
          </div>
        )}

        {showStats && (
          <div className="mb-6">
            <MyStats onClose={() => setShowStats(false)} />
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-slate-400">
            <div className="text-lg mb-2">Loading predictions...</div>
            <div className="text-sm">Running 1,000 Monte Carlo simulations per game</div>
          </div>
        ) : tab === 'today' ? (
          games.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              No games scheduled for today
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-slate-400 mb-2">
                {games.length} game{games.length !== 1 ? 's' : ''} today — powered by 1,000-sim Monte Carlo engine
              </div>
              {games.map(game => (
                <GameCard
                  key={game.game_id}
                  game={game}
                  teamNames={TEAM_NAMES}
                  onSelect={() => setSelectedGame(game)}
                  onPredictionSubmit={loadData}
                />
              ))}
            </div>
          )
        ) : (
          results.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              No results from yesterday
            </div>
          ) : (
            <div className="space-y-4">
              {results.map(r => (
                <ResultCard key={r.game_id} result={r} teamNames={TEAM_NAMES} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}
