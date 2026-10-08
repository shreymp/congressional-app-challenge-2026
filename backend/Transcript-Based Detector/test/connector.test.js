const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { app } = require('../server');
const { scoreTranscript } = require('../src/jev');

test('API forwards each transcript to JEV and returns its probability', async () => {
  const received = [];
  let modelReply = { probability: 0.82 };
  const model = http.createServer(async (req, res) => {
    let payload = '';
    for await (const chunk of req) payload += chunk;
    received.push(JSON.parse(payload));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(modelReply));
  });
  model.listen(0, '127.0.0.1');
  await new Promise((resolve) => model.once('listening', resolve));
  const server = app.listen(0, '127.0.0.1');
  await new Promise((resolve) => server.once('listening', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = async (transcript) => {
    const response = await fetch(`${base}/v1/jev/probability`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    return { status: response.status, body: await response.json() };
  };

  try {
    delete process.env.JEV_MODEL_URL;
    assert.equal((await post('hello')).status, 503);
    assert.equal(received.length, 0);

    process.env.JEV_MODEL_URL = `http://127.0.0.1:${model.address().port}`;
    assert.deepEqual(await post('Send me the code'), {
      status: 200,
      body: { probability: 0.82 },
    });
    assert.deepEqual(received, [{ transcript: 'Send me the code' }]);
    assert.equal((await post('')).status, 400);
    assert.equal(received.length, 1);

    modelReply = { probability: 1.2 };
    await assert.rejects(scoreTranscript('test'), /invalid probability/);
  } finally {
    delete process.env.JEV_MODEL_URL;
    await new Promise((resolve) => server.close(resolve));
    await new Promise((resolve) => model.close(resolve));
  }
});
