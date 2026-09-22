# Modelo de autorização de fonte de vagas

Use uma cópia deste documento para cada fonte ou quadro que autorizar. O
registro preenchido deve ser acompanhado do contrato, termo, e-mail ou outra
evidência verificável do titular da fonte. Preencher este modelo não ativa a
coleta: a fonte só entra no registro operacional depois da revisão e do
cadastro da evidência.

## Identificação

- `source_id`:
- Nome do fornecedor:
- Empresa ou proprietário do quadro:
- Domínios exatos autorizados:
- Responsável do fornecedor e cargo:
- Responsável interno pela revisão:
- Data da autorização:
- Data da próxima revisão (máximo de 180 dias):

## Endpoint e escopo técnico

- URL base e caminho do endpoint/feed:
- Método e autenticação (descrever sem colar tokens ou senhas):
- Identificador da conta/contrato que recebeu a permissão:
- Limite por minuto/hora/dia:
- Concorrência máxima:
- Intervalo mínimo entre requisições:
- Resultado da revisão de `robots.txt` e restrições do endpoint:
- Campos que podem ser buscados:
  - [ ] título
  - [ ] empresa
  - [ ] localidade
  - [ ] modalidade
  - [ ] tipo de contrato
  - [ ] faixa salarial
  - [ ] descrição resumida
  - [ ] data de publicação/validade
  - [ ] identificador externo
  - [ ] URL canônica de candidatura
  - [ ] outro:

## Usos autorizados

Marque somente os usos que a evidência realmente cobre:

- [ ] `automated_fetch` — buscar o feed em intervalo definido
- [ ] `commercial_display` — exibir oportunidades no Candidatura Certa
- [ ] `ai_processing` — classificar ou resumir campos autorizados
- [ ] `description_caching` — guardar descrição por prazo definido
- [ ] `redistribution` — republicar campos no produto
- [ ] `automated_submission` — enviar candidatura por integração oficial

Se `automated_submission` estiver marcado, anexe o escopo do endpoint, os
campos, anexos, destinatários, confirmação por vaga e a autorização separada
da pessoa candidata. Autorização de coleta ou exibição nunca libera envio.

## Atribuição e retenção

- Texto ou marca de atribuição exigida:
- URL canônica que deve acompanhar a vaga:
- Prazo de retenção do anúncio:
- Prazo de retenção do conteúdo bruto:
- Como solicitar retirada/correção:
- Prazo para expirar e purgar uma vaga retirada:
- Campos pessoais proibidos de armazenar:
- Condição de desligamento imediato:

## Evidência

- Tipo de evidência: contrato / licença / e-mail / painel / documentação da API
- URL da versão dos termos ou contrato:
- Data em que a evidência foi consultada:
- Arquivo ou referência interna da cópia arquivada:
- Hash SHA-256 da cópia, quando permitido:
- Observações e limitações:

## Aprovação

- Revisão jurídica concluída por:
- Revisão técnica concluída por:
- Direitos confirmados para todos os usos marcados: sim / não
- Endpoint testado em ambiente de validação: sim / não
- Atribuição conferida: sim / não
- Plano de desligamento testado: sim / não
- Decisão: aprovado / aprovado com restrições / recusado
- Assinatura ou confirmação do responsável:
- Data:

## Dados que não devem ser enviados neste arquivo

Não registrar tokens, chaves privadas, senhas, cookies, URLs de banco ou
credenciais de produção. Esses valores ficam apenas no gerenciador de segredos
do Render ou no ambiente protegido de execução. O worker continua bloqueado
enquanto não houver uma entrada aprovada no `SOURCE_REGISTRY`.

Para revisar um registro antes de enviá-lo para cadastro, salve os campos em
JSON usando os mesmos nomes abaixo e execute:

```text
python scripts/validate_source_authorization.py caminho/da-fonte.json
```

O comando apenas valida o formato e informa as lacunas. Mesmo que o resultado
seja "pronto", ele não cadastra nem ativa a fonte; a evidência ainda precisa
ser revisada e registrada no servidor por uma pessoa autorizada.

Depois da revisão jurídica e técnica, os registros aprovados podem ser
colocados juntos no segredo `SOURCE_AUTHORIZATION_RECORDS_JSON` do Render como
um objeto JSON ou uma lista de objetos. O scheduler e o worker validam todos os
registros antes de ativar qualquer um; se um registro estiver pendente, nenhum
é carregado. Essa variável não deve conter tokens ou senhas. As credenciais do
endpoint, quando existirem, ficam em variáveis separadas do Render.
