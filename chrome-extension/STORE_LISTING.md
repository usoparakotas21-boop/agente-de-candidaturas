# Chrome Web Store — ficha pronta da versão 1.0.1

Use estes dados no painel do Chrome Web Store. A submissão só deve ocorrer depois que a página, a política de privacidade e as telas de divulgação estiverem disponíveis publicamente e conferidas.

## Dados da ficha

- Nome: Candidatura Certa — Copiloto
- Resumo: Prepare informações profissionais para vagas da Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br; revise e envie você mesmo no portal.
- Categoria: Produtividade
- Idioma principal: Português (Brasil)
- Página inicial: https://candidaturacerta.com.br/
- Política de privacidade: https://candidaturacerta.com.br/privacidade
- Suporte: https://wa.me/5571991824951
- Ícone: `icons/icon128.png`
- Capturas preparadas: `store-screenshot-popup.png` e `store-screenshot-sidepanel.png` (interfaces reais do popup e do painel lateral; revisar o enquadramento no painel da loja antes do envio).

## Descrição completa

O Copiloto da Candidatura Certa ajuda você a preparar uma candidatura sem sair da vaga aberta em Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br.

Com a sua autorização, ele reconhece formulários compatíveis da Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br, consulta os dados profissionais que você escolheu salvar na sua conta e preenche campos reconhecidos que estejam vazios. Você pode revisar os dados antes de continuar. O painel lateral também oferece compatibilidade estimada e trechos profissionais para copiar.

Se você autorizar separadamente, pode escolher um currículo e uma carta em PDF da sua biblioteca para anexá-los a campos identificados no portal aberto. Os arquivos permanecem em memória e são transferidos somente depois da sua confirmação.

O Copiloto não envia candidaturas, não clica no botão de envio, não responde perguntas abertas, não faz login no portal, não resolve CAPTCHA e não contorna limites. Você revisa os dados e conclui a candidatura no próprio portal. Use o complemento apenas quando as regras do portal permitirem.

Recursos principais:

- Preenchimento assistido de campos profissionais reconhecidos e vazios.
- Compatibilidade estimada entre seu perfil e a vaga.
- Painel lateral com sugestões copiáveis.
- Anexação opcional de currículo e carta depois de confirmação.
- Opção independente e desligada por padrão para enviar dados profissionais selecionados ao Gemini e gerar pontos de conversa.
- Limites de uso apresentados conforme o seu plano Candidatura Certa.

O complemento funciona em computadores com Chrome 116 ou Edge baseado em Chromium equivalente. Não funciona no aplicativo de celular. Compatibilidade de campos varia conforme o formulário de cada vaga.

## Uso de dados e declarações

O complemento processa dados profissionais escolhidos pela pessoa, dados visíveis da vaga ativa, o cookie de acesso à conta da Candidatura Certa após permissão explícita e, somente mediante uma opção independente, dados profissionais selecionados e o texto da vaga enviados à API Gemini do Google. A política de privacidade pública explica cada finalidade, dado, destinatário, prazo e controle da pessoa usuária.

- Os dados servem apenas para os recursos descritos nesta ficha.
- Não há venda de dados, publicidade comportamental ou transferência para corretores de dados.
- O cookie de acesso é usado apenas para autenticar chamadas HTTPS à API da Candidatura Certa e não é armazenado pelo complemento.
- O conteúdo bruto da vaga não é guardado pelo recurso de compatibilidade.
- Os PDFs não são armazenados pela extensão; só seguem para um campo identificado no portal após confirmação.
- O uso do Gemini requer consentimento independente e permanece desativado por padrão.
- A extensão não usa código remoto.

## Justificativa das permissões

- `activeTab`: atuar somente na vaga que a pessoa abriu e escolheu preparar.
- `scripting`: ler os controles visíveis e preencher os campos reconhecidos depois do clique explícito.
- `sidePanel`: exibir sugestões e ações de cópia no painel lateral do navegador.
- `clipboardWrite`: copiar para a área de transferência apenas quando a pessoa aciona uma ação de cópia.
- `cookies` (opcional): ler o cookie de acesso da própria conta Candidatura Certa, somente depois da autorização.
- Domínios opcionais do aplicativo: autenticar e consultar a conta depois da conexão iniciada no popup.
- Domínios opcionais Gupy, Vagas.com, InfoJobs, Catho, Sólides e Empregos.com.br: permitir o botão automático num domínio somente após ação e permissão próprias daquele site. Sem isso, a pessoa ainda pode usar o complemento na aba ativa.

## Antes de enviar para revisão

O pacote 1.0.1, os ícones, a descrição, as justificativas e a política pública estão preparados. No painel da loja, o titular ainda precisa concluir cadastro e declarações legais, enviar o ZIP `app/static/candidatura-certa-autopreenchimento.zip`, incluir ao menos uma captura de tela verdadeira do complemento em uso, preencher as práticas de privacidade com os dados descritos acima e enviar a versão para análise. A extensão só será pública depois da aprovação da loja.
