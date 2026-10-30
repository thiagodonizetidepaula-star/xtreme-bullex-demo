(() => {
  "use strict";
  if (window.__xtremeAndroidUiAssisted) return;
  const badge = document.getElementById('connection');
  const ssid = document.getElementById('ssid');
  const connect = document.getElementById('connect');
  const card = connect?.closest('.card');
  if (!badge || !ssid || !connect || !card) return;
  window.__xtremeAndroidUiAssisted = true;
  // The native user-authorized handoff handles DEMO connection. Do not
  // expose or persist SSID inside the web UI or intercept trade requests.
  const label = ssid.closest('label');
  if (label) label.hidden = true;
  const details = card.querySelector('details');
  if (details) details.hidden = true;
  connect.hidden = true;
  const heading = card.querySelector('h2');
  if (heading) heading.textContent = 'Conexão DEMO pelo Android';
  const hint = document.createElement('p');
  hint.className = 'hint';
  heading?.after(hint);
  const refresh = () => {
    const connected = badge.textContent.trim() === 'DEMO CONFIRMADA';
    hint.textContent = connected
      ? 'Conectado. Aguarde um sinal e toque OPERAR SINAL apenas se quiser enviar aquela ordem.'
      : 'Desconectado. Toque CONECTAR POCKET DEMO no topo do Android. Não precisa copiar SSID.';
  };
  new MutationObserver(refresh).observe(badge, {childList:true, subtree:true, characterData:true});
  refresh();
})();
