import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../app/src/main/assets/demo-probe.js', import.meta.url), 'utf8');
function run(sent) {
  const seen = [];
  class FakeSocket { send(value) { sent.push(value); } }
  const sandbox = { window: { WebSocket: FakeSocket, XtremeDemoBridge: { postMessage: p => seen.push(p) } }, WebSocket: FakeSocket };
  vm.runInNewContext(source, sandbox);
  const socket = new FakeSocket();
  const valid = '42["auth",{"session":"demo-session-123456","uid":123,"isDemo":1}]';
  socket.send('42["other",{"session":"ignored"}]');
  socket.send('42["auth",{"session":"real-account-session","uid":123,"isDemo":0}]');
  socket.send('42["auth",{"session":"fake-account-session","uid":123,"isDemo":"1"}]');
  socket.send(valid);
  socket.send(valid);
  assert.deepEqual(seen, [valid], 'only first demo auth should reach native listener');
  assert.equal(sent.length, 5, 'every WebSocket send must still reach the broker');
}
const wire = []; run(wire);
console.log('PASS: demo-only WebSocket hook forwards untouched frames and redacts real-account auth');
