import { useState, useEffect } from 'react';
import { getDailyGames, getYesterdayResults, getManagerNickname } from '../api';
import GameCard from './GameCard';
import ResultCard from './ResultCard';
import MyStats from './MyStats';
import Settings from './Settings';
import Leaderboard from './Leaderboard';

const TEAM_NAMES = {
  // MLB
  NYY: 'Yankees', BOS: 'Red Sox', TBR: 'Rays', BAL: 'Orioles', TOR: 'Blue Jays',
  CLE: 'Guardians', MIN: 'Twins', CHW: 'White Sox', KCR: 'Royals', DET: 'Tigers',
  HOU: 'Astros', SEA: 'Mariners', TEX: 'Rangers', LAA: 'Angels', ATH: 'Athletics',
  NYM: 'Mets', PHI: 'Phillies', ATL: 'Braves', MIA: 'Marlins', WSN: 'Nationals',
  CHC: 'Cubs', MIL: 'Brewers', STL: 'Cardinals', PIT: 'Pirates', CIN: 'Reds',
  LAD: 'Dodgers', SDP: 'Padres', SFG: 'Giants', ARI: 'D-backs', COL: 'Rockies',
  // KBO
  LG: 'Twins', '두산': 'Bears', KIA: 'Tigers', '삼성': 'Lions', '롯데': 'Giants',
  '한화': 'Eagles', SSG: 'Landers', NC: 'Dinos', KT: 'Wiz', '키움': 'Heroes',
  // NPB
  '巨人': 'Giants', '阪神': 'Tigers', '中日': 'Dragons', DeNA: 'BayStars',
  '広島': 'Carp', 'ヤクルト': 'Swallows', 'オリックス': 'Buffaloes',
  'ソフトバンク': 'Hawks', '西武': 'Lions', '楽天': 'Eagles',
  'ロッテ': 'Marines', '日本ハム': 'Fighters',
};

const LEAGUE_FILTERS = [
  { id: 'all', label: 'ALL' },
  { id: 'mlb', label: 'MLB' },
  { id: 'kbo', label: 'KBO' },
  { id: 'npb', label: 'NPB' },
];

export default function DailyHome({ onNavigateToGame, onWatchSim }) {
  const [tab, setTab] = useState('today');
  const [league, setLeague] = useState('all');
  const [games, setGames] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedGame, setSelectedGame] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const managerName = getManagerNickname();

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

  // Filter by league
  const filteredGames = league === 'all' ? games : games.filter(g => (g.league_id || 'mlb') === league);
  const filteredResults = league === 'all' ? results : results.filter(r => (r.league_id || 'mlb') === league);

  // Count games per league
  const leagueCounts = {};
  const sourceList = tab === 'today' ? games : results;
  for (const item of sourceList) {
    const lid = item.league_id || 'mlb';
    leagueCounts[lid] = (leagueCounts[lid] || 0) + 1;
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
              <p className="text-slate-400 text-sm mt-1">
                {today}
                {managerName && <span className="text-amber-400/70 ml-2">— Mgr. {managerName}</span>}
              </p>
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

          {/* League filter tabs */}
          <div className="flex gap-1 mb-3">
            {LEAGUE_FILTERS.map(lf => {
              const count = lf.id === 'all' ? sourceList.length : (leagueCounts[lf.id] || 0);
              const isActive = league === lf.id;
              const hasGames = lf.id === 'all' || count > 0;
              return (
                <button
                  key={lf.id}
                  onClick={() => setLeague(lf.id)}
                  disabled={!hasGames && !loading}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold tracking-wider transition-colors ${
                    isActive
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      : hasGames
                        ? 'text-slate-400 hover:text-white hover:bg-slate-700'
                        : 'text-slate-600 cursor-default'
                  }`}
                >
                  {lf.label}
                  {!loading && count > 0 && <span className="ml-1 text-slate-500 font-normal">{count}</span>}
                </button>
              );
            })}
          </div>

          {/* Day tabs */}
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
            <button
              onClick={() => setShowLeaderboard(s => !s)}
              className={`py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                showLeaderboard
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Ranks
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

        {showLeaderboard && (
          <div className="mb-6">
            <Leaderboard onClose={() => setShowLeaderboard(false)} />
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-slate-400">
            <div className="text-lg mb-2">Loading schedule...</div>
            <div className="text-sm text-slate-500 mt-3 max-w-sm mx-auto leading-relaxed">
              Dugout is in beta and runs on a free-tier server that sleeps when idle.
              The first load may take over a minute — thank you for your patience!
            </div>
          </div>
        ) : tab === 'today' ? (
          filteredGames.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              {league !== 'all' ? `No ${league.toUpperCase()} games scheduled for today` : 'No games scheduled for today'}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-slate-400 mb-2">
                {filteredGames.length} game{filteredGames.length !== 1 ? 's' : ''} today
                {filteredGames.some(g => g.game_type === 'S') && (
                  <span className="ml-2 text-green-400 font-medium">Spring Training</span>
                )}
              </div>
              {filteredGames.map(game => (
                <GameCard
                  key={`${game.league_id || 'mlb'}-${game.game_id}`}
                  game={game}
                  teamNames={TEAM_NAMES}
                  onSelect={() => setSelectedGame(game)}
                  onPredictionSubmit={loadData}
                  onWatchSim={(away, home) => onWatchSim?.(away, home)}
                />
              ))}
            </div>
          )
        ) : (
          filteredResults.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              {league !== 'all' ? `No ${league.toUpperCase()} results from yesterday` : 'No results from yesterday'}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredResults.map(r => (
                <ResultCard key={`${r.league_id || 'mlb'}-${r.game_id}`} result={r} teamNames={TEAM_NAMES} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}
