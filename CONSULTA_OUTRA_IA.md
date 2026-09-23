# Consulta técnica — Agente de Candidaturas (JobPilot)

## Objetivo

Validar com outra IA a arquitetura e o plano de publicação do projeto antes de ativar autenticação real, Supabase, RLS, Google OAuth/Gmail e hospedagem pública.

## Contexto do projeto

O projeto está em `C:\agente_curriculos` e foi enviado para:

`https://github.com/usoparakotas21-boop/agente-de-candidaturas`

Branch atual: `master`  
Commit inicial enviado: `e43db06`

É uma aplicação FastAPI para:

- captar vagas por texto, print, PDF e Gmail;
- avaliar qualidade, fraude e confiança da vaga;
- classificar oportunidades como `AUTOMATICA`, `REVISAR` ou `DESCARTAR`;
- gerar currículo e carta personalizados em DOCX;
- manter candidaturas e histórico de status.

## Estado atual confirmado

- API FastAPI funcional.
- Dashboard HTML/JavaScript sem framework.
- SQLite local em `data/agente.db`.
- Suporte de conexão PostgreSQL via `DATABASE_URL`.
- Modelos SQLAlchemy para candidatos, vagas, candidaturas, eventos e fila.
- Fila de decisão persistente com endpoints em `/queue`.
- Extrator de vagas corrigido e validado.
- OAuth do Gmail implementado em `app/gmail_integration.py`.
- Monitor de Gmail implementado em `app/gmail_monitor.py`.
- Criptografia de refresh token prevista por `TOKEN_ENCRYPTION_KEY`.
- RLS parcial em script `scripts/migrate_0_23.py`, atualmente focado em `queue_items`.
- Autenticação ativa ainda está em modo local simplificado em `app/auth.py`.
- `AUTH_REQUIRED` ainda está fixado como `False` no arquivo ativo.
- O monitor do Gmail atualmente inicia junto com o processo web.
- Não existe ainda `Dockerfile`, `render.yaml` ou configuração de deploy.
- O projeto foi inicializado no Git, mas ainda não há pipeline de CI/CD.

## Testes

A suíte completa foi executada com sucesso:

```text
Ran 38 tests ... OK
```

Os testes usam SQLite temporário e não validam ainda o isolamento real entre dois usuários Supabase.

## Arquivos principais

- `app/main.py`: aplicação FastAPI e rotas principais.
- `app/auth.py`: autenticação atualmente simplificada.
- `app/auth_backup.py`: versão anterior com integração HTTP ao Supabase Auth e middleware.
- `app/database.py`: seleção entre SQLite local e PostgreSQL por `DATABASE_URL`.
- `app/models.py`: modelos SQLAlchemy.
- `app/gmail_integration.py`: OAuth e conexão individual do Gmail.
- `app/gmail_monitor.py`: sincronização e monitoramento de e-mails.
- `scripts/migrate_0_23.py`: migração da fila e RLS parcial.
- `app/static/dashboard.html`: frontend do dashboard.

## Variáveis de produção previstas

Nunca incluir valores no Git ou nesta consulta. Apenas os nomes:

```text
DATABASE_URL
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
AUTH_REQUIRED=true
COOKIE_SECURE=true
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
TOKEN_ENCRYPTION_KEY
BASE_URL
```

## Arquitetura pretendida

```text
Usuário
  |
  v
Render Web Service (FastAPI + Dashboard)
  |-------- Supabase Auth
  |-------- Supabase PostgreSQL
  |-------- Google OAuth / Gmail readonly
  |
  v
Render Background Worker (monitor Gmail)
```

## Pontos que precisam de revisão

1. A versão ativa de `app/auth.py` deve ser substituída por uma autenticação real baseada em Supabase Auth?
2. O middleware de autenticação deve proteger todas as rotas, mantendo públicas somente `/`, `/dashboard`, login, callback OAuth e documentação?
3. Quais políticas RLS devem existir para `candidates`, `jobs`, `applications`, `application_events`, `queue_items` e `email_integrations`?
4. É melhor manter `owner_id` como texto contendo o UUID do Supabase ou alterar os tipos para UUID no PostgreSQL?
5. O worker do Gmail deve ser um processo separado no Render? Como evitar que o monitor seja iniciado duas vezes?
6. Como tratar migração dos dados atuais do SQLite para o Supabase sem enviar dados pessoais ao GitHub?
7. O callback do Google deve usar o domínio final do Render e também um callback local de desenvolvimento?
8. Quais testes de segurança mínimos devem ser executados antes de abrir o serviço na internet?
9. O projeto deve usar Render Web Service + Background Worker, ou outra arquitetura seria mais adequada para este volume?
10. Quais endpoints devem permanecer públicos e quais devem exigir cookie de sessão válido?

## Restrições importantes

- Não publicar `.env`, tokens, client secrets, banco SQLite, currículos ou documentos gerados.
- Não usar a chave service role do Supabase no frontend.
- O escopo Gmail deve permanecer somente leitura (`gmail.readonly`).
- Não ativar candidatura automática antes de revisar segurança, consentimento e regras das plataformas.
- A aplicação precisa funcionar no celular e no computador.

## Pergunta principal para a outra IA

Com base nesse estado, qual é a sequência técnica mais segura para:

1. ativar Supabase Auth;
2. implementar e testar RLS multiusuário;
3. configurar Google OAuth para Gmail;
4. separar o worker do processo web;
5. migrar dados locais com segurança;
6. publicar no Render com HTTPS e segredos protegidos?

Peça respostas específicas para FastAPI, SQLAlchemy, Supabase PostgreSQL, Google OAuth e Render. Não forneça nem solicite segredos reais.
