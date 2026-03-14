import { useState, useEffect } from 'react';
import { Bot, User } from 'lucide-react';

export default function DecisionPanel({ options, aiRecommendation, onDecide, mode }) {
  const [typedText, setTypedText] = useState('');
  const fullText = aiRecommendation?.reason || '';

  useEffect(() => {
    if (!fullText) return;
    setTypedText('');
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setTypedText(fullText.slice(0, i));
      if (i >= fullText.length) clearInterval(timer);
    }, 20);
    return () => clearInterval(timer);
  }, [fullText]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div className="relative bg-slate-800 border-t border-amber-500/30 rounded-t-2xl w-full max-w-2xl p-6 decision-slide-up">
        {/* AI Coach */}
        <div className="flex items-start gap-3 mb-5">
          <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center shrink-0">
            <Bot size={18} className="text-amber-400" />
          </div>
          <div>
            <div className="text-xs text-amber-400 uppercase tracking-wider mb-1">AI Coach</div>
            <div className="text-slate-200 text-sm leading-relaxed">
              {typedText}
              {typedText.length < fullText.length && <span className="cursor-blink" />}
            </div>
            {aiRecommendation && (
              <div className="mt-2 text-xs text-slate-400">
                Recommended: <span className="text-amber-400 font-medium">{aiRecommendation.action}</span>
              </div>
            )}
          </div>
        </div>

        {/* Options */}
        <div className="space-y-2">
          {options.map((opt, i) => {
            const isRecommended = aiRecommendation?.action === opt.action;
            return (
              <button
                key={i}
                onClick={() => onDecide(opt.action)}
                className={`w-full text-left px-4 py-3 rounded-lg border transition-all flex items-center justify-between ${
                  isRecommended
                    ? 'border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20'
                    : 'border-slate-600 bg-slate-700/50 hover:bg-slate-700'
                }`}
              >
                <div>
                  <div className="text-white text-sm font-medium">{opt.label}</div>
                  <div className="text-xs text-slate-400 mt-0.5">{opt.reason}</div>
                </div>
                {isRecommended && (
                  <span className="text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">AI Pick</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
