# Candidatura Certa — fechamento das pendências, 26/10/2026

Branch: `audit/seis-frentes-2026-10-21`. Esta rodada continua `56c9faf` e não substitui o histórico de 16/10 e 21/10. O código foi preservado nas interfaces existentes e atualizado na mesma branch isolada. Produção foi apenas inspecionada; não houve merge, deploy, alteração de produção, pagamentos ou envio de e-mails. Políticas e privilégios foram alterados somente no projeto Supabase de desenvolvimento.

## Correções concluídas no código

### OAuth Gmail e Outlook

`oauth_state_nonces` registra somente hash do nonce, provedor, titular e expiração. A assinatura, o titular e a validade do state são verificados antes do DELETE atômico que consome o nonce. A transação é confirmada antes da chamada ao provedor: replay, duas requisições simultâneas e reinício de conexão não reutilizam o state. Falha do banco bloqueia emissão/callback com 503, sem fallback em memória. A tabela é RLS/server-only e suas permissões são tratadas no bootstrap e em `scripts/migrate_rls.py`.

Os nomes `_create_state`, `_state`, `_validate_state` e as rotas existentes foram mantidos. Inícios de autorização anteriores à implantação não terão registro no ledger: será necessário iniciar uma nova conexão. Se o provedor falhar após o consumo, o usuário também deverá reiniciar o fluxo, evitando repetição de autorização.

### Isolamento e identificadores legados

Adicionada política restritiva que exige que todos os identificadores preenchidos pertençam ao mesmo sujeito, sem substituir as políticas permissivas existentes. Um trigger impede que clientes alterem ou apaguem `owner_id`/`user_id`; reconciliação fica reservada ao backend. Perfil comum continua editável. O backend mantém acesso para manutenção. Administradores declarados por `public.is_admin()` preservam a leitura/escrita de conteúdo prevista na política existente, mas o trigger também bloqueia sua reassociação direta por papel cliente.

Consulta atual somente de contagens: candidates = 3 registros owner-only, candidatos = 0, email_integrations = 3 registros owner-only. **Zero conflitos, zero registros sem ambos os identificadores e zero registros precisando preencher owner_id a partir de user_id.** Nenhum dado foi reatribuído por suposição ou por e-mail. As linhas owner-only continuam permitidas pela regra nova.

### Administração, cortesias e assinatura

`app/admin_identity.py` centraliza a autoridade administrativa de backend: identidade confirmada, claim em `app_metadata` ou allowlist administrativa existente. `user_metadata` é ignorado e a string `false` não concede autoridade. A conta histórica de cortesia mantém seus benefícios, porém deixa de retornar `is_admin=true` nos benefícios sem ser administradora nas rotas. O guard de MFA continua aplicado às ações administrativas.

O backend preserva sua allowlist histórica; a função RLS `public.is_admin()` continua baseada exclusivamente em app_metadata. Não se ampliaram permissões SQL para reproduzir uma allowlist de e-mails no banco. A diferença de compatibilidade está explícita e a lista de backend deve ser retirada apenas após provisionar claims administrativos equivalentes e validar o acesso da equipe.

Assinatura, cota, verificação de acesso e métricas passam a usar a mesma validade: **access_until futuro e status permitido**. Status suspenso, substituído ou rejeitado não dá acesso mesmo com prazo futuro. Autorização no provedor ou a palavra cortesia, isoladamente, não tornam uma assinatura sem prazo ativa. Uma linha mais nova pendente/expirada ou substituída deixa de ocultar um período ainda válido do mesmo titular. Consulta agregada atual encontrou uma assinatura authorized com prazo e duas pending sem prazo; não foi removido prazo nem alterado status de ninguém.

Ações administrativas de cortesia, suspensão e revogação agora identificam o titular pelo e-mail confirmado em `auth.users`, usando consulta parametrizada, e alteram somente assinaturas com o `owner_id` encontrado. E-mail editável de perfil ou pagador deixa de selecionar assinaturas de outras contas. E-mail sem conta confirmada retorna 404; duplicidade retorna 409; provedor indisponível ou sem permissão de leitura retorna 503. A concessão antecipada a e-mail ainda não cadastrado deixa de criar um UUID fictício. As rotas de consulta de assinatura e download de e-book também usam o titular autenticado. É necessário verificar em staging que o papel SQL do backend possui leitura autorizada de `auth.users` antes de implantar.

### SSRF dos scrapers

