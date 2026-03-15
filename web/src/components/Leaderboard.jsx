import { useState, useEffect } from 'react';
import { getLeaderboard, getManagerId } from '../api';
import { useLanguage } from '../i18n/index.jsx';

export default function Leaderboard({ onClose }) {
  const { t } = useLanguage();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const myId = getManagerId();

  useEffect(() => {
    getLeaderboard()
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-4 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">{t('leaderboard.title')}</h3>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">Close</button>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-6">Loading...</div>
      ) : data.length === 0 ? (
        <div className="text-center text-slate-400 py-6 text-sm">
          {t('leaderboard.noPredictions')}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs border-b border-slate-700">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2 px-2">Manager</th>
                <th className="text-right py-2 px-2">Avg Pts</th>
                <th className="text-right py-2 px-2">Win%</th>
                <th className="text-right py-2 px-2">Exact</th>
                <th className="text-right py-2 px-2">Games</th>
              </tr>
            </thead>
            <tbody>
              {data.map((entry, i) => {
                const isMe = entry.manager_id === myId;
                return (
                  <tr
                    key={entry.manager_id}
                    className={`border-b border-slate-700/50 ${isMe ? 'bg-amber-500/10' : ''}`}
                  >
                    <td className="py-2 px-2 text-slate-400">
                      {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}
                    </td>
                    <td className={`py-2 px-2 font-medium ${isMe ? 'text-amber-400' : 'text-white'}`}>
                      {entry.nickname}
                      {entry.manager_id && (
                        <span className="text-xs text-slate-500 ml-1">({entry.manager_id})</span>
                      )}
                      {isMe && <span className="text-xs text-amber-500/70 ml-1">← you</span>}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-amber-400">
                      {entry.avg_points.toFixed(1)}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-slate-300">
                      {(entry.win_accuracy * 100).toFixed(0)}%
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-purple-400">
                      {entry.exact_scores}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-slate-400">
                      {entry.total_scored}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="text-xs text-slate-500 mt-2 text-center">
            {data[0]?.season === 'S' ? t('stats.springTraining') : t('stats.regularOnly')}
          </div>
        </div>
      )}
    </div>
  );
}
