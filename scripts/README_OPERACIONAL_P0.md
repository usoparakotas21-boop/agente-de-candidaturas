# Fechamento operacional do P0

Atualizado em 20/09/2026. O fechamento operacional do P0 já confirmou e-mail
em Gmail/Outlook, rate limiting distribuído com Upstash, checagem de senhas
vazadas via HIBP e a primeira execução do backup cifrado no GitHub Actions.
Restam apenas o replay real assinado do Mercado Pago (**P0.5**) e a cópia
externa da chave privada mais uma restauração integral Supabase-compatível
(**P0.11**). Testes automatizados não substituem essas duas evidências.

## 1. E-mail confirmado e reenvio

**Concluído em 18/09/2026:** recebimento, confirmação e reenvio foram
confirmados em contas Gmail e Outlook. Não repetir a configuração; manter os
testes automatizados de regressão. Nenhum token ou link de confirmação deve ser
registrado no repositório.

## 2. Replay controlado do Mercado Pago sem nova cobrança

Reutilize o `payment_id` da compra aprovada que já gerou os documentos. Não
inicie outro checkout nem faça novo pagamento. Obtenha o `payment_id` no painel
do Mercado Pago. No PowerShell, a partir da raiz do repositório, cole este
bloco. Ele pede o ID do pagamento e lê o segredo sem exibi-lo nem colocá-lo no
histórico de comandos:

```powershell
$env:MERCADOPAGO_WEBHOOK_URL = "https://agente-de-candidaturas.onrender.com/webhooks/mercadopago"
$env:MERCADOPAGO_PAYMENT_ID = Read-Host "ID do pagamento aprovado no Mercado Pago"
$secure = Read-Host "Segredo do webhook do Render" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $env:MERCADOPAGO_WEBHOOK_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  & "C:\Users\xucla\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts/replay_mercadopago_webhook.py
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  Remove-Item Env:MERCADOPAGO_WEBHOOK_SECRET, Env:MERCADOPAGO_PAYMENT_ID -ErrorAction SilentlyContinue
}
```

O script envia duas vezes exatamente a mesma entrega assinada. Como a compra
existente já está paga, ambas podem indicar `idempotent: true`; confirme HTTP
de sucesso, `verified: true`, que não há segunda liberação/recibo e que o
documento continua acessível. Não informe o segredo na linha de comando: o
script lê `MERCADOPAGO_WEBHOOK_SECRET` do ambiente local seguro.

**Evidência observada em 20/09/2026:** o painel do Mercado Pago está em modo de
produção, aponta para o endpoint acima e mantém habilitado o evento
`Pagamentos (legacy)`. O simulador entregou `payment.updated` com
`live_mode: false` e recebeu HTTP 200. Isso comprova apenas que a URL responde;
não comprova assinatura válida, consulta de pagamento aprovado nem idempotência
real. **P0.5 permanece pendente** até o script acima confirmar duas entregas
assinadas para um pagamento existente e aprovado, sem nova cobrança.

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

**Validação local em 20/09/2026:** o SHA-256 do arquivo cifrado confere com o
manifesto; a autenticação AES-256-GCM e a abertura com a chave privada passaram,
e o conteúdo tem assinatura de archive custom PostgreSQL. A chave está em
`backups/database/backup-decryption-key.pem`, ignorada pelo Git e não rastreada.
Os 8 testes de backup passaram. Isso confirma a cifragem e a recuperabilidade do
arquivo, mas ainda não substitui uma restauração Supabase-compatível.

Para concluir **P0.11**, falta somente:

1. Confirmar uma cópia de `backups/database/backup-decryption-key.pem` num
gerenciador de senhas/arquivos seguro fora deste computador. Não enviar a
chave ao GitHub, ao Render, ao repositório ou ao chat.
2. Com a chave disponível no ambiente isolado, restaurar o artefato cifrado em
uma instância Supabase local/compatível descartável e conferir schema, dados
e políticas RLS. Nunca restaurar em produção.

O ambiente atual não tem Docker, Supabase CLI nem `pg_restore`; por isso a
restauração integral não pode ser executada aqui até que exista um runtime local
Supabase compatível.

O PostgreSQL 17 local permitiu uma restauração filtrada, mas não inclui
`supabase_vault`; portanto, isso ainda não é a restauração Supabase-compatível
exigida pelo gate.

**Execução local registrada em 19/09/2026:** foi criado um dump real do PostgreSQL 17
de produção, com checksum validado. A restauração em PostgreSQL 17 descartável
recuperou as 11 tabelas públicas, as 11 políticas RLS e cerca de 527 linhas
estimadas. Para esse teste em PostgreSQL vanilla, `supabase_vault` e os dados
de `vault.secrets` foram excluídos; ainda é necessário validar a restauração
integral em um projeto Supabase compatível. O dump foi cifrado localmente e o
original em texto puro apagado. O workflow gratuito já agenda o upload cifrado
por 30 dias; àquela data, faltava configurar a secret, guardar a chave fora do
computador, rodar o workflow e confirmar a restauração completa.

**Execução externa registrada em 20/09/2026:** depois de configurar
`SUPABASE_DATABASE_URL` como secret, o GitHub Actions completou o run manual #4
(`35486170058`). O artifact `supabase-backup-35486170058` foi publicado com 374
KB e retenção de 30 dias; os binários `pg_dump` e `pg_restore` foram fixados na
mesma instalação PostgreSQL 17 pelo commit `eb94f91`. O dump enviado ao artifact
está criptografado. A chave privada ainda permanece local e a restauração total
Supabase-compatível não foi demonstrada.
