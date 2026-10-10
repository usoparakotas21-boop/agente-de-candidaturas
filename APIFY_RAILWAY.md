# Apify no Railway

Esta aplicação já tem o conector pronto para o Actor `hKByXkMQaC5Qt9UMN`. A publicação usa somente o Dataset produzido pelo Actor; não há scraping direto dentro do site.

## Configuração única

1. No Apify, execute o Actor e copie o **Dataset ID** da execução que contém as vagas.
2. No Railway, abra o serviço de produção `truthful-vision` → **Variables** e adicione os valores abaixo. `APIFY_API_TOKEN` é segredo e deve ser colado somente no Railway.

```text
APIFY_API_TOKEN=<token do Apify>
APIFY_DATASET_ID=<dataset da execução>
APIFY_SOURCE_APPROVED=true
APIFY_PERMISSION_EVIDENCE=Autorização registrada pelo proprietário do projeto em 2026-10-10
APIFY_TERMS_REFERENCE=https://console.apify.com/actors/hKByXkMQaC5Qt9UMN/info/readme
APIFY_ROBOTS_REVIEW=Revisão da fonte mantida pelo operador; atualizar quando a política da fonte mudar.
```

O Railway faz um novo deploy ao salvar as variáveis. O conector falha fechado se token, Dataset ou registro de autorização estiverem ausentes.

## Sincronização

Depois que o deploy terminar, entre no painel de desenvolvedor e clique em **Sincronizar vagas autorizadas do Apify**. O sistema lê até 500 itens, normaliza cargo, empresa, local, modalidade, salário e URL, elimina duplicadas por origem e grava a data/origem de cada vaga.

O endpoint usado é `https://api.apify.com/v2/datasets/<DATASET_ID>/items?clean=true&format=json`. O Actor continua sendo executado no Apify; o Railway apenas lê o resultado autorizado.

## Operação segura

- Nunca coloque o token no GitHub, em arquivos `.env` versionados ou em mensagens.
- Troque o `APIFY_DATASET_ID` quando quiser apontar para uma nova execução.
- Se a fonte ficar sem autorização, defina `APIFY_SOURCE_APPROVED=false`; a sincronização será bloqueada sem apagar o catálogo já salvo.
- A origem e a data ficam disponíveis na inteligência de mercado para que cada análise possa ser auditada.
