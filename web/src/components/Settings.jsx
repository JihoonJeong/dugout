import { useState, useEffect } from 'react';
import { getAdvisorProviders } from '../api';

const PROVIDER_LABELS = {
  anthropic: 'Claude (Anthropic)',
  openai: 'GPT (OpenAI)',
  google: 'Gemini (Google)',
};

export default function Settings({ onClose }) {
  const [providers, setProviders] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState(
    localStorage.getItem('llm_provider') || 'anthropic'
  );
  const [apiKey, setApiKey] = useState(
    localStorage.getItem('llm_api_key') || ''
  );
  const [selectedModel, setSelectedModel] = useState(
    localStorage.getItem('llm_model') || ''
  );
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getAdvisorProviders()
      .then(data => setProviders(data.providers || []))
      .catch(() => {});
  }, []);

  const currentProvider = providers.find(p => p.name === selectedProvider);

  function handleSave() {
    localStorage.setItem('llm_provider', selectedProvider);
    localStorage.setItem('llm_api_key', apiKey);
    localStorage.setItem('llm_model', selectedModel || currentProvider?.default_model || '');
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleClear() {
    localStorage.removeItem('llm_provider');
    localStorage.removeItem('llm_api_key');
    localStorage.removeItem('llm_model');
    setApiKey('');
    setSelectedModel('');
  }

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-white">AI Coach Settings</h2>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">✕</button>
        )}
      </div>

      <p className="text-sm text-slate-400 mb-4">
        Connect your own API key to get AI-powered matchup analysis. Your key stays in your browser — never sent to Dugout servers for storage.
      </p>

      {/* Provider */}
      <div className="mb-4">
        <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Provider</label>
        <div className="flex gap-2">
          {['anthropic', 'openai', 'google'].map(p => (
            <button
              key={p}
              onClick={() => { setSelectedProvider(p); setSelectedModel(''); }}
              className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                selectedProvider === p
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {PROVIDER_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* API Key */}
      <div className="mb-4">
        <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={e => setApiKey(e.target.value)}
          placeholder={selectedProvider === 'anthropic' ? 'sk-ant-...' : selectedProvider === 'openai' ? 'sk-...' : 'AI...'}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm focus:border-amber-500 focus:outline-none"
        />
        <div className="text-xs text-slate-500 mt-1">
          Stored in localStorage only. Used via server proxy (key immediately discarded after API call).
        </div>
      </div>

      {/* Model */}
      {currentProvider && (
        <div className="mb-4">
          <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wider">Model</label>
          <select
            value={selectedModel || currentProvider.default_model}
            onChange={e => setSelectedModel(e.target.value)}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm focus:border-amber-500 focus:outline-none"
          >
            {currentProvider.models.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          className="flex-1 py-2 bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold rounded-lg transition-colors text-sm"
        >
          {saved ? '✓ Saved!' : 'Save'}
        </button>
        <button
          onClick={handleClear}
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors text-sm"
        >
          Clear Key
        </button>
      </div>
    </div>
  );
}