O transporte já validado do importador foi centralizado em `utils/public_http.py` e ganhou versão assíncrona. `criar_cliente_protegido` agora usa esse transporte em `SafeHttpClient`, cobrindo os scrapers que usam esse caminho. Cada destino e redirecionamento conecta ao IP público validado, com Host, SNI e verificação TLS do domínio original. DNS assíncrono não bloqueia o event loop. Proxy de ambiente é ignorado; proxy explicitamente configurado é encaminhado pelo transporte, com destino já fixado em IP. TLS não é reutilizado entre nomes que compartilhem endereço.

Clientes HTTP externos injetados explicitamente, requisições diretas fora desse cliente e configurações de saída de rede permanecem responsabilidades dos respectivos consumidores. Isso não é bloqueio de egress de toda a infraestrutura. Limites de tamanho preexistentes do cliente genérico continuam sendo verificados depois da leitura da resposta; esta rodada não implementa streaming universal contra todas as formas de bomba de descompressão.

### Dependências e imagem

A nova consulta encontrou três avisos em pypdf 6.21.1. Atualizado para **6.21.2** e repetida a auditoria com resolução de dependências: resultado final nos anexos. A ausência de avisos é temporal e não cobre npm, imagem base ou pacotes do sistema.

Dockerfile passa a executar como usuário `app`, com diretório de trabalho gravável. `.dockerignore` exclui .env, chaves, bancos locais, currículos, backups, caches e dependências locais. O CMD existente foi preservado. A CI também constrói a imagem e verifica usuário sem root, flags de segurança, schema e geração/leitura de DOCX/PDF com dados sintéticos.

## Railway: conferência atual pelo navegador

O conector continuou UNAUTHORIZED, mas o usuário abriu uma sessão no navegador e foi possível concluir as verificações abaixo na interface, sem alterar configurações:

- Projeto truthful-vision; serviço web; ambiente production; uma réplica em sfo; fonte `usoparakotas21-boop/agente-de-candidaturas`, branch `master`.
- **Wait for CI desligado.** Permanece uma alteração operacional a aprovar/aplicar; não foi ligado automaticamente.
- Implantação ativa `e9d87e16-5ad9-494a-8506-5c9680ec9800`, mensagem “fix: report catalog and workflow vacancy counts”. As correções da branch de auditoria não são a implantação ativa.
- Configuração de build indica Dockerfile detectado; start command Uvicorn `app.main:app`; healthcheck `/health`. A configuração exibida não prova quais camadas foram usadas no build antigo.
- Conferidos individualmente apenas valores não secretos: AUTH_REQUIRED=true, COOKIE_SECURE=true, MFA_LOGIN_ENFORCE=true, PWNED_PASSWORD_CHECK=true, RATE_LIMIT_DISTRIBUTED_REQUIRED=true. Os valores foram ocultados novamente.
- Confirmada presença de UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN pelo filtro de nomes. Presença não prova conectividade, valor válido ou robustez. Segredos não foram revelados/copiados, nem foi realizada rotação.
- Amostra limitada do painel de logs “Last 15 min”: nove ocorrências de timestamp visíveis, zero correspondências de e-mail, zero menções ERROR/Traceback/Exception e zero padrões de credencial detectados pela expressão utilizada. São contagens da área visível, **não nove eventos certificados nem uma auditoria de todo o histórico**. Nenhum log bruto foi exportado. Retenção e controles de acesso não foram certificados.
- GET público `/health` retornou 200 e `/` retornou 200; HSTS e CSP presentes. Na página pública, `Cache-Control: private, no-store, max-age=0`, `nosniff` e `X-Frame-Options: DENY`. `/login` retornou 401; o formulário real está na landing page, não nessa rota. Não houve login de usuário real para medir cookies autenticados. Evidência em `public-headers.json`.

## Supabase: estado atual e limite da execução

As consultas continuam mostrando 64 grants TRUNCATE para anon/authenticated, correspondentes a 32 tabelas por papel, e as políticas legadas de identidade. A proteção da branch ainda precisa ser aplicada no ambiente adequado. Advisor de 26/10 confirma proteção contra senhas vazadas desativada. O flag PWNED_PASSWORD_CHECK do backend **não equivale** à proteção nativa do Auth.

Não existe branch de desenvolvimento Supabase; a tentativa de criá-la retornou que Branching requer plano Pro. A organização foi verificada como **Free**, e a proteção nativa contra senhas vazadas também exige Pro ou superior. O projeto separado `agente-candidaturas-dev`, antes INACTIVE, foi reativado e passou a ACTIVE_HEALTHY. Não foi criado recurso pago.

