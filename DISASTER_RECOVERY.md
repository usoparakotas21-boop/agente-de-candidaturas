# Runbook de backup e recuperação

Este runbook descreve o mínimo necessário para recuperar o serviço sem expor
segredos. Os valores reais ficam apenas no Supabase, Render e provedores OAuth.

## Antes de aceitar pagamentos

1. No projeto Supabase de produção, confirmar que os backups automáticos estão
   ativos, qual é a retenção e se o plano permite restauração para um projeto
   isolado. Ativar PITR quando estiver disponível no plano.
2. Registrar a data do último backup e o responsável pela verificação no
   controle operacional privado. Não colocar tokens, URLs completas de banco ou
   dumps neste repositório.
3. Fazer um teste de restauração em projeto separado. Aplicar as migrações,
   confirmar RLS nas 11 tabelas e executar a suíte local antes de considerar a
   restauração válida.
4. Confirmar que o UptimeRobot monitora `/health` e que o alerta chega ao canal
   operacional definido.

No plano Free, a rotina externa já está preparada em
`scripts/backup_supabase.py`. Ela usa `DATABASE_URL` somente pelo ambiente do
processo filho (`PGDATABASE`), produz um dump customizado, valida o arquivo com
`pg_restore --list` e grava checksum SHA-256 e manifesto sem segredos em
`backups/database/` (diretório ignorado pelo Git).

Antes de agendar, instale os PostgreSQL client tools e valide os pré-requisitos:

```powershell
uv run python scripts/backup_supabase.py --check
```

Para criar um backup verificado:

```powershell
uv run python scripts/backup_supabase.py
```

O script não apaga backups antigos automaticamente. A retenção deve ser
configurada no destino privado depois que o primeiro teste de restauração for
aprovado.

## Teste de restauração

O teste deve usar uma cópia isolada, nunca o banco de produção. Depois de
restaurar:

- conferir que a aplicação inicia com `DATABASE_URL` usando TLS;
- executar `python -m unittest discover -s tests -p "test_*.py"`;
- executar a consulta de cobertura RLS de `scripts/migrate_rls.py` em modo de
  leitura;
- testar login, MFA, leitura de vaga, download condicionado a pagamento e
  logout;
- apagar o projeto temporário e registrar o resultado sem dados pessoais.

## Revogação emergencial

Se houver suspeita de exposição, executar nesta ordem e registrar somente o
horário e o tipo de credencial afetada:

1. Pausar o serviço ou o checkout no Render, se a exposição puder liberar
   pagamentos ou documentos.
2. Rotacionar no Render `DATABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
   `TOKEN_ENCRYPTION_KEY`, `OAUTH_STATE_SECRET`, `GEMINI_API_KEY` e os segredos
   de webhook afetados. Nunca substituir valores por texto neste repositório.
3. Revogar sessões e refresh tokens no Supabase Auth quando o incidente
   envolver autenticação.
4. Revogar tokens do Gmail/Outlook no respectivo provedor e remover as
   conexões armazenadas, se a chave de criptografia ou o banco tiverem sido
   expostos.
5. Revogar e recriar credenciais OAuth do Google/Microsoft e credenciais de
   pagamento no painel do provedor quando aplicável.
6. Fazer novo deploy, verificar `/health`, revisar logs por acesso anômalo e
   executar a suíte completa antes de reabrir o serviço.

## Evidência mínima

Manter fora do Git um registro com data, operador, backup/restauração testado,
credenciais rotacionadas e resultado dos testes. O status público do projeto
deve registrar apenas se a etapa foi confirmada, sem incluir valores sensíveis.
