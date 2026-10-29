(() => {
  "use strict";
  if (window.__xtremeAndroidUiAssisted) return;
  window.__xtremeAndroidUiAssisted = true;
  const badge = document.getElementById('connection');
  const ssid = document.getElementById('ssid');
  const connect = document.getElementById('connect');
  if (!badge || !ssid || !connect) return;
  const label = ssid.closest('label');
  const details = connect.closest('.card')?.querySelector('details');
  const card = connect.closest('.card');
  const hint = document.createElement('p');
  hint.className = 'hint';
  hint.textContent = 'Conta DEMO conectada pelo Android: não é necessário inserir o SSID novamente.';
  hint.hidden = true;
  card?.querySelector('h2')?.after(hint);
  const update = () => {
    const connected = badge.textContent.trim() === 'DEMO CONFIRMADA';
    if (label) label.hidden = connected;
    connect.hidden = connected;
    if (details) details.hidden = connected;
    hint.hidden = !connected;
  };
  new MutationObserver(update).observe(badge, {childList:true, subtree:true, characterData:true});
  update();
})();