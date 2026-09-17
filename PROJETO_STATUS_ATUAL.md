# Agente de Candidaturas — status atual

**Atualizado em:** 17/09/2026  
**Versão declarada da API:** 0.24.0  
**Commit publicado:** `4bcf86a` — `Audit security checklist and reprioritize backlog`
**Produção:** `https://agente-de-candidaturas.onrender.com`  
**Repositório:** `usoparakotas21-boop/agente-de-candidaturas`  
**Diretório local:** `C:\agente_curriculos`

Este arquivo é o retrato operacional atual. O arquivo `PROJETO_STATUS.md` continua como histórico detalhado; quando houver conflito, este documento representa o estado mais recente.

## O que existe de fato

### Aplicação e acesso

- API FastAPI com dashboard responsivo para celular e computador.
- Deploy público no Render, com health check em `/health`.
- Login, cadastro, logout, recuperação e alteração de senha pelo Supabase Auth.
- Cookies de sessão com `HttpOnly`, `SameSite=Lax` e `Secure` configurável por `COOKIE_SECURE`.
- Cookie de acesso e refresh renovados pelo middleware quando necessário.
- Formulário de cadastro com aceite obrigatório dos Termos de Uso e da Política de Privacidade.
- Confirmação de e-mail é um gate explícito: sessão, login, callback de confirmação e rotas protegidas recusam contas pendentes; há página própria e reenvio limitado.
- O botão `Sair` existe no shell autenticado e na área de Segurança.

### Perfil, currículo e documentos

- Importação de currículo em PDF textual, DOC e DOCX.
- Extração de nome, resumo, experiências, competências, formação e dados de contato.
- Perfil profissional editável e preferências de cargo, localização, modalidade, palavras-chave e score.
- Estúdio independente em `/criar-documentos` para informar cargo, empresa, local, URL e detalhes da vaga.
- Geração de prévia de currículo adaptado e carta de apresentação personalizada.
- Prévia gratuita com conteúdo limitado; arquivos completos são liberados por plano ou compra avulsa.
- Geração de DOCX do currículo e da carta após autorização de exportação.
- Fluxo de importação mostra o estado concluído e permite substituir o currículo.

### Captação e análise de vagas

- Cadastro manual e captação por texto copiado.
- Captação por print, imagem e PDF com OCR local.
- Recuperação de informações de páginas públicas e dados `JobPosting` quando disponíveis.
- Integração Gmail com OAuth individual e escopo `gmail.readonly`.
- Monitor automático do Gmail e separação de alertas-resumo em vagas individuais.
- Integração Outlook/Microsoft Graph com escopo de leitura e monitor equivalente.
- Detecção de duplicidade e registro de mensagens já processadas.
- Parser de localização, modalidade e salário em vários formatos.
- Modalidades Presencial, Híbrido e Remoto já são reconhecidas parcialmente.
- Análise de aderência com score, pontos fortes, lacunas, recomendação e justificativa.
- Motor de decisão com `AUTOMATICA`, `REVISAR` e `DESCARTAR`.
- Confiança de captura abaixo de 80%, localização/modalidade ausentes e pendências relevantes levam a revisão.
- Detecção de sinais de vaga suspeita, cobrança indevida e contratação PJ/MEI apresentada como emprego.

### Fila, vagas e candidaturas

- Fila persistente com aprovação, recusa, expiração e promoção para vaga/candidatura.
- Dashboard com filtros de decisão e status, busca por cargo/empresa e contadores.
- Paginação da fila com 5, 10 ou 25 itens por página.
- Estado vazio com ação direta para captar uma vaga.
- Cabeçalho reorganizado com CTA único `+ Captar vaga`, menu `Ações` e Preferências compactas.
- Banco de vagas com busca, origem, localização, modalidade, salário e detalhes completos.
- Detalhamento da vaga abre dentro do site e exibe análise, currículo, carta e próximo passo.
- Botão para abrir o anúncio original e iniciar candidatura no site da plataforma.
- O sistema registra a candidatura enviada quando o usuário conclui o envio na plataforma externa.
- A candidatura automática geral ainda não está habilitada.

### Pagamentos

