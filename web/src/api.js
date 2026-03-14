const BASE = import.meta.env.VITE_API_URL || '';

export async function createGame({ awayTeamId, homeTeamId, mode, awayPhilosophy, homePhilosophy, seed }) {
  const res = await fetch(`${BASE}/game/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      away_team_id: awayTeamId,
      home_team_id: homeTeamId,
      mode,
      away_philosophy: awayPhilosophy,
      home_philosophy: homePhilosophy,
      seed: seed || undefined,
    }),
  });
  return res.json();
}

export async function getState(gameId) {
  const res = await fetch(`${BASE}/game/${gameId}/state`);
  return res.json();
}

export async function advanceGame(gameId) {
  const res = await fetch(`${BASE}/game/${gameId}/advance`, { method: 'POST' });
  return res.json();
}

export async function sendDecision(gameId, action, reason = '') {
  const res = await fetch(`${BASE}/game/${gameId}/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, reason }),
  });
  return res.json();
}

export async function getBoxScore(gameId) {
  const res = await fetch(`${BASE}/game/${gameId}/boxscore`);
  return res.json();
}

export async function getLog(gameId) {
  const res = await fetch(`${BASE}/game/${gameId}/log`);
  return res.json();
}

// ── Daily Prediction API ──

export async function getDailyGames(date = 'today') {
  const url = date === 'today' ? `${BASE}/daily/games/today` : `${BASE}/daily/games/${date}`;
  const res = await fetch(url);
  return res.json();
}

export async function submitPrediction({ gameId, gameDate, predictedWinner, predictedAwayScore, predictedHomeScore, confidence }) {
  const res = await fetch(`${BASE}/daily/predictions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      game_id: gameId,
      game_date: gameDate,
      predicted_winner: predictedWinner,
      predicted_away_score: predictedAwayScore,
      predicted_home_score: predictedHomeScore,
      confidence,
    }),
  });
  return res.json();
}

export async function updatePrediction(predictionId, { gameDate, predictedWinner, predictedAwayScore, predictedHomeScore, confidence }) {
  const res = await fetch(`${BASE}/daily/predictions/${predictionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      game_date: gameDate,
      predicted_winner: predictedWinner,
      predicted_away_score: predictedAwayScore,
      predicted_home_score: predictedHomeScore,
      confidence,
    }),
  });
  return res.json();
}

export async function getYesterdayResults() {
  const res = await fetch(`${BASE}/daily/results/yesterday`);
  return res.json();
}

// ── LLM Advisor API ──

export async function getAdvisorProviders() {
  const res = await fetch(`${BASE}/advisor/providers`);
  return res.json();
}

export async function analyzeMatchup(data) {
  const res = await fetch(`${BASE}/advisor/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}
