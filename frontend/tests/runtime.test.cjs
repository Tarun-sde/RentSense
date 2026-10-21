/* eslint-disable @typescript-eslint/no-require-imports, @typescript-eslint/no-this-alias */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
// Compile only the small runtime modules under test; no browser or extra runner dependency.
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(
  fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }
).outputText, filename);
const { createQueryClient, apiQuery } = require('../lib/query-client.ts');
const { connectTelemetry } = require('../lib/telemetry-connection.ts');
const { applyTelemetry } = require('../lib/telemetry-cache.ts');

test('successful equipment creation invalidates operational but not reference data', async () => {
  const originalFetch = global.fetch;
  const originalWindow = global.window;
  global.window = {};
  const { getQueryClient } = require('../lib/query-client.ts');
  const client = getQueryClient();
  const { createEquipment } = require('../lib/api.ts');
  client.setQueryData(['api', '/equipment'], []);
  client.setQueryData(['api', '/sites'], []);
  global.fetch = async () => ({ ok: true, json: async () => ({ id: 'new-asset' }) });
  try {
    await createEquipment({ id: 'new-asset', type: 'Excavator', dealer: 'Test', daily_rate: 100 });
    assert.equal(client.getQueryState(['api', '/equipment']).isInvalidated, true);
    assert.equal(client.getQueryState(['api', '/sites']).isInvalidated, false);
  } finally { client.clear(); global.fetch = originalFetch; global.window = originalWindow; }
});

test('cached route revisits deduplicate, failures preserve data, invalidation refreshes', async () => {
  const client = createQueryClient();
  let calls = 0;
  const original = global.fetch;
  global.fetch = async () => { calls++; return { ok: true, json: async () => [{ id: 'asset' }] }; };
  try {
    const query = { ...apiQuery('/equipment'), retry: false };
    await Promise.all([client.fetchQuery(query), client.fetchQuery(query)]);
    await client.fetchQuery(query);
    assert.equal(calls, 1);
    await client.invalidateQueries({ queryKey: query.queryKey });
    global.fetch = async () => { throw new Error('offline'); };
    await assert.rejects(client.fetchQuery(query), /offline/);
    assert.deepEqual(client.getQueryData(query.queryKey), [{ id: 'asset' }]);
    global.fetch = async () => ({ ok: true, json: async () => [{ id: 'recovered' }] });
    assert.deepEqual(await client.fetchQuery(query), [{ id: 'recovered' }]);
  } finally { client.clear(); global.fetch = original; }
});

test('telemetry ignores older packets and bounds history', () => {
  const client = createQueryClient();
  const event = { equipment_id: 'asset', timestamp: new Date().toISOString(), status: 'ACTIVE', utilization_rate: 0.5 };
  const item = { id: 'asset', latest_telemetry: null, recent_telemetry: Array(20).fill({}) };
  client.setQueryData(['api', '/equipment'], [item]);
  client.setQueryData(['api', '/equipment/asset'], item);
  applyTelemetry(client, event);
  applyTelemetry(client, { ...event, timestamp: '2020-01-01', status: 'IDLE' });
  assert.equal(client.getQueryData(['api', '/equipment'])[0].status, 'ACTIVE');
  assert.equal(client.getQueryData(['api', '/equipment/asset']).recent_telemetry.length, 20);
  client.clear();
});

test('SSE open is stale, disconnect schedules bounded retry, cleanup closes everything', () => {
  const originals = Object.fromEntries(['EventSource', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'document'].map(k => [k, global[k]]));
  const timers = new Map(); let next = 0; let source;
  global.setTimeout = global.setInterval = (fn, delay) => { timers.set(++next, { fn, delay }); return next; };
  global.clearTimeout = global.clearInterval = id => timers.delete(id);
  global.document = { hidden: false };
  global.EventSource = class { constructor() { source = this; } addEventListener() {} close() { this.closed = true; } };
  try {
    const states = [];
    const stop = connectTelemetry({ onState: s => states.push(s), onEvent() {}, refresh: async () => {} });
    source.onopen();
    assert.equal(states.at(-1), 'STALE');
    source.onerror();
    assert.equal(source.closed, true);
    assert.ok([...timers.values()].some(t => t.delay >= 5000 && t.delay < 6000));
    stop();
    assert.equal(timers.size, 0);
  } finally { Object.assign(global, originals); }
});
