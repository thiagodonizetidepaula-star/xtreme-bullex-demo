(() => {
  "use strict";
  if (window.__xtremeAndroidUiAssisted) return;
  const badge = document.getElementById('connection');
  const ssid = document.getElementById('ssid');
  const connect = document.getElementById('connect');
  const card = connect?.closest('.card');
  if (!badge || !ssid || !connect || !card) return;
  window.__xtremeAndroidUiAssisted = true;
  const label = ssid.closest('label');
  const details = card.querySelector('details');
  if (label) label.hidden = true;
  if (details) details.hidden = true;
  connect.hidden = true;
  const heading = card.querySelector('h2');
  if (heading) heading.textContent = '01 / Conexão Pocket Demo no Android';
  const hint = document.createElement('p');
  hint.className = 'hint';
  heading?.after(hint);
  const refresh = () => {
    const connected = badge.textContent.trim() === 'DEMO CONFIRMADA';
    hint.textContent = connected
      ? 'DEMO conectada. Não precisa inserir SSID. Toque TESTE MANUAL 5S no topo para carregar preços.'
      : 'Desconectado. Use CONECTAR POCKET DEMO no topo do Android para reconectar sem SSID.';
  };
  new MutationObserver(refresh).observe(badge, {childList:true, subtree:true, characterData:true});
  refresh();
})();