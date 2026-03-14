import { useState } from 'react';
import { registerManager, setManagerLocal } from '../api';
import { useLanguage, SUPPORTED_LANGS } from '../i18n/index.jsx';

export default function ManagerSetup({ onComplete }) {
  const { t, lang, setLang } = useLanguage();
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
        {/* Language selector */}
        <div className="flex justify-center gap-1 mb-6">
          {SUPPORTED_LANGS.map(l => (
            <button
              key={l.code}
              onClick={() => setLang(l.code)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                lang === l.code
                  ? 'text-amber-400 bg-amber-500/10 border border-amber-500/30'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        <div className="text-4xl mb-4">⚾</div>
        <h1 className="text-2xl font-bold text-white mb-2">{t('manager.welcome')}</h1>
        <p className="text-slate-400 text-sm mb-6">
          {t('manager.chooseNickname')}
        </p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={nickname}
            onChange={e => setNickname(e.target.value)}
            placeholder={t('manager.placeholder')}
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
            {submitting ? t('manager.registering') : t('manager.register')}
          </button>
        </form>
      </div>
    </div>
  );
}
