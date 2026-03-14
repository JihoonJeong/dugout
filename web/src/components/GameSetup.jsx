import { useState } from 'react';
import { Play } from 'lucide-react';

const TEAMS = [
  'ARI','ATH','ATL','BAL','BOS','CHC','CHW','CIN','CLE','COL','DET',
  'HOU','KCR','LAA','LAD','MIA','MIL','MIN','NYM','NYY',
  'PHI','PIT','SDP','SEA','SFG','STL','TBR','TEX','TOR','WSN',
];

const PHILOSOPHIES = [
  { value: 'analytics', label: 'Analytics' },
  { value: 'moneyball', label: 'Moneyball' },
  { value: 'old_school', label: 'Old School' },
  { value: 'win_now', label: 'Win Now' },
  { value: 'development', label: 'Development' },
];

const MODES = [
  { value: 'spectate', label: 'Spectate', desc: 'AI vs AI — watch and learn' },
  { value: 'advise', label: 'Advise', desc: 'AI recommends, you decide' },
  { value: 'manage', label: 'Manage', desc: 'You call the shots' },
];

export default function GameSetup({ onStart, onBack }) {
  const [away, setAway] = useState('NYY');
  const [home, setHome] = useState('BOS');
  const [mode, setMode] = useState('spectate');
  const [awayPhil, setAwayPhil] = useState('analytics');
  const [homePhil, setHomePhil] = useState('analytics');

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="bg-slate-800/80 rounded-2xl p-8 w-full max-w-lg border border-slate-700">
        <h1 className="text-3xl font-bold text-center mb-1 text-white tracking-tight">
          DUGOUT
        </h1>
        <p className="text-center text-slate-400 text-sm mb-8">AI Baseball Manager</p>

        {onBack && (
          <button
            onClick={onBack}
            className="mb-4 text-sm text-slate-400 hover:text-white transition-colors"
          >
            ← Back to Daily Picks
          </button>
        )}

        {/* Teams */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Away</label>
            <select value={away} onChange={e => setAway(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white font-mono text-lg">
              {TEAMS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Home</label>
            <select value={home} onChange={e => setHome(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white font-mono text-lg">
              {TEAMS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        {/* Mode */}
        <div className="mb-6">
          <label className="block text-xs text-slate-400 mb-2 uppercase tracking-wider">Mode</label>
          <div className="space-y-2">
            {MODES.map(m => (
              <button key={m.value}
                onClick={() => setMode(m.value)}
                className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
                  mode === m.value
                    ? 'border-amber-500 bg-amber-500/10 text-white'
                    : 'border-slate-600 bg-slate-900/50 text-slate-300 hover:border-slate-500'
                }`}>
                <div className="font-medium">{m.label}</div>
                <div className="text-xs text-slate-400 mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Philosophy */}
        <div className="grid grid-cols-2 gap-4 mb-8">
          <div>
            <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Away AI</label>
            <select value={awayPhil} onChange={e => setAwayPhil(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white">
              {PHILOSOPHIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Home AI</label>
            <select value={homePhil} onChange={e => setHomePhil(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white">
              {PHILOSOPHIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
        </div>

        {/* Start */}
        <button
          onClick={() => onStart({ awayTeamId: away, homeTeamId: home, mode, awayPhilosophy: awayPhil, homePhilosophy: homePhil })}
          className="w-full bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors">
          <Play size={20} />
          Play Ball
        </button>
      </div>
    </div>
  );
}