- Checkout de exportação integrado com Mercado Pago.
- Checkout de exportação integrado com InfinitePay; `INFINITEPAY_HANDLE` e `INFINITEPAY_EXPORT_PRICE_CENTS` estão configurados no Render, mas a conta ativa e uma transação real ainda não foram confirmadas diretamente no provedor.
- Webhooks consultam o status no provedor antes de liberar a exportação.
- Compras são associadas ao usuário e ao `order_nsu`.
- `receipt_url` é persistida quando o provedor informa o endereço do recibo.
- Ainda não existe envio automático de comprovante por e-mail.

### Segurança já publicada

- Middleware adiciona `Content-Security-Policy`, `Strict-Transport-Security` em HTTPS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` e `Permissions-Policy`.
- Rate limiting em memória por IP e identificador de conta para login, cadastro, recuperação de senha, reenvio de confirmação e alterações de credenciais.
- Limite retorna HTTP 429 com `Retry-After`.
- Dados de negócio filtrados por `owner_id` nas rotas principais.
- Refresh tokens de Gmail e Outlook cifrados com Fernet usando `TOKEN_ENCRYPTION_KEY`.
- Uploads têm limites de tamanho no backend: 5 MB para currículo e 10 MB para arquivos de vaga.
- Frontend usa `textContent` ou escape em vários pontos que exibem conteúdo de vaga.
- Segredos são configurados por variáveis de ambiente e não devem ser colocados no Git.

### Legal e privacidade já existentes

- `/termos` com Termos de Uso básicos.
- `/privacidade` com Política de Privacidade básica.
- `/seguranca` com alteração de e-mail, alteração de senha, integrações e configuração de autenticador.
- O cadastro exige aceite dos Termos e da Política.

### Operação e serviços externos já configurados

- Render Web Service com `autoDeploy: true` e `healthCheckPath: /health` definido em `render.yaml`.
- Supabase PostgreSQL e Supabase Auth são os serviços de dados e autenticação da produção.
- Google Cloud OAuth/Gmail e Microsoft Graph/Outlook são integrações externas autorizadas pelo usuário.
- Mercado Pago e InfinitePay são os provedores externos de checkout.
- UptimeRobot é usado como monitor externo de disponibilidade do serviço público/health check. O monitor, intervalo e contatos de alerta não são armazenados no Git; devem ser conferidos diretamente na conta UptimeRobot quando houver auditoria operacional.
- Nenhuma dessas configurações externas deve ser recriada como se estivesse ausente sem antes verificar o painel do respectivo provedor.

## O que está parcial ou ainda não existe

- O gate de confirmação de e-mail está implementado; falta validar em produção as configurações de confirmação, os templates/redirecionamentos do Supabase e o fluxo em mais de um provedor de e-mail.
- A integração InfinitePay está configurada no Render; falta validar no painel do provedor o status da conta, o recebimento do webhook e um checkout controlado antes de aceitar pagamentos reais.
- O card de onboarding aparece de forma estática no dashboard e ainda não acompanha sempre o estado real de `/profile` e `/preferences`.
- Logout existe, mas falta torná-lo mais óbvio no cabeçalho global em todas as telas.
- Rate limiting é local ao processo; ainda falta proteção distribuída no edge quando houver múltiplas instâncias.
- CSP usa `unsafe-inline` porque as telas atuais contêm scripts e estilos inline; a política precisa ser endurecida depois da migração para nonces ou arquivos externos.
- Falta teste formal de IDOR/RLS com dois usuários para cada rota que recebe IDs, principalmente downloads e exportações. O script `scripts/migrate_rls.py` cobre as tabelas de negócio, mas ainda não inclui `document_export_purchases` e não houve confirmação de aplicação em todas as tabelas no projeto de produção.
- A aplicação usa `SUPABASE_PUBLISHABLE_KEY` e não há `SERVICE_ROLE_KEY` no código ou no `render.yaml`; ainda falta revisar no painel do Supabase e do Render se a chave mestra nunca foi exposta e se o acesso do banco segue o menor privilégio.
- Currículo e arquivos de vaga já conferem assinatura/formato em seus parsers; a foto de perfil ainda confia no `content_type` declarado e falta uma camada central que imponha magic bytes em todos os uploads.
- Falta garantir área temporária privada para todos os processamentos de arquivo e expurgo automático de anexos/rascunhos antigos.
- Falta sanitização central no backend para conteúdo de vaga, e-mail e OCR que possa voltar para HTML.
- O avaliador que envia pergunta, resposta e contexto para a Gemini ainda precisa de uma fronteira explícita de dados não confiáveis e testes contra prompt injection.
- Falta verificação contra senhas comprometidas e fluxo completo de MFA no login, recuperação, revogação e expiração de sessões.
- Os handlers de webhook consultam o provedor antes de liberar a compra, mas as rotas de webhook ainda não estão na lista pública do middleware de autenticação; também falta assinatura/verificação equivalente e idempotência explícita contra replay.
- As rotas de download verificam o `owner_id` da candidatura e exigem uma compra `PAID` para o usuário, mas ainda falta amarrar a autorização a uma transação/exportação específica e validar esse cenário com dois usuários.
- A conexão PostgreSQL é criada a partir de `DATABASE_URL`, mas o código não força `sslmode=require`; falta confirmar no Render que a URL de produção exige TLS.
- Não há handler global para exceções inesperadas; o endpoint `/health` ainda devolve `str(exc)` no campo `detail`, e alguns erros de integração podem propagar mensagens técnicas. Falta padronizar respostas públicas e manter detalhes somente nos logs internos.
- O OCR do endpoint `/intake/file` é chamado de forma síncrona dentro de uma rota `async`; monitores Gmail/Outlook usam tarefas no mesmo processo e as chamadas externas têm timeouts individuais, mas não há limite total de 30 segundos nem isolamento de recursos para OCR/IA.
- Não há evidência versionada de backup diário, teste de restauração ou runbook de revogação/rotação de tokens OAuth e chaves de API após exposição.
- Modalidade, salário e localização têm parsing parcial; regime CLT, PJ, MEI, estágio e não informado ainda não são campos estruturados completos.
- Falta separar claramente salário oferecido de pretensão salarial do candidato.
- Falta envio de recibo por e-mail após pagamento confirmado.
- Falta retenção configurável e expurgo automático após 30/60 dias para temporários, prints e rascunhos abandonados.
- Falta exportação/portabilidade e exclusão definitiva da conta no mesmo fluxo LGPD.
- Falta registrar versão e data do consentimento aceito pelo usuário.
- O monitor Gmail/Outlook ainda roda junto do processo web; falta worker distribuído independente.
- O monitor UptimeRobot não é controlado pelo código; alterações de intervalo, URL ou alertas precisam ser feitas no painel do UptimeRobot.
- A busca de páginas públicas já bloqueia hosts e IPs não globais, valida cada redirecionamento e limita o corpo recebido; a proteção contra SSRF precisa permanecer coberta por testes de regressão.
- O OCR usa arquivos temporários e os remove em `finally`; documentos gerados e outros fluxos ainda precisam de uma política uniforme de diretório privado e expurgo.
- Não existe painel administrativo multiusuário.
- Não existe aprendizado baseado em entrevistas, aprovações e reprovações.
- O produto ainda não fecha o ciclo de resultado: não há atribuição confiável entre versão do currículo, canal, candidatura e entrevista qualificada.
- A proteção contra golpes já aparece como sinal na análise, mas ainda não é uma porta de entrada claramente posicionada nem um fluxo completo de risco antes da candidatura.
- As heurísticas de RH brasileiro ainda não estão formalizadas como regras versionadas e explicáveis do motor de análise.
- Não existe visão Kanban, extensão de navegador ou exportação operacional para CSV/Excel.

## Direção de produto incorporada ao planejamento

As orientações de produto foram lidas junto com o histórico técnico e foram incorporadas sem deslocar o P0 de segurança, privacidade e pagamentos. A ordem adotada é:

- **Resultado medido antes de escala:** registrar fonte, versão do currículo/carta, decisão, candidatura enviada, retorno, entrevista qualificada e desfecho. A métrica principal continua sendo entrevistas qualificadas por 100 candidaturas.
- **Proteção contra golpe como proposta central:** ampliar os sinais de vaga falsa, cobrança indevida, PJ disfarçado e inconsistências do anúncio para uma decisão de risco visível antes de abrir ou enviar a candidatura.
- **Conhecimento de RH como regra do produto:** transformar critérios de triagem, ATS, pretensão salarial, regime e sinais de vaga fantasma em heurísticas versionadas, justificadas e testáveis, complementando a IA.
- **Prova antes de promessa:** qualquer alegação de aumento de conversão deverá vir de dados observados no produto; não será apresentada como promessa antes de haver amostra e atribuição suficientes.

## Próximas prioridades

### P0 — antes de aceitar usuários pagantes

1. Executar testes de isolamento entre dois usuários em vagas, candidaturas, documentos, fila, compras, integrações e rotas de download/exportação; ativar e verificar RLS em todas as tabelas do Supabase, incluindo `document_export_purchases`, e exigir dono compatível e transação paga válida.
2. Corrigir a exposição dos webhooks de pagamento ao provedor e validar assinatura, consulta server-to-server e idempotência atômica contra replays; uma transição já paga não deve ser reaplicada.
3. Validar MFA de ponta a ponta, incluindo desafio no login, recuperação, revogação e expiração de sessões.
4. Centralizar validação de tamanho, extensão, MIME e assinatura real (magic bytes) dos uploads, incluindo foto de perfil.
5. Sanitizar/escapar conteúdo externo no backend para fechar a superfície de XSS armazenado.
6. Revisar CSP com OAuth e checkout e eliminar gradualmente `unsafe-inline` com nonces ou scripts externos.
7. Criar tratamento global de exceções com respostas JSON padronizadas, sem stack traces ou detalhes de banco/provedor, e remover detalhes técnicos de endpoints públicos como `/health`.
8. Validar em produção o gate de verificação de e-mail, os templates/redirecionamentos do Supabase e o reenvio limitado.
9. Confirmar no painel da InfinitePay que a conta está habilitada, testar checkout/webhook controlado e registrar o resultado sem expor credenciais.
10. Validar no Render o rate limiting publicado e preparar proteção distribuída na borda.
11. Implementar retorno de foco ao botão que abriu cada modal e foco inicial previsível dentro do diálogo.
12. Isolar OCR/IA/leitura de e-mail em tarefas controladas, evitar bloquear o loop HTTP e impor limite total de 30 segundos e limites de concorrência/CPU por processamento.
13. Colocar todos os arquivos processados em área temporária privada e definir limpeza segura.
14. Auditar variáveis do Render, o histórico Git, o uso exclusivo da `SUPABASE_PUBLISHABLE_KEY`, a ausência de `SERVICE_ROLE_KEY` no cliente e `sslmode=require` na conexão PostgreSQL.
15. Adicionar consulta segura contra senhas comprometidas sem enviar a senha completa a terceiros.
16. Confirmar backups diários do Supabase, executar um teste de restauração e documentar a revogação/rotação emergencial de tokens OAuth e chaves de API.

### P1 — resultado, proteção, LGPD, IA e monetização

1. Fechar o loop de resultado: persistir eventos de candidatura e retorno, versionar currículo/carta e origem, registrar entrevistas qualificadas e criar a primeira visão de conversão por 100 candidaturas.
2. Transformar proteção contra golpe em etapa explícita de risco, com sinais, explicação, bloqueio ou revisão e registro do resultado para calibrar os critérios.
3. Formalizar heurísticas de RH brasileiro para triagem, ATS, pretensão salarial, regime e vaga fantasma; cada regra deve ser versionada, explicável e coberta por teste.
4. Implementar no mesmo sprint a exportação/portabilidade e a exclusão definitiva da conta, com confirmação forte, remoção de dados relacionados e política de retenção.
5. Registrar versão, data e evidência do consentimento de Termos e Privacidade.
6. Criar rotina de expurgo automático de temporários, prints e rascunhos após prazo configurável de 30/60 dias.
7. Delimitar conteúdo de vagas, OCR, Gmail e PDFs como dados não confiáveis; adicionar testes contra prompt injection.
8. Estruturar CLT/PJ/MEI/estágio, modalidade e salário com confiança de extração e exibição na análise.
9. Enviar comprovante simples por e-mail depois da confirmação idempotente do pagamento.
10. Finalizar os textos legais com responsável, canal de contato, retenção e subprocessadores.
11. Sincronizar o card de onboarding com o perfil e as preferências reais.
12. Exibir links legais e logout no cabeçalho/rodapé global.

### Próximo ciclo prático já classificado

1. **Gate de e-mail confirmado:** já implementado no backend; o próximo trabalho é somente validar a configuração real do Supabase, templates, redirecionamentos e reenvio em produção. Não é uma nova implementação P0.
2. **Idempotência de pagamentos:** permanece dentro do **P0.2**, junto da assinatura dos webhooks e da exposição pública correta das rotas. A chave deve registrar `order_nsu` e `payment_id` e permitir apenas uma transição válida para `PAID`.
3. **Expurgo automático de uploads:** permanece em **P1.6**, depois do fechamento do P0; a rotina deve cobrir temporários, prints e rascunhos abandonados com prazo configurável de 30/60 dias.

### P2 — escala e diferenciação

- Separar Gmail/Outlook em worker próprio e monitorar falhas.
- Configurar domínio próprio, DNS autoritativo redundante e recuperação operacional; quando o domínio definitivo existir, avaliar proxy da Cloudflare para filtrar tráfego L7 antes do Render.
- Adicionar Kanban de candidaturas e exportação CSV/Excel/JSON.
- Criar extensão de navegador para captação autorizada.
- Criar painel administrativo para acompanhar a operação e as métricas já instrumentadas.
- Adicionar aprendizado baseado nos resultados das candidaturas depois que houver volume e atribuição confiáveis.

## Validações recentes

- Compilação de `app/auth.py`, `app/main.py` e `app/security.py` aprovada.
- 25 testes de autenticação e controles de segurança aprovados, incluindo cadastro/login/callback pendentes e redirecionamento de contas não confirmadas.
- Cabeçalhos de segurança confirmados no endpoint público `/health`.
- Deploy `e84fd60` confirmado como ativo no Render.
- Health check do Render e monitor externo UptimeRobot fazem parte da operação; credenciais e IDs dos monitores não são documentados por segurança.
- A suíte completa foi reexecutada após instalar a dependência declarada `psycopg[binary]`: **71 testes aprovados em 3,776 s**. O registro histórico de 59 testes ficou desatualizado porque novos testes foram adicionados.

## Auditoria do checklist de segurança e operação — 17/09/2026

| Item verificado | Evidência encontrada | Estado e prioridade |
| --- | --- | --- |
| Confirmação de e-mail | Gate no backend, tela pública de confirmação e reenvio limitado; deploy `e84fd60` ativo | Implementado; validação com conta real e templates do Supabase permanece em **P0.8** |
| Cookies e headers | Cookies `HttpOnly`, `Secure` configurável e `SameSite=Lax`; middleware publica CSP, HSTS em HTTPS, `nosniff`, `DENY` e políticas complementares | Implementado; endurecimento da CSP segue em **P0.6** |
| Rate limiting | Limites por IP/conta e testes de 429 aprovados; armazenamento é local ao processo | Proteção distribuída segue em **P0.10** |
| Isolamento/IDOR | Rotas principais filtram `owner_id`, inclusive fila; não há teste integrado com dois usuários | Validação pendente em **P0.1** |
| RLS e menor privilégio | `scripts/migrate_rls.py` cria políticas para as tabelas de negócio, mas não inclui `document_export_purchases`; aplicação e Render não referenciam `SERVICE_ROLE_KEY`, porém a aplicação do RLS e o papel efetivo do banco ainda não foram confirmados em produção | Completar e testar RLS em **P0.1**; revisar chaves e papel do banco em **P0.14** |
| Uploads | PDF/DOCX e arquivos de vaga conferem assinatura e limites; foto de perfil aceita o MIME declarado | Centralização e magic bytes em **P0.4** |
| Arquivos temporários | OCR remove temporários ao terminar; não há política uniforme para documentos gerados, rascunhos e expurgo | Área privada em **P0.13**; retenção automática em **P1.6** |
| MFA | Há endpoints de inscrição, desafio e verificação TOTP para usuário já autenticado; não há desafio integrado ao login, recuperação, revogação e expiração | Validação ponta a ponta em **P0.3** |
| Gmail/Outlook | Gmail usa `gmail.readonly`; refresh tokens são cifrados com Fernet; OAuth usa `state` assinado e expirável | Implementado; manter auditoria de configuração do provedor |
| XSS e prompt injection | Captura remove tags HTML e frontend escapa vários campos; a entrada enviada ao avaliador Gemini ainda não tem fronteira central de dados não confiáveis nem testes hostis | XSS armazenado em **P0.5**; prompt injection em **P1.7** |
| Webhooks de pagamento | Handlers consultam Mercado Pago/InfinitePay antes de marcar pago; middleware exige sessão porque os caminhos não estão públicos; falta assinatura e guarda idempotente explícita | Correção completa em **P0.2** |
| Downloads e exportações | Rotas filtram a candidatura pelo usuário e exigem uma compra `PAID` do proprietário; a autorização ainda não está vinculada a uma transação/exportação específica e falta teste integrado de IDOR | Refinamento e teste em **P0.1** |
| Erros e informação interna | Não há handler global; `/health` devolve `str(exc)` e algumas rotas deixam exceções inesperadas subirem | Padronização sem vazamento em **P0.7** |
| Tarefas pesadas | OCR usa temporários removidos, mas `/intake/file` executa OCR síncrono na rota `async`; monitores rodam como tarefas no mesmo processo e falta limite total de 30 segundos | Isolamento, timeout total e concorrência em **P0.12** |
| Backup e recuperação | O repositório não comprova backup diário, teste de restauração ou runbook de revogação/rotação de credenciais | Confirmar e testar em **P0.16** |
| SQL injection | Consultas de negócio usam SQLAlchemy com parâmetros; SQL dinâmico encontrado no script de RLS usa apenas nomes de tabelas constantes do próprio código | Coberto na revisão atual; manter regra de não interpolar entrada do usuário |
| SSRF | `job_source_fetcher` rejeita credenciais, resolve DNS, bloqueia IPs não globais, revalida redirecionamentos e limita resposta | Coberto na revisão atual; manter testes de regressão |
| Termos, privacidade e consentimento | Páginas e checkbox existem; versão/data/evidência do consentimento não são persistidas | Consentimento em **P1.5**; textos legais em **P1.10** |
| Exportação e exclusão LGPD | Não há fluxo de portabilidade e exclusão definitiva | **P1.4** |
| Recibo por e-mail | `receipt_url` pode ser persistida, mas não há envio automático | **P1.9** |
| InfinitePay | Variáveis `INFINITEPAY_HANDLE` e `INFINITEPAY_EXPORT_PRICE_CENTS` presentes no Render; não houve teste de checkout real nem confirmação independente do painel da conta | Configuração presente; validação do provedor em **P0.9** |
| UptimeRobot | Monitor externo de disponibilidade/health check já faz parte da operação e está documentado; IDs e alertas ficam no painel externo | Concluído operacionalmente; conferir painel quando houver auditoria, sem recriar configuração |
| Suíte completa | Dependência `psycopg[binary]` instalada no ambiente local; descoberta completa executou 71 testes | **Concluído nesta verificação** |
| Acessibilidade dos modais | Diálogos usam `<dialog>` e controles nomeados, mas os fechamentos chamam `.close()` sem retorno de foco sistemático ao disparador | **P0.11** |

## Variáveis e segredos

Os valores reais não pertencem a este documento. Devem permanecer somente no painel do Render ou no ambiente local protegido:

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`;
- `COOKIE_SECURE`, `AUTH_REQUIRED`, `APP_BASE_URL`;
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_STATE_SECRET`;
- `TOKEN_ENCRYPTION_KEY`;
- `GEMINI_API_KEY`;
- credenciais, tokens e chaves dos webhooks Mercado Pago/InfinitePay.

## Histórico recente de entregas

| Commit | Entrega |
| --- | --- |
| `cad91fb` | Cabeçalhos de segurança e rate limiting de autenticação |
| `863f9e8` | Verificação de e-mail e portabilidade/exclusão agrupadas no planejamento P0/P1 |
| `66f5c7d` | Retenção, recibos, prompt injection e parsing de regime/modalidade/salário no planejamento |
| `2c05531` | Refinamento do backlog de segurança, logout, onboarding, XSS e webhooks |
| `f2d9a7c` | Roadmap de segurança, privacidade e LGPD |
| `b44daee` | Ações do dashboard, busca e paginação da fila |
| `6c00d98` | Estúdio de currículo e carta adaptados |
| `90aeccb` | Checkout de exportação via Mercado Pago |
| `4f00417` | Checkout de exportação via InfinitePay |

## Regra para continuar o projeto

Não liberar candidatura automática geral nem aceitar usuários pagantes antes de concluir o P0, testar o isolamento de dados e validar os webhooks. Não registrar senhas, tokens, chaves ou URLs privadas em commits, Markdown, logs ou conversas.
