# Pocket Lens Android — APK de teste

Abre o Pocket Lens hospedado e uma WebView separada da Pocket Option oficial. Login por e-mail é feito no site oficial; contas externas como Google não são suportadas neste fluxo. Usuário entra primeiro no Pocket Lens com sua conta Mesa Trader, toca em Conectar e seleciona a conta DEMO no site da corretora.

## Fluxo

O script registrado em DOCUMENT_START_SCRIPT observa apenas os pacotes WebSocket `auth` enviados aos servidores `*.po.market/socket.io/`. Não lê formulários, senhas ou cookies. Se `isDemo` for exatamente 1 e o identificador de usuário e sessão forem válidos, encaminha o pacote uma vez à Activity. A Activity, com allowlist de origem e frame principal, o entrega à função do Pocket Lens em HTTPS. O backend valida e abre o feed de leitura existente. O app retorna ao analisador apenas após autenticação e catálogo recebidos. Selecionar conta real cancela a tentativa e desconecta o analisador.

A sessão é uma credencial sensível. O pacote trafega somente pelo telefone e pelo backend próprio Pocket Lens em HTTPS, onde fica na memória; não é gravado em logs ou repositório. As cookies normais do WebView oficial podem permanecer no armazenamento privado Android para o próximo login. Backup Android desativado. Certificados TLS nunca são ignorados, tráfego HTTP bloqueado, acesso a arquivos desativado, somente INTERNET solicitada. Sem eventos de negociação no adaptador do analisador.

## Compilar

JDK 17, Gradle 8.9, Android SDK platform 35 e build tools 35.0.0. Execute `gradle testDebugUnitTest assembleDebug` nesta pasta, com ANDROID_HOME definido ou local.properties local (ignorado pelo Git). O APK de teste é assinado com a chave debug local; não é uma publicação da Play Store. WebView debugging desativado também no build debug.

Execute `node test-session-bridge.cjs` para os testes de encaminhamento restrito. Testes Java verificam os limites de origem e esquemas.

## Estado de validação

Compilação e testes automatizados não comprovam login na corretora. O teste real exige um aparelho Android com WebView atualizado e uma sessão do titular. A corretora pode recusar WebViews ou mudar servidores/protocolo. Nesse caso o APK deve informar falha e continuar desconectado; não usa dados simulados. O app não tenta contornar CAPTCHA, 2FA, bloqueios ou certificados. Se a corretora não aceitar este fluxo, não existe confirmação de funcionamento apenas por abrir sua página.
