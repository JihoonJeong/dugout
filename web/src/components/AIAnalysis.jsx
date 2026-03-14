import { useState } from 'react';
import { analyzeMatchup } from '../api';
import { useLanguage } from '../i18n/index.jsx';

const TEAM_NAMES = {
  // MLB
  NYY: 'New York Yankees', BOS: 'Boston Red Sox', TBR: 'Tampa Bay Rays',
  BAL: 'Baltimore Orioles', TOR: 'Toronto Blue Jays',
  CLE: 'Cleveland Guardians', MIN: 'Minnesota Twins', CHW: 'Chicago White Sox',
  KCR: 'Kansas City Royals', DET: 'Detroit Tigers',
  HOU: 'Houston Astros', SEA: 'Seattle Mariners', TEX: 'Texas Rangers',
  LAA: 'Los Angeles Angels', ATH: 'Athletics',
  NYM: 'New York Mets', PHI: 'Philadelphia Phillies', ATL: 'Atlanta Braves',
  MIA: 'Miami Marlins', WSN: 'Washington Nationals',
  CHC: 'Chicago Cubs', MIL: 'Milwaukee Brewers', STL: 'St. Louis Cardinals',
  PIT: 'Pittsburgh Pirates', CIN: 'Cincinnati Reds',
  LAD: 'Los Angeles Dodgers', SDP: 'San Diego Padres', SFG: 'San Francisco Giants',
  ARI: 'Arizona Diamondbacks', COL: 'Colorado Rockies',
  // KBO
  LG: 'LG Twins', '두산': 'Doosan Bears', KIA: 'KIA Tigers', '삼성': 'Samsung Lions',
  '롯데': 'Lotte Giants', '한화': 'Hanwha Eagles', SSG: 'SSG Landers',
  NC: 'NC Dinos', KT: 'KT Wiz', '키움': 'Kiwoom Heroes',
  // NPB
  '巨人': 'Yomiuri Giants', '阪神': 'Hanshin Tigers', '中日': 'Chunichi Dragons',
  DeNA: 'Yokohama DeNA BayStars', '広島': 'Hiroshima Carp', 'ヤクルト': 'Tokyo Yakult Swallows',
  'オリックス': 'Orix Buffaloes', 'ソフトバンク': 'Fukuoka SoftBank Hawks',
  '西武': 'Saitama Seibu Lions', '楽天': 'Tohoku Rakuten Golden Eagles',
  'ロッテ': 'Chiba Lotte Marines', '日本ハム': 'Hokkaido Nippon-Ham Fighters',
};

export default function AIAnalysis({ game, onClose }) {
  const { t } = useLanguage();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const hasKey = !!localStorage.getItem('llm_api_key');

  async function handleAnalyze() {
    const provider = localStorage.getItem('llm_provider') || 'anthropic';
    const apiKey = localStorage.getItem('llm_api_key');
    const model = localStorage.getItem('llm_model') || '';

    if (!apiKey) {
      setError('No API key configured. Go to Settings to add your key.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await analyzeMatchup({
        provider,
        api_key: apiKey,
        model: model || undefined,
        away_team_id: game.away_team_id,
        home_team_id: game.home_team_id,
        away_team_name: TEAM_NAMES[game.away_team_id] || game.away_team_id,
        home_team_name: TEAM_NAMES[game.home_team_id] || game.home_team_id,
        away_starter_name: game.away_starter_name,
        home_starter_name: game.home_starter_name,
        venue: game.venue,
        game_time: game.game_time,
        engine_away_win_pct: game.final_away_win_pct,
        engine_home_win_pct: game.final_home_win_pct,
        engine_avg_away_runs: game.mc_avg_away_runs,
        engine_avg_home_runs: game.mc_avg_home_runs,
        engine_avg_total_runs: game.mc_avg_total_runs,
      });

      if (result.error) {
        setError(result.error);
      } else {
        setAnalysis(result);
      }
    } catch (e) {
      setError(e.message || 'Analysis failed');
    }
    setLoading(false);
  }

  if (!analysis && !loading && !error) {
    return (
      <div className="mt-3 border-t border-slate-700 pt-3">
        <button
          onClick={handleAnalyze}
          disabled={!hasKey}
          className={`w-full py-2 rounded-lg text-sm font-medium transition-colors ${
            hasKey
              ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
          }`}
        >
          {hasKey ? `🤖 ${t('ai.analyze')}` : `🤖 ${t('ai.setupKey')}`}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-slate-700 pt-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-purple-400 uppercase tracking-wider font-medium">{t('ai.title')}</span>
        {onClose && (
          <button onClick={() => { setAnalysis(null); setError(null); onClose?.(); }}
            className="text-slate-500 hover:text-white text-xs">✕</button>
        )}
      </div>

      {loading && (
        <div className="text-center py-4 text-slate-400 text-sm">
          <div className="cursor-blink">{t('ai.analyzing')}</div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {analysis && (
        <div className="space-y-3">
          {/* Prediction */}
          <div className="flex items-center justify-between bg-slate-900/50 rounded-lg p-3">
            <div>
              <span className="text-xs text-slate-500">AI Pick:</span>
              <span className="ml-2 text-white font-bold">
                {analysis.predicted_winner === 'away' ? game.away_team_id : game.home_team_id}
              </span>
              <span className="ml-1 text-slate-400 text-sm">
                ({(analysis.confidence * 100).toFixed(0)}%)
              </span>
            </div>
            {analysis.predicted_away_score != null && (
              <div className="font-mono text-white">
                {analysis.predicted_away_score} - {analysis.predicted_home_score}
              </div>
            )}
          </div>

          {/* Analysis text */}
          <p className="text-sm text-slate-300 leading-relaxed">
            {analysis.analysis}
          </p>

          {/* Key factors */}
          {analysis.key_factors?.length > 0 && (
            <div>
              <div className="text-xs text-slate-500 mb-1">{t('ai.keyFactors')}</div>
              <ul className="space-y-1">
                {analysis.key_factors.map((f, i) => (
                  <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">•</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk factors */}
          {analysis.risk_factors?.length > 0 && (
            <div>
              <div className="text-xs text-slate-500 mb-1">{t('ai.risks')}</div>
              <ul className="space-y-1">
                {analysis.risk_factors.map((f, i) => (
                  <li key={i} className="text-xs text-red-400/70 flex items-start gap-1.5">
                    <span className="text-red-500 mt-0.5">⚠</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Meta */}
          <div className="text-xs text-slate-600">
            {analysis.provider}/{analysis.model} • {analysis.tokens_used} tokens
          </div>
        </div>
      )}
    </div>
  );
}
