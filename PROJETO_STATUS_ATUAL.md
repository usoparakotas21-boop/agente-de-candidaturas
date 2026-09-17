# Agente de Candidaturas — status atual

**Atualizado em:** 17/09/2026  
**Versão declarada da API:** 0.24.0  
**Commit publicado:** `e84fd60` — `Enforce email confirmation before access`
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
- Checkout de exportação integrado com InfinitePay.
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
- O card de onboarding aparece de forma estática no dashboard e ainda não acompanha sempre o estado real de `/profile` e `/preferences`.
- Logout existe, mas falta torná-lo mais óbvio no cabeçalho global em todas as telas.
- Rate limiting é local ao processo; ainda falta proteção distribuída no edge quando houver múltiplas instâncias.
- CSP usa `unsafe-inline` porque as telas atuais contêm scripts e estilos inline; a política precisa ser endurecida depois da migração para nonces ou arquivos externos.
- Falta teste formal de IDOR/RLS com dois usuários para cada rota que recebe IDs.
- Currículo e arquivos de vaga já validam assinatura/formato em seus parsers; a foto de perfil ainda confia no `content_type` declarado e falta uma camada central para todos os uploads.
- Falta garantir área temporária privada para todos os processamentos de arquivo e expurgo automático de anexos/rascunhos antigos.
- Falta sanitização central no backend para conteúdo de vaga, e-mail e OCR que possa voltar para HTML.
- Falta verificação contra senhas comprometidas e fluxo completo de MFA no login, recuperação e revogação.
- Os handlers de webhook consultam o provedor antes de liberar a compra, mas as rotas de webhook ainda não estão na lista pública do middleware de autenticação; também falta assinatura/verificação equivalente e idempotência explícita contra replay.
- Modalidade, salário e localização têm parsing parcial; regime CLT, PJ, MEI, estágio e não informado ainda não são campos estruturados completos.
- Falta separar claramente salário oferecido de pretensão salarial do candidato.
- Falta envio de recibo por e-mail após pagamento confirmado.
- Falta retenção configurável e expurgo automático após 30/60 dias para temporários, prints e rascunhos abandonados.
- Falta exportação/portabilidade e exclusão definitiva da conta no mesmo fluxo LGPD.
- Falta registrar versão e data do consentimento aceito pelo usuário.
- O monitor Gmail/Outlook ainda roda junto do processo web; falta worker distribuído independente.
- O monitor UptimeRobot não é controlado pelo código; alterações de intervalo, URL ou alertas precisam ser feitas no painel do UptimeRobot.
- Não existe painel administrativo multiusuário.
- Não existe aprendizado baseado em entrevistas, aprovações e reprovações.
- Não existe visão Kanban, extensão de navegador ou exportação operacional para CSV/Excel.

## Próximas prioridades

### P0 — antes de aceitar usuários pagantes

1. Validar em produção o gate de verificação de e-mail, os templates/redirecionamentos do Supabase e o reenvio limitado.
2. Corrigir a exposição dos webhooks de pagamento ao provedor e validar assinatura, consulta server-to-server e idempotência contra replays.
3. Validar no Render o rate limiting publicado e preparar proteção distribuída na borda.
4. Executar testes de isolamento entre dois usuários em vagas, candidaturas, documentos, fila, compras e integrações.
5. Centralizar validação de tamanho, extensão, MIME e assinatura dos uploads, incluindo foto de perfil.
6. Colocar todos os arquivos processados em área temporária privada e definir limpeza segura.
7. Revisar CSP com OAuth e checkout e eliminar gradualmente `unsafe-inline`.
8. Auditar variáveis do Render e o histórico Git em busca de segredos.
9. Validar MFA de ponta a ponta, incluindo desafio no login, recuperação e revogação.
10. Adicionar consulta segura contra senhas comprometidas sem enviar a senha completa a terceiros.
11. Sanitizar/escapar conteúdo externo no backend para fechar a superfície de XSS armazenado.
12. Reexecutar a suíte completa em ambiente com todas as dependências instaladas; a execução local atual está bloqueada por `psycopg` ausente no `venv`.

### P1 — LGPD, IA e monetização

