const http = require('node:http');
const { scoreTranscript, isConfigured } = require('./src/jev');

const MAX_TRANSCRIPT_LENGTH = 20000;
const MAX_BODY_BYTES = 32768;

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      const error = new Error('Request too large');
      error.status = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    const error = new Error('Invalid JSON');
    error.status = 400;
    throw error;
  }
}

const app = http.createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  if (req.method === 'GET' && path === '/health') {
    return json(res, 200, { ok: true, modelConfigured: isConfigured() });
  }
  if (path !== '/v1/jev/probability') {
    return json(res, 404, { error: 'Not found' });
  }
  if (req.method !== 'POST') {
    return json(res, 405, { error: 'Method not allowed' });
  }

  let body;
  try {
    body = await readJson(req);
  } catch (error) {
    return json(res, error.status || 400, { error: error.message });
  }
  const transcript = body?.transcript;
  if (typeof transcript !== 'string' || transcript.trim().length === 0 ||
      transcript.length > MAX_TRANSCRIPT_LENGTH) {
    return json(res, 400, { error: 'Expected a nonempty transcript of at most 20000 characters' });
  }
  if (!isConfigured()) {
    return json(res, 503, { error: 'JEV_MODEL_URL is not configured' });
  }

  try {
    const probability = await scoreTranscript(transcript);
    return json(res, 200, { probability });
  } catch (error) {
    console.error('JEV inference failed:', error.message);
    return json(res, 503, { error: 'JEV inference unavailable' });
  }
});

if (require.main === module) {
  const port = process.env.PORT || 3000;
  app.listen(port, process.env.HOST || '127.0.0.1', () => console.log(`JEV connector listening on port ${port}`));
}

module.exports = { app };

