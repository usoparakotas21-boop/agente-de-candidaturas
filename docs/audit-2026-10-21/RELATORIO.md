# Candidatura Certa — retomada das seis frentes, 21/10/2026

## Resultado para conferência

Correções na branch `audit/seis-frentes-2026-10-21`, continuando `audit/dry-owasp-2026-10-16` (`ca06b1c`). O fetch confirmou `origin/master` em `aca2b38`; as correções anteriores ainda não estão nessa base. As interfaces existentes foram preservadas. Nenhum deploy, merge, pagamento, envio de mensagem ou alteração de banco/configuração de produção foi realizado.

A revisão de código e os testes locais foram executados. Supabase foi consultado somente em catálogos e advisors, sem ler registros de usuários. A frente Railway está parcialmente bloqueada por credenciais OAuth expiradas nas duas conexões; configurações e logs antigos não foram tratados como evidência atual. Portanto esta entrega não significa que todas as verificações externas estejam concluídas nem que produção esteja corrigida.

## 1. DRY e arquitetura

- Localizada a mesma consulta de assinatura em `main._get_user_plan_and_entitlement` e `plan_limits._effective_plan`.
- Criado `app/billing_access.py`: `subscription_for_owner` centraliza seleção por titular autenticado; `subscription_has_access` centraliza validade. Funções públicas e formatos de retorno existentes permanecem.
- Corrigida divergência: antes a cota aceitava assinatura pausada/cancelada sem validade, enquanto o acesso principal recusava. Teste matricial cobre cinco status, prazo futuro, expirado e ausente (15 cenários), além de isolamento por proprietário e colisão de e-mail.
- Mantida a compatibilidade existente para `active`/`authorized` sem prazo e cortesia explícita sem prazo. Isso precisa de decisão de negócio/reconciliação antes de exigir universalmente período pago confirmado. O helper mais estrito `_subscription_is_entitled` permanece com sua finalidade original.
- `app/main.py` continua extenso e `app/app-main.py` continua duplicado. A refatoração foi limitada às regras comprovadamente repetidas; não houve remoção de arquivo legado sem confirmação de consumidores. Métricas administrativas e allowlist administrativa ainda usam regras próprias, que devem ser alinhadas em outra revisão com critérios de negócio explícitos.

## 2. OWASP, ponto a ponto

| Item | Verificação e resultado |
|---|---|
| Autenticação | Mantida validação do usuário pelo Supabase, refresh e MFA. Novo bloqueio impede `AUTH_REQUIRED=false` de desligar login quando há marcador Railway/produção. Cinco testes de processo isolado cobrem os marcadores e preservação do modo local. |
| Autorização | Retestados proprietário financeiro, colisão de e-mail, bypass `DEBUG`, e-mail confirmado e MFA administrativo. Correções da auditoria anterior continuam na branch. Não foi executado ataque contra usuários reais. |
| SQL Injection | Consultas de negócio revisadas usam SQLAlchemy/binds. DDL financeiro usa tupla fixa; o novo loop de revogação usa `format('%I', ...)` para identificadores vindos do catálogo. Nenhuma SQL Injection confirmada nesses caminhos; não é prova de cobertura integral de todo SQL do sistema. |
| XSS | Mantida correção DOM em `applications-enhance.js`; teste executável com payload malicioso passou. Revisados exemplos de sinks em dashboard, simulador, feedback e LinkedIn: escape de texto/HTML ou sanitização explícita existem nos caminhos inspecionados. A existência desses escapes não certifica todos os templates/sinks. |
| SSRF | Corrigida janela entre DNS e conexão de `fetch_job_posting`: transporte conecta ao IP literal validado e preserva Host/SNI e validação de certificado do domínio. Desabilitados proxy de ambiente e reuso TLS entre nomes que compartilhem IP. Redirects são revalidados; mantidos limite de bytes e quantidade de redirecionamentos. Erros de porta/URL e resposta DNS vazia viram erros controlados. Testes offline exercitam HTTPX→httpcore, conexão, TLS, rebinding, redirect privado, IPs internos e compartilhamento de IP. |
| CSRF | Retestada proteção Origin/Fetch Metadata da branch anterior e exceções dos webhooks assinados/extensão bearer. Requisições sem esses cabeçalhos continuam compatíveis; não há token CSRF universal. OAuth state de Gmail/Outlook tem assinatura, titular e expiração, mas não há consumo persistente de nonce de uso único. |
| Webhooks | Revisado HMAC com comparação constante, request-id, janela de cinco minutos, consulta de confirmação ao provedor e ledger idempotente. Testes existentes passaram. Não foram enviados webhooks/pagamentos a produção; formato real de timestamp/ID ainda exige sandbox do provedor. |
| Dependências | Antes: 262 avisos em 13 pins. Atualizados os 13 pacotes e os pins necessários para compatibilidade, incluindo FastAPI/Starlette, aiohttp e bibliotecas de documentos. Depois: zero avisos conhecidos nos pins e nos 98 pacotes resolvidos por `pip-audit -r requirements.txt`. `pip check` aprovado. O resultado não cobre npm, binários/imagem base, pacotes do sistema nem futuras vulnerabilidades. |

