# Candidatura Certa — Copiloto de candidaturas

O copiloto pode adicionar um botão flutuante numa vaga HTTPS da Gupy, Vagas.com ou InfoJobs. Para usar uma vez, abra o complemento na vaga e confirme que o portal permite preenchimento assistido. Para o botão aparecer automaticamente nas páginas de vagas reconhecidas daquele domínio, escolha **Ativar botão automaticamente neste domínio** e aprove a permissão específica do Chrome. A permissão pode ser revogada pelo mesmo botão. A extensão não lê nem envia seu perfil até você clicar no botão da página, confirmar o uso dos dados e autorizar a preparação.

Após a autorização, o complemento envia à API da Candidatura Certa o título, a descrição visível e os dados selecionados do seu perfil para calcular uma compatibilidade estimada e preparar um resumo direcionado. Por padrão, o texto bruto da vaga não é salvo nem enviado ao Gemini. Os campos reconhecidos e vazios são preenchidos com dados do perfil; se houver um resumo sugerido, ele substitui o resumo base apenas nos campos ainda vazios. Revise cada campo. No painel lateral, você pode analisar a vaga aberta separadamente após consentimento específico e copiar o resumo, as competências e as experiências relevantes. Uma segunda opção, desligada por padrão, autoriza enviar apenas resumo, competências, experiências e texto da vaga ao Google Gemini para produzir pontos de conversa; nome e dados de contato são excluídos. No popup, você também pode selecionar uma candidatura salva, buscar o currículo e a carta atuais na biblioteca e anexá-los aos campos identificados após uma confirmação separada. A revisão e o clique final em **Enviar** continuam com você.

O plano Essencial inclui até 30 preparações assistidas por mês, Start até 150 e Pro e Consultoria até 500. Cada preparação é contabilizada quando você autoriza a consulta do perfil, mesmo se a página não tiver campos compatíveis. O contador renova no primeiro dia do mês pelo horário de Brasília.

O complemento bloqueia LinkedIn, Jobbol e Glassdoor. Ele não faz login nos portais, não envia formulários, não clica nos botões de candidatura, não responde perguntas abertas ou sensíveis, não resolve CAPTCHA e não contorna limites ou verificações. Campos já preenchidos, consentimentos, elegibilidade e pretensão salarial ficam com você; uploads só ocorrem após sua confirmação e em campos identificados como currículo ou carta.

## Instalação de teste

1. Na página **Perfil**, baixe o ZIP do complemento e extraia-o numa pasta local.
2. Use Chrome 116 ou posterior (ou Edge baseado em Chromium equivalente) e abra `chrome://extensions`; no Edge, abra `edge://extensions`.
3. Ative o **Modo do desenvolvedor** e escolha **Carregar sem compactação**.
4. Selecione a pasta extraída que contém `manifest.json`.
5. Abra uma vaga compatível, clique no ícone do complemento e escolha **Conectar minha conta**. A permissão para ler o cookie de acesso dos domínios oficiais da Candidatura Certa é solicitada apenas nesse clique.
6. Na vaga, confirme que o portal permite preenchimento assistido. Escolha **Mostrar copiloto nesta página** para usar uma vez, ou **Ativar botão automaticamente neste domínio** para as próximas páginas de vagas reconhecidas naquele domínio. O Chrome pede a permissão do site somente quando você ativa essa opção.
7. Clique no botão flutuante, confirme o uso do perfil e revise os campos.

A distribuição pela Chrome Web Store ou Edge Add-ons ainda não está publicada; por isso esta versão exige instalação de teste pelo modo de desenvolvedor.

## Dados e privacidade

O complemento usa `activeTab`, `scripting`, `sidePanel` e escrita de área de transferência para as ações solicitadas. O acesso aos cookies é opcional e depende de permissão explícita para `candidaturacerta.com.br` e o endereço de serviço antigo no Render. A permissão automática de um portal é opcional, solicitada por domínio somente depois da sua ação e removida quando você desativa o recurso. A extensão lê apenas o cookie `HttpOnly` de acesso para autenticar solicitações à API da Candidatura Certa por HTTPS. O token não é guardado no complemento nem exposto à página da vaga; o cookie de renovação fica reservado ao site para preservar a sessão.

O servidor envia à extensão apenas os campos selecionados do perfil da própria conta depois da autorização. Eles ficam em memória no complemento ou no painel lateral enquanto usados. Após o clique e consentimento no copiloto ou painel lateral, o navegador envia título, empresa, localidade e até 12.000 caracteres da descrição visível à API própria; a descrição é processada em memória pelo analisador de compatibilidade e personalizador determinísticos e não é persistida. A análise determinística não chama o Gemini. Se você marcar a opção separada para usar Gemini, a plataforma envia à API do Google apenas o resumo, as competências e as experiências profissionais junto com o texto da vaga; nome, e-mail, telefone e links são removidos antes da chamada. O histórico de uso guarda o domínio do portal, contagem de campos e horários, sem a URL da vaga, o texto preenchido, senhas ou PDFs; esses registros são apagados em até 60 dias. O painel lateral busca o perfil ou analisa a vaga somente após consentimento e oferece trechos para copiar; respostas geradas são rascunhos que você deve revisar.

Se você escolher PDFs locais ou buscar documentos na biblioteca e autorizar a anexação, os arquivos são lidos em memória e transferidos diretamente para o campo de upload claramente identificado no portal ativo. A extensão não os armazena. Feche o painel de cópia para deixar de exibir o perfil na tela e use **Desconectar** no popup para revogar a permissão de cookies.

Os eventos `input` e `change` são usados para que o formulário reconheça a alteração de valor. Não são sintetizados gestos humanos, não se clica em envio e não se tenta contornar controles do portal.

## Verificação

Execute os testes unitários do complemento a partir da raiz do projeto:

```sh
node --test tests/chrome-extension.test.cjs
```
