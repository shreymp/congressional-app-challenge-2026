function isConfigured() {
  return Boolean(process.env.JEV_MODEL_URL);
}

async function scoreTranscript(transcript) {
  if (!isConfigured()) throw new Error('JEV_MODEL_URL is not configured');

  const response = await fetch(process.env.JEV_MODEL_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript }),
    signal: AbortSignal.timeout(2500),
  });
  if (!response.ok) throw new Error(`Model returned HTTP ${response.status}`);

  const result = await response.json();
  if (typeof result.probability !== 'number' || !Number.isFinite(result.probability) ||
      result.probability < 0 || result.probability > 1) {
    throw new Error('Model returned an invalid probability');
  }
  return result.probability;
}

module.exports = { isConfigured, scoreTranscript };