1. Implementar no mesmo sprint a exportação/portabilidade e a exclusão definitiva da conta, com confirmação forte, remoção de dados relacionados e política de retenção.
2. Registrar versão, data e evidência do consentimento de Termos e Privacidade.
3. Criar rotina de expurgo automático de temporários, prints e rascunhos após prazo configurável de 30/60 dias.
4. Delimitar conteúdo de vagas, OCR, Gmail e PDFs como dados não confiáveis; adicionar testes contra prompt injection.
5. Estruturar CLT/PJ/MEI/estágio, modalidade e salário com confiança de extração e exibição na análise.
6. Enviar comprovante simples por e-mail depois da confirmação idempotente do pagamento.
7. Finalizar os textos legais com responsável, canal de contato, retenção e subprocessadores.
8. Sincronizar o card de onboarding com o perfil e as preferências reais.
9. Exibir links legais e logout no cabeçalho/rodapé global.

### P2 — escala e diferenciação

- Separar Gmail/Outlook em worker próprio e monitorar falhas.
- Configurar domínio próprio, DNS autoritativo redundante e recuperação operacional.
- Adicionar Kanban de candidaturas e exportação CSV/Excel/JSON.
- Criar extensão de navegador para captação autorizada.
- Criar painel administrativo e métricas de entrevistas qualificadas.
- Adicionar aprendizado baseado nos resultados das candidaturas.

## Validações recentes

- Compilação de `app/auth.py`, `app/main.py` e `app/security.py` aprovada.
- 25 testes de autenticação e controles de segurança aprovados, incluindo cadastro/login/callback pendentes e redirecionamento de contas não confirmadas.
- Cabeçalhos de segurança confirmados no endpoint público `/health`.
- Deploy `e84fd60` confirmado como ativo no Render.
- Health check do Render e monitor externo UptimeRobot fazem parte da operação; credenciais e IDs dos monitores não são documentados por segurança.
- O conjunto histórico registrava 59 testes aprovados em 15/09/2026; a suíte completa precisa ser reexecutada no ambiente com todas as dependências instaladas.

## Auditoria do checklist de segurança e operação — 17/09/2026

| Item verificado | Evidência encontrada | Estado e prioridade |
| --- | --- | --- |
| Confirmação de e-mail | Gate no backend, tela pública de confirmação e reenvio limitado; deploy `e84fd60` ativo | Implementado; validação com conta real e templates do Supabase permanece em **P0.1** |
| Cookies e headers | Cookies `HttpOnly`, `Secure` configurável e `SameSite=Lax`; middleware publica CSP, HSTS em HTTPS, `nosniff`, `DENY` e políticas complementares | Implementado; endurecimento da CSP segue em **P0.7** |
| Rate limiting | Limites por IP/conta e testes de 429 aprovados; armazenamento é local ao processo | Proteção distribuída segue em **P0.3** |
| Isolamento/IDOR | Rotas principais filtram `owner_id`, inclusive fila; não há teste integrado com dois usuários | Validação pendente em **P0.4** |
| Uploads | PDF/DOCX e arquivos de vaga conferem assinatura e limites; foto de perfil aceita o MIME declarado | Centralização e foto em **P0.5** |
| Arquivos temporários | OCR remove temporários ao terminar; não há política uniforme para documentos gerados, rascunhos e expurgo | Área privada em **P0.6**; retenção automática em **P1.3** |
| Gmail/Outlook | Gmail usa `gmail.readonly`; refresh tokens são cifrados com Fernet; OAuth usa `state` assinado e expirável | Implementado; manter auditoria de configuração do provedor |
| XSS e prompt injection | Captura remove tags HTML e frontend escapa vários campos; não há sanitização central nem testes de conteúdo hostil na IA | XSS armazenado em **P0.11**; prompt injection em **P1.4** |
| Webhooks de pagamento | Handlers consultam Mercado Pago/InfinitePay antes de marcar pago; middleware exige sessão porque os caminhos não estão públicos; falta assinatura e guarda idempotente explícita | Correção completa em **P0.2** |
| Termos, privacidade e consentimento | Páginas e checkbox existem; versão/data/evidência do consentimento não são persistidas | **P1.2** e **P1.7** |
| Exportação e exclusão LGPD | Não há fluxo de portabilidade e exclusão definitiva | **P1.1** |
| Recibo por e-mail | `receipt_url` pode ser persistida, mas não há envio automático | **P1.6** |
| UptimeRobot | Monitor externo de disponibilidade/health check já faz parte da operação e está documentado; IDs e alertas ficam no painel externo | Concluído operacionalmente; conferir painel quando houver auditoria, sem recriar configuração |
| Suíte completa | 25 testes de auth/segurança passam; descoberta completa encontrou 48 testes, mas 5 módulos não importam no ambiente local porque `psycopg` não está instalado | Bloqueio de validação em **P0.12** |

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
