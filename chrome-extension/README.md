# Candidatura Certa — Copiloto de candidaturas

O copiloto adiciona um botão flutuante somente depois que você abre o complemento numa vaga HTTPS da Gupy, Vagas.com ou InfoJobs e confirma que o portal permite preenchimento assistido. Ao clicar no botão da página e autorizar o uso do perfil, ele consulta campos reconhecidos e vazios, preenche os dados correspondentes e mostra o limite mensal do seu plano. No popup, você também pode selecionar uma candidatura salva, buscar o currículo e a carta atuais na biblioteca e anexá-los aos campos identificados após uma confirmação separada. A revisão e o clique final em **Enviar** continuam com você.

O plano Essencial inclui até 30 preparações assistidas por mês, Start até 150 e Pro e Consultoria até 500. Cada preparação é contabilizada quando você autoriza a consulta do perfil, mesmo se a página não tiver campos compatíveis. O contador renova no primeiro dia do mês pelo horário de Brasília.

O complemento bloqueia LinkedIn, Jobbol e Glassdoor. Ele não faz login nos portais, não envia formulários, não clica nos botões de candidatura, não responde perguntas abertas ou sensíveis, não resolve CAPTCHA e não contorna limites ou verificações. Campos já preenchidos, consentimentos, elegibilidade e pretensão salarial ficam com você; uploads só ocorrem após sua confirmação e em campos identificados como currículo ou carta.

## Instalação de teste

1. Na página **Perfil**, baixe o ZIP do complemento e extraia-o numa pasta local.
2. Use Chrome 116 ou posterior (ou Edge baseado em Chromium equivalente) e abra `chrome://extensions`; no Edge, abra `edge://extensions`.
3. Ative o **Modo do desenvolvedor** e escolha **Carregar sem compactação**.
4. Selecione a pasta extraída que contém `manifest.json`.
5. Abra uma vaga compatível, clique no ícone do complemento e escolha **Conectar minha conta**. A permissão para ler o cookie de acesso dos domínios oficiais da Candidatura Certa é solicitada apenas nesse clique.
6. Na vaga, marque a confirmação de permissão do portal e escolha **Mostrar copiloto nesta página**. Clique no botão flutuante, confirme o uso do perfil e revise os campos.

A distribuição pela Chrome Web Store ou Edge Add-ons ainda não está publicada; por isso esta versão exige instalação de teste pelo modo de desenvolvedor.

## Dados e privacidade

O complemento usa `activeTab`, `scripting`, `sidePanel` e escrita de área de transferência para as ações solicitadas. O acesso aos cookies é opcional e depende de permissão explícita para `candidaturacerta.com.br` e o endereço de serviço antigo no Render. A extensão lê apenas o cookie `HttpOnly` de acesso para autenticar solicitações à API da Candidatura Certa por HTTPS. O token não é guardado no complemento nem exposto à página da vaga; o cookie de renovação fica reservado ao site para preservar a sessão.

O servidor envia à extensão apenas os campos selecionados do perfil da própria conta depois da autorização. Eles ficam em memória no complemento ou no painel lateral enquanto usados. O histórico de uso guarda o domínio do portal, contagem de campos e horários, sem a URL da vaga, o texto preenchido, senhas ou PDFs; esses registros são apagados em até 60 dias. O painel lateral busca o perfil somente após seu clique e oferece trechos do perfil para copiar; não inventa respostas personalizadas para perguntas abertas.

Se você escolher PDFs locais ou buscar documentos na biblioteca e autorizar a anexação, os arquivos são lidos em memória e transferidos diretamente para o campo de upload claramente identificado no portal ativo. A extensão não os armazena. Feche o painel de cópia para deixar de exibir o perfil na tela e use **Desconectar** no popup para revogar a permissão de cookies.

Os eventos `input` e `change` são usados para que o formulário reconheça a alteração de valor. Não são sintetizados gestos humanos, não se clica em envio e não se tenta contornar controles do portal.

## Verificação

Execute os testes unitários do complemento a partir da raiz do projeto:

```sh
node --test tests/chrome-extension.test.cjs
```
