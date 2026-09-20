# Fechamento operacional do P0

Atualizado em 20/09/2026. O fechamento operacional do P0 já confirmou e-mail
em Gmail/Outlook, rate limiting distribuído com Upstash, checagem de senhas
vazadas via HIBP e a primeira execução do backup cifrado no GitHub Actions.
O replay real assinado do Mercado Pago foi concluído (**P0.5**). O restore do
archive também passou em stack local oficial descartável do Supabase: 11 tabelas
públicas, 527 linhas agregadas e 11 políticas RLS ativas em cada tabela. O commit
`b10485a` está Live no Render com a configuração de MFA simplificada; a regra de
AAL2 exige código em toda sessão de uma conta com TOTP,
inclusive sessão antiga, renovada ou obtida pelo callback; os 202 testes
passaram e `/health` respondeu 200 com banco conectado. O proprietário confirmou
que guardou a chave de restauração em local seguro externo; **P0.11 está
concluído**. Para fechar o P0, resta confirmar um login real com TOTP (**P0.3**).

## 1. E-mail confirmado e reenvio

**Concluído em 18/09/2026:** recebimento, confirmação e reenvio foram
confirmados em contas Gmail e Outlook. Não repetir a configuração; manter os
testes automatizados de regressão. Nenhum token ou link de confirmação deve ser
registrado no repositório.

## 2. Replay controlado do Mercado Pago sem nova cobrança

Reutilize o `payment_id` da compra aprovada. Não inicie outro checkout nem faça
novo pagamento. No PowerShell, na raiz do repositório, execute uma única vez:

```powershell
& '.\scripts\replay_mercadopago_webhook.ps1'
```

O script pede o ID, depois o segredo em campo oculto, valida que ambos foram
preenchidos e só então envia duas vezes a mesma entrega assinada. A saída
mostra somente status HTTP, confirmação, status do pagamento e idempotência; não
imprime o corpo integral da resposta. A segunda entrega precisa retornar
`idempotent: true`.

**Evidência observada em 20/09/2026:** o painel do Mercado Pago está em modo de
produção, aponta para o endpoint acima e mantém habilitado o evento
`Pagamentos (legacy)`. O simulador entregou `payment.updated` com
`live_mode: false` e recebeu HTTP 200. Isso comprova apenas que a URL responde;
não comprova assinatura válida, consulta de pagamento aprovado nem idempotência
real. Esta evidência do simulador foi substituída pelo replay assinado abaixo.

**Teste controlado em 20/09/2026:** duas entregas reais assinadas chegaram ao
endpoint com HTTP 200 e `verified: true`, mas apontavam para uma transação
cancelada; por isso `idempotent` e `receipt` vieram nulos e nenhuma aprovação
foi aplicada. A assinatura e a consulta do evento foram aceitas, mas esse teste
não prova o caminho de pagamento aprovado nem a idempotência. Foi localizada
uma venda do produto de R$ 9,90 com status aprovado; o replay aprovado foi
executado em seguida, sem nova cobrança. O identificador financeiro foi
omitido deste arquivo.

**Replay aprovado concluído em 20/09/2026:** o usuário executou o script com o
`payment_id` da venda aprovada existente e o segredo informado somente no campo
oculto. O script terminou sem erro; por implementação, isso exige HTTP 2xx e
`verified: true` nas duas entregas e `idempotent: true` na segunda. Os logs do
Render confirmaram duas chamadas HTTP 200 ao endpoint. **P0.5 concluído para a
transação testada**, sem criar uma cobrança adicional. O JSON detalhado da
saída não foi preservado nesta sessão; nenhum segredo ou identificador foi
registrado neste arquivo.

## 3. Rate limiting entre instâncias

**Concluído para o ambiente atual:** Redis REST compartilhado do Upstash Free
está configurado como secret no Render e `RATE_LIMIT_DISTRIBUTED_REQUIRED=true`
está ativo. Após o deploy `5d736f2`, `/health` retornou 200 e a tentativa de
login sintética chegou ao Auth (401), sem falha 503 do Redis. Não recriar as
secrets nem repetir o deploy. Validar concorrência entre instâncias quando o
serviço escalar; a chave permanece apenas no Render.

