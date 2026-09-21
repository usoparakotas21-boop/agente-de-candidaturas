# Candidatura Certa — preparação assistida de candidaturas no Chrome

O complemento prepara formulários de candidatura numa página HTTPS que a própria pessoa abriu. Depois de confirmar que o portal permite preenchimento assistido, marcar a autorização daquela página e clicar em **Preencher campos reconhecidos**, ele completa campos de texto conhecidos e seleciona cidade/estado apenas quando há uma opção exatamente compatível com o perfil. Os campos precisam estar vazios. Depois, a pessoa revisa as respostas e conclui o envio no portal.

O complemento bloqueia páginas do LinkedIn (`linkedin.com` e `linkedin.cn`), Jobbol (`jobbol.com.br`) e Glassdoor (`glassdoor.com`), cujas regras oficiais restringem as extensões ou agentes automatizados. Se a vaga encaminhar para o portal de carreiras do empregador ou para outro ATS, use o complemento somente se esse destino permitir preenchimento assistido.

O complemento não envia formulários, não faz login, não clica em botões do portal, não acessa páginas em segundo plano e não tenta resolver CAPTCHA nem contornar limites ou controles. Opcionalmente, você pode escolher um PDF de currículo e um de carta e autorizar separadamente que sejam anexados aos campos claramente identificados no anúncio ativo. Essa transferência vai para o portal que você abriu; os PDFs não são salvos no armazenamento do complemento. Arquivos não identificados com clareza, consentimentos, elegibilidade, pretensão salarial e respostas abertas continuam manuais. Use apenas em portais que permitam preenchimento e anexação assistidos; se aparecer uma verificação ou uma regra contra automação, pare e continue manualmente.

## Instalação

1. Na página **Perfil** da Candidatura Certa, baixe o complemento e exporte seu perfil depois de salvar as alterações.
2. Extraia o arquivo ZIP para uma pasta local.
3. No Chrome, abra `chrome://extensions`, ative **Modo do desenvolvedor** e escolha **Carregar sem compactação**.
4. Selecione a pasta extraída que contém `manifest.json`.
5. Abra o menu do complemento, importe `candidatura-certa-perfil.json` e confirme o preenchimento apenas quando estiver num formulário compatível.
6. Se o anúncio pedir anexos e o portal permitir, escolha os PDFs atuais do currículo e da carta, marque a autorização de anexação e clique em **Anexar PDFs selecionados nesta página**. Revise os nomes dos arquivos no portal; conclua o envio manualmente.

## Dados e privacidade

O complemento pede somente `activeTab`, `scripting` e `storage`. A permissão da aba ativa é usada após a pessoa clicar no ícone; não há acesso permanente a sites. O perfil importado é guardado em `chrome.storage.local` neste perfil do Chrome e não é enviado à Candidatura Certa nem a outros serviços. PDFs só são lidos quando você os escolhe no popup e autoriza o anexo; eles ficam apenas na memória durante a ação e são transferidos diretamente para o portal ativo. Em computador compartilhado, use **Apagar** para remover o perfil local ao terminar.

Campos de upload que não estejam claramente identificados para currículo ou carta, senhas, caixas de seleção, perguntas abertas, campos ocultos e campos que já têm valor são ignorados. Os PDFs selecionados só são ligados a um campo único e visível com rótulo correspondente; campos ambíguos ficam para preenchimento manual. Selects só são alterados para cidade/estado quando um valor ou rótulo de opção coincide exatamente com a localização do perfil. A extensão não escolhe salário, respostas de elegibilidade ou consentimentos, nem envia uma candidatura.