O desenvolvimento tinha nove tabelas públicas, incluindo `email_integrations` e `processed_email_messages` com RLS desativada. Contagens exatas identificaram uma candidatura, uma integração, 25 mensagens processadas e uma conta Auth; todos os titulares correspondiam a essa conta. Esses registros não foram excluídos nem reatribuídos. As políticas de titular foram aplicadas às duas tabelas junto com a proteção de identidade, revogação de privilégios e ledger OAuth server-only. A migração foi registrada no desenvolvimento como `20261026202926`, `auditoria_staging_isolamento_oauth_20261026`; o SQL executado está em `staging-sql-evidencia.txt` para revisão, e não é uma instrução para aplicar em produção.

Após a alteração, as contagens permaneceram iguais; nenhuma das dez tabelas públicas do desenvolvimento estava sem RLS, não havia grants TRUNCATE para anon/authenticated e o ledger não podia ser lido pelos clientes. Teste com papel authenticated confirmou que o titular enxergava sua integração e suas 25 mensagens, outro sujeito via zero linhas e tentativas de reatribuir titular foram bloqueadas. O advisor deixou de apontar as duas tabelas sem RLS; permaneceu o alerta de senha vazada, indisponível no plano Free.

O desenvolvimento é um schema antigo com nove tabelas anteriores à criação do ledger, não uma cópia completa das 35 tabelas de produção. Portanto, a proteção financeira nas cinco tabelas e a execução integral de `scripts/migrate_rls.py` foram validadas em PostgreSQL 17 descartável na CI, mas não puderam ser aplicadas integralmente a esse desenvolvimento incompleto. Não foi implantada uma aplicação de staging nem configuradas credenciais sandbox dos provedores.

## Testes e homologação

- Local: 566 testes Python aprovados, 35 testes PostgreSQL ignorados por ausência de servidor/Docker local, 96 subtests. JavaScript: 30 aprovados. `pip check` aprovado.
- Novos testes: replay/concorrência/expiração/indisponibilidade do nonce, redirecionamento privado e DNS/TLS no cliente assíncrono, autoridade administrativa, isolamento de identificadores, tabela de nonce server-only e execução idempotente do script RLS em schema descartável.
- O workflow de CI executou os 35 testes PostgreSQL, o build e o smoke da imagem. A [execução 40395770158](https://github.com/usoparakotas21-boop/agente-de-candidaturas/actions/runs/40395770158), commit `ac77d54c7a9952bd1b0ebcacfc3437f3bd312e9e`, passou com **601 testes Python, sem skips, 96 subtests e 30 testes JavaScript**, além de `pip check`, `pip-audit` e Docker smoke. Evidência em `ci-tests.txt`.
- Testes de pagamentos, OAuth e documentos existentes passaram com mocks/fixtures; o novo smoke usa DOCX/PDF reais gerados localmente. Não houve transação com Mercado Pago nem consentimento real Google/Microsoft em staging. A homologação real depende de ambiente e contas sandbox, sem uso de credenciais de produção para testes.

## Passos operacionais ainda necessários

1. Complementar o schema de staging ou disponibilizar um banco descartável com schema equivalente ao atual, sem copiar registros/tokens reais. Configurar segredos, criptografia, callbacks e credenciais sandbox específicos do staging.
2. Aplicar a branch nesse ambiente e executar `python scripts/migrate_rls.py` apenas com a conexão de staging configurada com segurança. Validar login, MFA, autorização Google/Microsoft, pagamentos sandbox e geração de documentos; iniciar um novo OAuth após a mudança do ledger. Confirmar a permissão de leitura do backend em `auth.users` para ações administrativas.
3. A proteção nativa contra senhas vazadas está disponível no plano Pro ou superior, enquanto a organização atual é Free. A aplicação possui verificação própria ativa, que não cobre necessariamente acesso direto ao Supabase Auth. Decidir posteriormente sobre plano/configuração e validar os fluxos. [Documentação do provedor](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
4. Conferir backup/rollback, revisar a branch e aprovar o rollout. Ligar Wait for CI na Railway e realizar merge/deploy somente na janela acordada. Revalidar grants/políticas/flags, cookies autenticados e logs após a implantação.

Não marcar os itens acima como realizados apenas porque os testes automatizados passaram. A entrega contém o código integral atualizado, relatório, patch e evidências, mantendo o trabalho pronto para conferência e aplicação controlada.

Referências: [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [HTTPX SNI](https://www.python-httpx.org/advanced/extensions/), [changelog Supabase](https://supabase.com/changelog). O changelog foi novamente recuperado em 26/10 e não se usou a mudança de exposição de novas tabelas como substituto para corrigir grants existentes.
