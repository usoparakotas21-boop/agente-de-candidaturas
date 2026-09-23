# Candidatura Certa — preenchimento assistido no Chrome

O complemento preenche campos de texto comuns em uma página que a própria pessoa abriu. Ele só é executado depois de abrir o menu do complemento, marcar a autorização daquela página e clicar em **Preencher campos reconhecidos**. Os campos precisam estar vazios. Depois, a pessoa revisa as respostas e conclui o envio no portal.

O complemento não envia formulários, não faz login, não clica em botões do portal, não abre currículos/arquivos do computador (lê apenas o JSON de perfil que você escolhe importar), não acessa páginas em segundo plano e não tenta resolver CAPTCHA nem contornar limites ou controles. Use apenas em portais que permitam preenchimento assistido; se aparecer uma verificação ou uma regra contra automação, pare e continue manualmente.

## Instalação

1. Na página **Perfil** da Candidatura Certa, baixe o complemento e exporte seu perfil depois de salvar as alterações.
2. Extraia o arquivo ZIP para uma pasta local.
3. No Chrome, abra `chrome://extensions`, ative **Modo do desenvolvedor** e escolha **Carregar sem compactação**.
4. Selecione a pasta extraída que contém `manifest.json`.
5. Abra o menu do complemento, importe `candidatura-certa-perfil.json` e confirme o preenchimento apenas quando estiver num formulário compatível.

## Dados e privacidade

O complemento pede somente `activeTab`, `scripting` e `storage`. A permissão da aba ativa é usada após a pessoa clicar no ícone; não há acesso permanente a sites. O perfil importado é guardado em `chrome.storage.local` neste perfil do Chrome e não é enviado para a Candidatura Certa, para portais ou para outro serviço. Use **Apagar** no menu do complemento para removê-lo deste navegador. Em computador compartilhado, apague os dados ao terminar.

Campos de upload, senhas, caixas de seleção, opções, campos ocultos e campos que já têm valor são ignorados. A extensão não escolhe salário, respostas de elegibilidade ou consentimentos, nem envia uma candidatura.
