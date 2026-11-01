# Pocket Lens Android — APK de teste

Abre o Pocket Lens hospedado e uma WebView separada da Pocket Option oficial. Login por e-mail é feito no site oficial; contas externas como Google não são suportadas neste fluxo. Usuário entra primeiro no Pocket Lens com sua conta Mesa Trader, toca em Conectar e seleciona a conta DEMO no site da corretora.

## Fluxo

Na versão 1.0.2, o script DOCUMENT_START_SCRIPT observa a conexão WebSocket original aberta pela página oficial. O auth é inspecionado localmente apenas para confirmar isDemo=1: SSID, senhas e cookies não são encaminhados. Somente catálogo e dados de mercado permitidos (texto/binário) são enviados ao analisador via Activity e HTTPS. O backend NativeFeed agrega velas e calcula a análise sem abrir outro WebSocket ou refazer autenticação. Comandos no sentido contrário são limitados à assinatura de ativos e histórico. O retorno automático exige primeira cotação real atual, não apenas catálogo. Uma conta real suspende dados até selecionar DEMO.

A sessão da corretora permanece na WebView oficial no telefone. O backend recebe somente dados de mercado e comandos de leitura; o pacote auth não sai pelo relay Android 1.0.2. As cookies normais do WebView oficial podem permanecer no armazenamento privado Android para o próximo login. Backup Android desativado. Certificados TLS nunca são ignorados, tráfego HTTP bloqueado, acesso a arquivos desativado, somente INTERNET solicitada. Sem eventos de negociação no adaptador do analisador.

## Compilar

JDK 17, Gradle 8.9, Android SDK platform 35 e build tools 35.0.0. Execute `gradle testDebugUnitTest assembleDebug` nesta pasta, com ANDROID_HOME definido ou local.properties local (ignorado pelo Git). O APK de teste é assinado com a chave debug local; não é uma publicação da Play Store. WebView debugging desativado também no build debug.

Execute `node test-session-bridge.cjs` para os testes de encaminhamento restrito. Testes Java verificam os limites de origem e esquemas.

## Estado de validação

Compilação e testes automatizados não comprovam login na corretora. O teste real exige um aparelho Android com WebView atualizado e uma sessão do titular. A corretora pode recusar WebViews ou mudar servidores/protocolo. Nesse caso o APK deve informar falha e continuar desconectado; não usa dados simulados. O app não tenta contornar CAPTCHA, 2FA, bloqueios ou certificados. Se a corretora não aceitar este fluxo, não existe confirmação de funcionamento apenas por abrir sua página.

## Atualização 1.0.3

Acompanha múltiplos sockets demo simultâneos, mantendo a origem dos preços e encaminhando comandos somente a uma conexão demo pronta. Fechar um socket secundário não encerra a leitura de outro ativo. Diagnóstico transmite apenas contadores numéricos de preços e comandos, sem credenciais. Interface distingue sessão conectada de cotação ao vivo, oculta o convite para conectar quando autenticado e expõe Desconectar. Uma transmissão Android parada por mais de 15 segundos deixa de ser mostrada como conectada. A verificação em sessão real do usuário continua necessária.