O transporte SSRF novo cobre o importador `app/job_source_fetcher.py`; scrapers/cliente HTTP genérico não passaram a usar automaticamente essa proteção. Bibliotecas maiores foram atualizadas e a regressão passou, mas integrações reais de OAuth, pagamentos e geração de documentos ainda merecem homologação antes de deploy.

## 3. Supabase: isolamento e RLS

Consulta atual confirmou **35 tabelas públicas, 35 com RLS habilitada**. Foram inspecionadas as políticas públicas, grants, views e funções privilegiadas. Não há view pública no catálogo consultado. A função `is_admin()` usa `app_metadata`, invoker e search_path explícito. A única função pública SECURITY DEFINER retornada é event trigger `rls_auto_enable`, com EXECUTE restrito a postgres/service_role e search_path pg_catalog.

### Achados atuais

1. **Crítico: TRUNCATE concedido a anon/authenticated em 32 tabelas.** RLS não filtra TRUNCATE; políticas `false` não compensam esse grant. Exploração via API depende dos serviços/RPC expostos, que não foram invadidos nem testados destrutivamente. REFERENCES/TRIGGER também estavam concedidos nas mesmas 32 tabelas.
2. **Crítico condicionado à exposição: escrita financeira permanece em produção.** `billing_subscriptions`, `consultation_credits`, `document_export_purchases` têm grants de INSERT/UPDATE/DELETE e políticas ALL por owner_id. Um usuário pode ser dono da linha e ainda assim não poder definir seu pagamento/plano/saldo. A proteção da branch anterior ainda não foi aplicada remotamente. As outras duas tabelas financeiras têm política false, porém também tinham TRUNCATE.
3. `candidates`, `candidatos` e `email_integrations` permitem `user_id OR owner_id OR is_admin`. Esse modelo pode permitir reassociação de um identificador mantendo o outro. Substituí-lo sem reconciliar contas legadas pode bloquear usuários. Permanece aberto; não afirmamos isolamento completo dessas tabelas.
4. Advisor confirmou proteção contra senhas vazadas desativada. Nenhuma configuração Auth foi alterada. [Remediação](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
5. Advisor informa RLS sem política em `billing_webhook_events`, compatível com ledger exclusivo de servidor. Isso não é prova de vazamento. [Referência](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).
6. Não há políticas Storage retornadas. Não foram consultados buckets/conteúdo; isso não permite concluir que não existem buckets públicos ou arquivos expostos.

### Correção preparada

`protect_client_table_privileges` revoga TRUNCATE/REFERENCES/TRIGGER e, no PostgreSQL 17+, MAINTAIN de PUBLIC/anon/authenticated em todas as tabelas públicas existentes. A proteção financeira compartilhada chama essa função, mantendo os pontos de entrada de bootstrap e `scripts/migrate_rls.py`. As políticas restritivas financeiras anteriores permanecem. Nenhum SELECT/INSERT/UPDATE/DELETE não financeiro foi revogado por essa nova função. Novas tabelas/grants introduzidos após a execução precisam da mesma revisão.

Teste PostgreSQL foi estendido para conferir privilégios em cada tabela financeira e em uma tabela não financeira, idempotência, leitura do titular, invisibilidade de outra linha e escrita do backend. Usa exclusivamente banco efêmero local `audit_*`, com rollback. **Não executar o teste ou a migração contra produção durante esta conferência.**

Changelog Supabase foi recuperado e revisado. Atenção operacional: a mudança anunciada de exposição automática das novas tabelas pela Data API não substitui a revisão dos grants existentes. Também há atualização de segurança PostgreSQL publicada; o conector reportou versão 17.6.1.166. Upgrade/compatibilidade devem ser tratados pelo provedor em manutenção separada.

## 4. Railway: configuração, cookies, segredos e logs

- **Bloqueio atual:** ambas as conexões retornaram `UNAUTHORIZED / oauth_token_invalid_grant`, exigindo reautenticação. Não houve repetição de tentativa com comandos de alteração nem uso de credenciais alternativas para contornar o acesso.
- **Código:** cookies permanecem HttpOnly/SameSite; Secure passa a ser obrigatório quando o processo identifica Railway/produção. CSP, HSTS e proteção de origem continuam existentes. Testes de autenticação e cabeçalhos passaram.
- **Segredos no código:** varredura de padrões de alta confiança em 131 arquivos textuais versionados de app/utils/scripts/.github não encontrou correspondências de chave privada, token GitHub ou chave secreta Supabase. Não cobre histórico Git, todos os formatos ou binários; nenhum valor encontrado/variável secreta foi impresso.
- **Pendente por acesso:** fonte/SHA implantado, proteção das verificações antes de deploy, valores efetivos de flags, robustez/rotação de segredos, cookies observados em sessão real, logs recentes, redação, retenção, acesso e backups. Os nomes/valores e observações de 16/10 não foram reconfirmados hoje.

## 5. Testes e regressão

- Python local, após todas as mudanças: **539 passed, 8 skipped, 87 subtests**. Os oito skips são PostgreSQL, porque PostgreSQL/Docker não estão instalados localmente. Warnings são depreciações FastAPI/TestClient/HTTPX e reportlab.
- JavaScript: **30 passed**, zero skips/falhas.
- Dependências: `pip check` aprovado; pins sem avisos; auditoria com resolução de dependências **98 pacotes, zero avisos conhecidos**.
- `git diff --check` aprovado.
- Workflow isolado PostgreSQL 17 mantido e ampliado com `pip-audit`. [CI 39694541264](https://github.com/usoparakotas21-boop/agente-de-candidaturas/actions/runs/39694541264), commit `219fe380bab18c26356eb4a1714c3b71f9f66bac`, **aprovada: 547 testes Python, zero skips, 87 subtests e 30 testes JavaScript**. Os oito testes PostgreSQL reais passaram. `pip check` e `pip-audit` também passaram em Linux. Nenhum segredo de produção é utilizado pelo workflow de regressão.

Evidências: `python-tests.txt`, `javascript-tests.txt`, `pip-check.txt`, `dependencies-before.json`, `dependencies-after.json`, `dependencies-resolved.json`, `dependency-audit.txt`, `secret-pattern-scan.json`. Contagens de avisos refletem a base consultada em 21/10; não são contagem de explorações comprovadas.

## 6. Correções e conferência final

Branch isolada inclui as correções anteriores e esta rodada: centralização de assinatura, SSRF por conexão ao IP validado, revogação de privilégios que RLS não restringe, flags de produção obrigatórios, atualizações de dependências e testes correspondentes. Arquivos completos e diff serão disponibilizados junto ao relatório.

[Branch publicada para revisão](https://github.com/usoparakotas21-boop/agente-de-candidaturas/tree/audit/seis-frentes-2026-10-21). A criação de PR em rascunho pelo conector foi recusada com HTTP 403 `Resource not accessible by integration`; nenhum PR foi criado. Isso não impediu a publicação da branch e a execução da CI por push. O commit posterior de documentação não muda o código validado em `219fe38`.

Antes de eventual implantação: revisar as mudanças, reconciliar identificadores legados, testar a migração em staging, homologar integrações/documentos e completar a auditoria Railway após reautenticação. A implantação não faz parte desta execução. Permanecem explicitamente abertos os pontos externos acima, OAuth nonce único, alinhamento administrativo, legado de assinaturas sem prazo e cobertura dos demais clientes HTTP.

## Referências técnicas verificadas

- [Supabase RLS e grants](https://supabase.com/docs/guides/database/postgres/row-level-security).
- [Changelog Supabase](https://supabase.com/changelog).
- [Mudança dos grants de novas tabelas](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically).
- [Atualização PostgreSQL 15.19/17.11](https://supabase.com/changelog/postgres-15-19-17-11-breaking-changes).
- [HTTPX: sni_hostname, conexão a IP e identidade TLS](https://www.python-httpx.org/advanced/extensions/).
- [Starlette: notas de versão](https://www.starlette.io/release-notes/).
- [FastAPI: notas de versão](https://fastapi.tiangolo.com/release-notes/).