## 4. Proteção contra senhas vazadas sem upgrade

**Concluído sem upgrade:** cadastro e troca de senha consultam a API gratuita
HIBP Pwned Passwords com k-anonimato, enviando somente o prefixo de cinco
caracteres do SHA-1. A checagem está ativa no Render e falha fechada em caso de
erro ou resposta inválida. Testes cobrem senha comprometida e falhas do serviço.
A proteção nativa do Supabase Pro+ é defesa adicional opcional; não há ação
pendente nem necessidade de criar senha real para testar.

## 5. Backup, restauração e agendamento sem plano pago

Não use Render Cron nem faça upgrade Supabase Pro. O workflow
`.github/workflows/supabase-backup.yml` roda diariamente pelo GitHub Actions,
cria um dump PostgreSQL 17, valida com `pg_restore` e envia somente o arquivo
cifrado, com retenção de 30 dias. AES-256-GCM protege o dump; a chave de
conteúdo é envolvida com RSA-OAEP e a chave privada nunca vai para o GitHub.

**Execução confirmada:** `SUPABASE_DATABASE_URL` já está configurada como secret
no GitHub Actions. O run manual #4 (`35486170058`) terminou com sucesso e
armazenou artefato cifrado de 374 KB, com retenção de 30 dias; o agendamento
diário está definido para 05:17 no horário de Brasília. Os binários PostgreSQL
17 foram fixados no commit `eb94f91`. Não é necessário rodar o workflow de novo
nem reenviar a URL do banco.

**Restauração Supabase-compatível concluída em 20/09/2026:** o SHA-256 do
artefato cifrado conferiu com o manifesto, a autenticação AES-256-GCM e a
abertura com a chave privada passaram e o archive custom foi restaurado com
`pg_restore --exit-on-error` no container `supabase_db_codex_restore_p0`, parte
de um stack iniciado pela CLI oficial do Supabase. O destino foi um banco
separado chamado `codex_restore_p0`; a produção não foi acessada durante o
restore. A validação agregada encontrou 11 tabelas públicas, 527 linhas e 11
políticas RLS ativas em todas as 11 tabelas. Os 19 testes de backup/restauração
e a suíte completa de 202 testes passaram. Depois da validação,
o stack foi parado, seus containers e volumes foram removidos pela CLI, e a
pasta temporária foi apagada.

O WSL 2, Docker Desktop e a CLI oficial do Supabase foram usados para essa
validação local. A chave privada continua em
`backups/database/backup-decryption-key.pem`, ignorada pelo Git e não rastreada.
Em 20/09/2026, o proprietário confirmou que guardou uma cópia em local seguro
externo, concluindo **P0.11**. Não enviar a chave ao GitHub, ao Render, ao
repositório ou ao chat.

**Registro histórico — execução local de 19/09/2026 (superado pela restauração
Supabase-compatível acima):** foi criado um dump real do PostgreSQL 17
de produção, com checksum validado. A restauração em PostgreSQL 17 descartável
recuperou as 11 tabelas públicas, as 11 políticas RLS e cerca de 527 linhas
estimadas. Para esse teste em PostgreSQL vanilla, `supabase_vault` e os dados
de `vault.secrets` foram excluídos; ainda é necessário validar a restauração
integral em um projeto Supabase compatível. O dump foi cifrado localmente e o
original em texto puro apagado. O workflow gratuito já agenda o upload cifrado
por 30 dias; àquela data, faltava configurar a secret, guardar a chave fora do
computador, rodar o workflow e confirmar a restauração completa.

**Registro histórico — primeira execução externa em 20/09/2026 (complementado
pela validação de restore acima):** depois de configurar
`SUPABASE_DATABASE_URL` como secret, o GitHub Actions completou o run manual #4
(`35486170058`). O artifact `supabase-backup-35486170058` foi publicado com 374
KB e retenção de 30 dias; os binários `pg_dump` e `pg_restore` foram fixados na
mesma instalação PostgreSQL 17 pelo commit `eb94f91`. O dump enviado ao artifact
está criptografado. A chave privada ainda permanece local e a restauração total
Supabase-compatível não foi demonstrada.
