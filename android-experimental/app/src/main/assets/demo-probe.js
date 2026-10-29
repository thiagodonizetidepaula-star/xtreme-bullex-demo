// Experimental: inject at document start only on approved Pocket Option origins.
// Observe ONLY an outbound Socket.IO "auth" packet with isDemo: 1.
// Do not inspect passwords, localStorage, cookies, network responses or other messages.
(() => {
  "use strict";
  if (window.__xtremeDemoProbeInstalled || !window.WebSocket) return;
  window.__xtremeDemoProbeInstalled = true;
  const send = WebSocket.prototype.send;
  let detected = false;
  WebSocket.prototype.send = function (...args) {
    const data = args[0];
    try {
      if (!detected && typeof data === "string" && data.startsWith('42["auth",')) {
        const parsed = JSON.parse(data.slice(2));
        const auth = parsed && parsed[0] === "auth" ? parsed[1] : null;
        if (auth && auth.isDemo === 1 && Number.isInteger(auth.uid)
            && auth.uid > 0 && typeof auth.session === "string"
            && auth.session.length >= 10 && auth.session.length <= 16000) {
          detected = true;
          window.XtremeDemoBridge?.postMessage(data);
        }
      }
    } catch (_) { /* Never print payloads to console. */ }
    return send.apply(this, args);
  };
})();
