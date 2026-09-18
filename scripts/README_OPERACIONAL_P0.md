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

## 2. Checkout e replay controlado do Mercado Pago

Faça um único checkout de teste no Mercado Pago usando uma conta/meio de
pagamento sob seu controle. Depois de o pagamento aparecer como aprovado,
obtenha o `payment_id` no painel do Mercado Pago e execute, em um terminal com
as variáveis carregadas:

```powershell
$env:MERCADOPAGO_WEBHOOK_URL = "https://agente-de-candidaturas.onrender.com/webhooks/mercadopago"
$env:MERCADOPAGO_PAYMENT_ID = "<payment_id_do_checkout>"
python scripts/replay_mercadopago_webhook.py
```

O script envia duas vezes exatamente a mesma entrega assinada. A primeira deve
confirmar a compra e a segunda deve indicar `idempotent: true` (ou a mesma
transição já paga, sem liberar novamente). Não informe o segredo na linha de
comando: o script lê `MERCADOPAGO_WEBHOOK_SECRET` do ambiente local seguro.

## 3. Rate limiting entre instâncias

O código agora usa um contador Lua atômico em Redis REST quando estas variáveis
existem: `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`. No Render,
crie-as como secrets e faça um deploy. Mantenha
`RATE_LIMIT_DISTRIBUTED_REQUIRED=false` no primeiro deploy; valide login,
cadastro e reenvio em uma instância. Em seguida altere para `true` e faça um
segundo deploy: uma indisponibilidade do Redis passa a falhar fechado com 503.

Não há chave do Redis no cliente nem no Git.

## 4. Proteção nativa contra senhas vazadas

No Supabase, o recurso **Prevent use of leaked passwords** exige o plano
compatível. Faça o upgrade somente se essa proteção nativa for necessária para
o aceite do P0; depois ative a opção em Authentication → Protection e repita um
cadastro com uma senha de teste conhecida como comprometida. O aplicativo já
mantém a checagem k-anonimizada como camada independente.

## 5. Backup, restauração e agendamento

Instale os PostgreSQL client tools no ambiente que executará o backup e
configure `DATABASE_URL` apenas como secret. O script não coloca a URL na linha
de comando:

```powershell
python scripts/backup_supabase.py --check
python scripts/backup_supabase.py
```

Para validar restauração, crie um banco/projeto descartável separado, defina a
URL em `BACKUP_TEST_DATABASE_URL` e execute explicitamente:

```powershell
python scripts/backup_supabase.py --restore-to $env:BACKUP_TEST_DATABASE_URL
```

O dump é customizado, verificado com `pg_restore`, recebe SHA-256 e manifesto.
Agende o comando diário no Render Cron (se o plano permitir) ou no scheduler
privado que guarda `DATABASE_URL`; mantenha pelo menos uma cópia fora do banco
de produção e registre o resultado da restauração.
