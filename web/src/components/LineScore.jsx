export default function LineScore({ boxScore, awayId, homeId }) {
  if (!boxScore) return null;

  const { runs_by_inning: rbi, score, hits } = boxScore;
  const maxInnings = Math.max(rbi.away?.length || 0, rbi.home?.length || 0, 9);

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-4 overflow-x-auto">
      <table className="w-full font-mono text-sm">
        <thead>
          <tr className="text-slate-400">
            <th className="text-left w-16 pr-2"></th>
            {Array.from({ length: maxInnings }, (_, i) => (
              <th key={i} className="w-8 text-center">{i + 1}</th>
            ))}
            <th className="w-10 text-center border-l border-slate-600 pl-2">R</th>
            <th className="w-10 text-center">H</th>
          </tr>
        </thead>
        <tbody>
          <tr className="text-white">
            <td className="text-slate-300 font-medium pr-2">{awayId}</td>
            {Array.from({ length: maxInnings }, (_, i) => (
              <td key={i} className="text-center text-slate-300">
                {rbi.away?.[i] !== undefined ? rbi.away[i] : ''}
              </td>
            ))}
            <td className="text-center border-l border-slate-600 pl-2 font-bold">{score.away}</td>
            <td className="text-center">{hits.away}</td>
          </tr>
          <tr className="text-white">
            <td className="text-slate-300 font-medium pr-2">{homeId}</td>
            {Array.from({ length: maxInnings }, (_, i) => (
              <td key={i} className="text-center text-slate-300">
                {rbi.home?.[i] !== undefined ? rbi.home[i] : (i < maxInnings - 1 || boxScore.is_game_over ? '' : '')}
              </td>
            ))}
            <td className="text-center border-l border-slate-600 pl-2 font-bold">{score.home}</td>
            <td className="text-center">{hits.home}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
