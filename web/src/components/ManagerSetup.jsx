import { useState } from 'react';
import { registerManager, setManagerLocal } from '../api';

export default function ManagerSetup({ onComplete }) {
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const name = nickname.trim();
    if (!name) return;
    if (name.length > 20) {
      setError('20 characters max');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const res = await registerManager(name);
      if (res.manager_id) {
        setManagerLocal(res.manager_id, res.nickname);
        onComplete(res);
      } else {
        setError(res.detail || 'Registration failed');
      }
    } catch (e) {
      setError('Server error. Try again.');
    }
    setSubmitting(false);
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="bg-slate-800/90 border border-slate-700 rounded-2xl p-8 max-w-sm w-full text-center">
        <div className="text-4xl mb-4">⚾</div>
        <h1 className="text-2xl font-bold text-white mb-2">Welcome to Dugout</h1>
        <p className="text-slate-400 text-sm mb-6">
          Enter your manager name to start making predictions
        </p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={nickname}
            onChange={e => setNickname(e.target.value)}
            placeholder="Manager name"
            maxLength={20}
            className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-lg text-white text-center text-lg placeholder-slate-500 focus:outline-none focus:border-amber-500 mb-3"
            autoFocus
          />

          {error && (
            <div className="text-red-400 text-sm mb-3">{error}</div>
          )}

          <button
            type="submit"
            disabled={!nickname.trim() || submitting}
            className="w-full py-3 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-600 disabled:text-slate-400 text-slate-900 font-bold rounded-lg transition-colors"
          >
            {submitting ? 'Registering...' : 'Start Managing'}
          </button>
        </form>

        <p className="text-slate-500 text-xs mt-4">
          Predict game outcomes, compete on the leaderboard
        </p>
      </div>
    </div>
  );
}
