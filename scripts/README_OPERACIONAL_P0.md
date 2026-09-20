# Fechamento operacional do P0

Os testes automatizados e a implementação já estão no repositório. Os cinco
itens abaixo exigem uma evidência no ambiente externo; nenhum deles deve ser
marcado como concluído apenas por teste local.

## 1. E-mail confirmado e reenvio

Use duas contas de teste que você controle, de provedores diferentes (por
exemplo Gmail e Outlook). Para cada uma:

1. Crie a conta na tela pública e confirme que o checkbox está desmarcado por
   padrão.
2. Abra o e-mail recebido, confirme pelo link e entre no painel.
3. Crie uma segunda conta com o mesmo endereço, ou use uma conta pendente, e
   acione **Reenviar confirmação**. Confirme que o segundo e-mail chega e que o
   login sem confirmação continua bloqueado.
4. Registre apenas data, provedor e resultado. Não copie tokens ou links para o
   repositório.

O código já registra o gate, usa resposta genérica e limita o reenvio.

## 2. Replay controlado do Mercado Pago sem nova cobrança

Reutilize o `payment_id` da compra aprovada que já gerou os documentos. Não
inicie outro checkout nem faça novo pagamento. Obtenha o `payment_id` no painel
do Mercado Pago e execute, em um terminal com as variáveis carregadas:

```powershell
$env:MERCADOPAGO_WEBHOOK_URL = "https://agente-de-candidaturas.onrender.com/webhooks/mercadopago"
$env:MERCADOPAGO_PAYMENT_ID = "<payment_id_do_checkout>"
python scripts/replay_mercadopago_webhook.py
```

O script envia duas vezes exatamente a mesma entrega assinada. Como a compra
existente já está paga, ambas podem indicar `idempotent: true`; confirme HTTP
de sucesso, `verified: true`, que não há segunda liberação/recibo e que o
documento continua acessível. Não informe o segredo na linha de comando: o
script lê `MERCADOPAGO_WEBHOOK_SECRET` do ambiente local seguro.

## 3. Rate limiting entre instâncias

O código agora usa um contador Lua atômico em Redis REST quando estas variáveis
existem: `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`. No Render,
crie-as como secrets e faça um deploy. Mantenha
`RATE_LIMIT_DISTRIBUTED_REQUIRED=false` no primeiro deploy; valide login,
cadastro e reenvio em uma instância. Em seguida altere para `true` e faça um
segundo deploy: uma indisponibilidade do Redis passa a falhar fechado com 503.

Não há chave do Redis no cliente nem no Git.

## 4. Proteção contra senhas vazadas sem upgrade

Não faça upgrade do Supabase só para esse controle. O backend consulta a API
gratuita HIBP Pwned Passwords usando k-anonimato: envia apenas os primeiros
cinco caracteres do SHA-1, nunca a senha nem o hash completo, e inclui padding.
Senhas encontradas são recusadas; indisponibilidade ou resposta inválida do
serviço retorna erro temporário seguro e não libera a senha. A checagem já é
aplicada no cadastro e na troca de senha por `PWNED_PASSWORD_CHECK`.

A opção nativa **Prevent use of leaked passwords** do Supabase Pro+ pode ficar
desligada: ela seria defesa em profundidade, não requisito para fechar o P0.
Os testes locais cobrem senha comprometida, falha de rede, status 503 e resposta
malformada. Após publicar a alteração fail-closed, confirme o deploy Live; não
é necessário criar conta real nem usar senha pessoal para essa verificação.

## 5. Backup, restauração e agendamento sem plano pago

Não use Render Cron nem faça upgrade Supabase Pro. O workflow
`.github/workflows/supabase-backup.yml` roda diariamente pelo GitHub Actions,
cria um dump PostgreSQL 17, valida com `pg_restore` e envia somente o arquivo
cifrado, com retenção de 30 dias. AES-256-GCM protege o dump; a chave de
conteúdo é envolvida com RSA-OAEP e a chave privada nunca vai para o GitHub.

O workflow já está habilitado. A secret `SUPABASE_DATABASE_URL` foi configurada
no GitHub Actions e validada no run manual #4 (`35486170058`), concluído com
sucesso e artifact cifrado de 374 KB. A correção que fixa os binários PostgreSQL
17 está no commit `eb94f91`.

Para manter a cópia recuperável com o mínimo de passos manuais:

1. Na configuração do repositório GitHub, em **Settings → Secrets and
   variables → Actions**, a secret `SUPABASE_DATABASE_URL` já está configurada; para rotacioná-la, atualize-a com a URL
   PostgreSQL usada no Render. Copie diretamente do Render; não a envie por
   chat, arquivo ou commit.
2. Copie `backups/database/backup-decryption-key.pem` para um gerenciador de
   senhas/arquivos seguro fora deste computador. Sem essa chave, os artefatos
   são irrecuperáveis. O arquivo nunca deve ser commitado.
3. No GitHub, abra **Actions → Daily encrypted Supabase backup → Run workflow**.
   Confirme que a execução terminou verde e que o artifact `supabase-backup-*`
   contém `.dump.enc` e o manifesto `.json`.

O agendamento diário já está definido para 05:17 no horário de Brasília. O
workflow não precisa de secret do GitHub se `SUPABASE_DATABASE_URL` estiver
ausente: ele apenas encerra com aviso, sem expor dados. A primeira execução foi verificada. A restauração integral ainda precisa ser verificada antes de marcar o P0.11 completo.

Para restaurar, baixe o artifact cifrado, descriptografe localmente com a chave
privada em um caminho novo e restaure para uma instância Supabase local/isolada,
nunca para produção. A rotina antiga `scripts/backup_supabase.py` também pode
ser executada manualmente; `--check` verifica `pg_dump`, `pg_restore` e a
conexão via `DATABASE_URL`.

**Execução registrada em 19/09/2026:** foi criado um dump real do PostgreSQL 17
de produção, com checksum validado. A restauração em PostgreSQL 17 descartável
recuperou as 11 tabelas públicas, as 11 políticas RLS e cerca de 527 linhas
estimadas. Para esse teste em PostgreSQL vanilla, `supabase_vault` e os dados
de `vault.secrets` foram excluídos; ainda é necessário validar a restauração
integral em um projeto Supabase compatível. O dump foi cifrado localmente e o
original em texto puro apagado. O workflow gratuito já agenda o upload cifrado
por 30 dias; naquela data, faltava configurar a secret, guardar a chave fora do computador, rodar o workflow (concluído em 20/09/2026) e confirmar a restauração integral Supabase-compatível.
