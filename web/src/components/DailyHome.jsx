import { useState, useEffect } from 'react';
import { getDailyGames, getYesterdayResults, getManagerNickname } from '../api';
import { useLanguage, SUPPORTED_LANGS } from '../i18n/index.jsx';
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

const LEAGUE_IDS = ['all', 'mlb', 'kbo', 'npb'];

export default function DailyHome({ onNavigateToGame, onWatchSim }) {
  const { t, lang, setLang } = useLanguage();
  const [showToday, setShowToday] = useState(true);
  const [showResults, setShowResults] = useState(false);
  const [league, setLeague] = useState('all');
  const [games, setGames] = useState([]);
  const [results, setResults] = useState([]);
  const [loadingGames, setLoadingGames] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [selectedGame, setSelectedGame] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const managerName = getManagerNickname();

  useEffect(() => {
    loadGames();
  }, []);

  useEffect(() => {
    if (showResults && results.length === 0 && !loadingResults) {
      loadResults();
    }
  }, [showResults]);

  async function loadGames() {
    setLoadingGames(true);
    try {
      const data = await getDailyGames();
      setGames(data);
    } catch (e) {
      console.error('Failed to load games:', e);
    }
    setLoadingGames(false);
  }

  async function loadResults() {
    setLoadingResults(true);
    try {
      const data = await getYesterdayResults();
      setResults(data);
    } catch (e) {
      console.error('Failed to load results:', e);
    }
    setLoadingResults(false);
  }

  async function loadData() {
    loadGames();
    if (showResults) loadResults();
  }

  const filteredGames = league === 'all' ? games : games.filter(g => (g.league_id || 'mlb') === league);
  const filteredResults = league === 'all' ? results : results.filter(r => (r.league_id || 'mlb') === league);

  const sourceList = [...games, ...results];
  const leagueCounts = {};
  for (const item of sourceList) {
    const lid = item.league_id || 'mlb';
    leagueCounts[lid] = (leagueCounts[lid] || 0) + 1;
  }

  const today = new Date().toLocaleDateString(lang === 'ko' ? 'ko-KR' : lang === 'ja' ? 'ja-JP' : 'en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="bg-slate-800/80 border-b border-slate-700">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-white">
                <span className="text-amber-400">⚾</span> {t('app.title')}
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                {today}
                {managerName && <span className="text-amber-400/70 ml-2">— Mgr. {managerName}</span>}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* Language toggle */}
              <div className="flex bg-slate-900/50 rounded-md">
                {SUPPORTED_LANGS.map(l => (
                  <button
                    key={l.code}
                    onClick={() => setLang(l.code)}
                    className={`px-2 py-1 text-xs font-medium transition-colors ${
                      lang === l.code
                        ? 'text-amber-400 bg-amber-500/10'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setShowSettings(s => !s)}
                className="px-3 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
                title={t('nav.settings')}
              >
                ⚙
              </button>
              <button
                onClick={onNavigateToGame}
                className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
              >
                {t('app.simMode')} →
              </button>
            </div>
          </div>

          {/* League filter tabs */}
          <div className="flex gap-1 mb-3">
            {LEAGUE_IDS.map(lid => {
              const count = lid === 'all' ? sourceList.length : (leagueCounts[lid] || 0);
              const isActive = league === lid;
              const hasGames = lid === 'all' || count > 0;
              return (
                <button
                  key={lid}
                  onClick={() => setLeague(lid)}
                  disabled={!hasGames && !loading}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold tracking-wider transition-colors ${
                    isActive
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      : hasGames
                        ? 'text-slate-400 hover:text-white hover:bg-slate-700'
                        : 'text-slate-600 cursor-default'
                  }`}
                >
                  {t(`leagues.${lid}`)}
                  {!loading && count > 0 && <span className="ml-1 text-slate-500 font-normal">{count}</span>}
                </button>
              );
            })}
          </div>

          {/* Section toggles */}
          <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
            {[
              { key: 'today', label: t('nav.todayGames'), active: showToday, toggle: () => setShowToday(s => !s) },
              { key: 'results', label: t('nav.yesterday'), active: showResults, toggle: () => setShowResults(s => !s) },
              { key: 'stats', label: t('nav.stats'), active: showStats, toggle: () => setShowStats(s => !s) },
              { key: 'ranks', label: t('nav.ranks'), active: showLeaderboard, toggle: () => setShowLeaderboard(s => !s) },
            ].map(btn => (
              <button
                key={btn.key}
                onClick={btn.toggle}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  btn.active
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {btn.label}
              </button>
            ))}
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

        {showToday && (
          loadingGames ? (
            <div className="text-center py-12 text-slate-400 mb-6">
              <div className="text-lg mb-2">{t('daily.loadingSchedule')}</div>
              <div className="text-sm text-slate-500 mt-3 max-w-sm mx-auto leading-relaxed">
                {t('app.beta')}
              </div>
            </div>
          ) : filteredGames.length === 0 ? (
            <div className="text-center py-8 text-slate-400 mb-6">
              {league !== 'all'
                ? t('daily.noGamesLeague', { league: league.toUpperCase() })
                : t('daily.noGames')}
            </div>
          ) : (
            <div className="space-y-4 mb-6">
              <div className="text-sm text-slate-400 mb-2">
                {t('daily.gamesCount', { count: filteredGames.length })}
                {filteredGames.some(g => g.game_type === 'S') && (
                  <span className="ml-2 text-green-400 font-medium">{t('leagues.springTraining')}</span>
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
        )}

        {showResults && (
          loadingResults ? (
            <div className="text-center py-8 text-slate-400 mb-6">Loading results...</div>
          ) : filteredResults.length === 0 ? (
            <div className="text-center py-8 text-slate-400 mb-6">
              {league !== 'all'
                ? t('daily.noResultsLeague', { league: league.toUpperCase() })
                : t('daily.noResults')}
            </div>
          ) : (
            <div className="space-y-4 mb-6">
              <div className="text-sm text-slate-400 mb-2">
                {t('nav.yesterday')}
              </div>
              {filteredResults.map(r => (
                <ResultCard key={`${r.league_id || 'mlb'}-${r.game_id}`} result={r} teamNames={TEAM_NAMES} />
              ))}
            </div>
          )
        )}

        {!showToday && !showResults && !showStats && !showLeaderboard && (
          <div className="text-center py-12 text-slate-500 text-sm">
            Select a section above
          </div>
        )}
      </div>
    </div>
  );
}
