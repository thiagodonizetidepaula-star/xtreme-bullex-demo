(() => {
  "use strict";
  if (window.__xtremeAndroidUiAssisted) return;
  const badge = document.getElementById('connection');
  const ssid = document.getElementById('ssid');
  const connect = document.getElementById('connect');
  const card = connect?.closest('.card');
  const orderCard = document.getElementById('call')?.closest('.card');
  if (!badge || !ssid || !connect || !card || !orderCard) return;
  window.__xtremeAndroidUiAssisted = true;

  // Android uses a user-authorized in-app DEMO session handoff; hide desktop SSID instructions.
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
      ? 'DEMO conectada. Use TESTE MANUAL 5S acima para receber cotações.'
      : 'Desconectado. Use CONECTAR POCKET DEMO no topo do Android; não precisa copiar SSID.';
  };
  new MutationObserver(refresh).observe(badge, {childList:true, subtree:true, characterData:true});
  refresh();

  // Surface the definitive /api/order response where the user can see it on Android.
  // No auth token, request body, UID or SSID is read or stored by this diagnostic.
  const feedback = document.createElement('p');
  feedback.id = 'xtreme-order-feedback';
  feedback.setAttribute('role', 'status');
  feedback.style.cssText = 'border-left:3px solid #c1ee74;padding:12px;background:#172019;border-radius:7px;line-height:1.5;font-size:13px;color:#edf2f4';
  feedback.textContent = 'Teste manual: toque Compra DEMO ou Venda DEMO e confirme na janela do Android.';
  orderCard.appendChild(feedback);

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const target = args[0];
    const path = typeof target === 'string' ? target : target?.url || '';
    const watched = /^\/api\/(order|auto)$/.test(path);
    if (!watched) return originalFetch(...args);
    feedback.textContent = path === '/api/order'
      ? 'Solicitação de ordem DEMO sendo enviada ao servidor…'
      : 'Solicitação de automático DEMO sendo enviada ao servidor…';
    try {
      const response = await originalFetch(...args);
      const data = await response.clone().json().catch(() => ({}));
      if (!response.ok) {
        const reason = String(data.error || data.message || 'Requisição recusada').slice(0, 220);
        feedback.textContent = 'RECUSADO pelo servidor (' + response.status + '): ' + reason;
      } else {
        feedback.textContent = path === '/api/order'
          ? 'Pedido DEMO recebido pelo servidor. Aguardando confirmação oficial da corretora. Confira histórico e atividade antes de repetir.'
          : 'Pedido de automático DEMO recebido pelo servidor. Confira no painel se ficou realmente ativo.';
      }
      return response;
    } catch (_) {
      feedback.textContent = 'Falha de rede no envio. Confira ordens pendentes na corretora antes de tentar novamente.';
      throw _;
    }
  };
})();
