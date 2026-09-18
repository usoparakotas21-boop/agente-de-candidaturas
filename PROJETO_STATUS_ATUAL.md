# Agente de Candidaturas — status atual

**Atualizado em:** 18/09/2026
**Versão declarada da API:** 0.24.0  
**Commit publicado:** `e3d1390` — `feat: add branded AC favicon`
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
- O cadastro registra no metadata do usuário as versões dos Termos/Privacidade e o instante UTC do aceite; o backend rejeita chamadas sem os dois aceites explícitos.
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
- Modalidades Presencial, Híbrido e Remoto já são reconhecidas; a prévia de intake agora também devolve confiança de modalidade, salário e regime.
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

- Checkout de exportação integrado exclusivamente com Mercado Pago; o fallback de URL externa legado foi removido e toda compra avulsa exige candidatura vinculada.
- Rotas, permissões e variáveis de InfinitePay foram removidas do fluxo ativo; o checkout e o webhook aceitos são exclusivamente do Mercado Pago.
- Webhooks consultam o status no provedor antes de liberar a exportação.
- Compras são associadas ao usuário e ao `order_nsu`.
- `receipt_url` é persistida quando o provedor informa o endereço do recibo.
- O checkout grava o e-mail do pagador e o webhook confirmado tenta enviar um recibo transacional SMTP; o estado `SENT`, `FAILED` ou `SKIPPED` evita duplicidade e permite retry idempotente. As variáveis `SMTP_*` permanecem opcionais até o SMTP transacional ser configurado no Render.

### Segurança já publicada

- Middleware adiciona `Content-Security-Policy`, `Strict-Transport-Security` em HTTPS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` e `Permissions-Policy`.
- Rate limiting em memória por IP e identificador de conta para login, cadastro, recuperação de senha, reenvio de confirmação e alterações de credenciais.
- Limite retorna HTTP 429 com `Retry-After`.
- Dados de negócio filtrados por `owner_id` nas rotas principais.
- Testes de isolamento entre dois usuários cobrem listagem, consulta, atualização e downloads de vagas/candidaturas; o teste de cobertura garante que a migração RLS inclui todas as 11 tabelas do modelo.
- Refresh tokens de Gmail e Outlook cifrados com Fernet usando `TOKEN_ENCRYPTION_KEY`.
- Uploads têm limites de tamanho no backend: 5 MB para currículo e 10 MB para arquivos de vaga, com validação central de assinatura/magic bytes e decodificação de imagens.
- Conteúdo de vagas, e-mails e OCR passa por sanitização central antes de persistência ou análise; o frontend continua usando `textContent`/escape nas superfícies de exibição.
- Segredos são configurados por variáveis de ambiente e não devem ser colocados no Git.
- Assets estáticos usados pelas páginas autenticadas são servidos por rota pública com proteção contra traversal; isso permite carregar os controles de segurança sem sessão adicional.

### Legal e privacidade já existentes

- `/termos` com Termos de Uso básicos.
- `/privacidade` com Política de Privacidade básica.
- `/seguranca` com alteração de e-mail, alteração de senha, integrações e configuração de autenticador.
- O cadastro exige aceite dos Termos e da Política.

### Operação e serviços externos já configurados

- Render Web Service com `autoDeploy: true` e `healthCheckPath: /health` definido em `render.yaml`.
- Supabase PostgreSQL e Supabase Auth são os serviços de dados e autenticação da produção.
- Google Cloud OAuth/Gmail e Microsoft Graph/Outlook são integrações externas autorizadas pelo usuário.
- Mercado Pago é o único provedor externo de checkout no escopo ativo.
- UptimeRobot é usado como monitor externo de disponibilidade do serviço público/health check. O monitor, intervalo e contatos de alerta não são armazenados no Git; devem ser conferidos diretamente na conta UptimeRobot quando houver auditoria operacional.
- Nenhuma dessas configurações externas deve ser recriada como se estivesse ausente sem antes verificar o painel do respectivo provedor.

## O que está parcial ou ainda não existe

- O gate de confirmação de e-mail está implementado; `/termos` e `/privacidade` retornaram 200 sem sessão em produção com CSP/HSTS/nosniff ativos. A configuração do Supabase Auth foi conferida diretamente: `Confirm email` está ligado, o provedor Email está habilitado e o cadastro permanece permitido. Ainda falta apenas o teste operacional de recebimento/reenvio em mais de um provedor.
- InfinitePay está fora do escopo e não possui rota, variável ou critério de aceite ativo.
- O card de onboarding consulta `/profile` e `/preferences`: some quando os dois estão completos e vira um atalho de preferências quando o perfil já existe; mantém fallback estático se a consulta falhar.
- Logout existe no dashboard e agora também aparece como ação explícita no cabeçalho global das subpáginas autenticadas.
- Rate limiting é local ao processo; a verificação externa com 11 logins sintéticos retornou 10 respostas 401 e a 11ª 429. Ainda falta proteção distribuída no edge quando houver múltiplas instâncias.
- CSP usa nonce para scripts e elementos `<style>`, sem `style-src-attr unsafe-inline`; os templates ativos e scripts de interação foram migrados para classes/CSS nonceados. HSTS/nosniff/frame-ancestors continuam confirmados em `/health`, `/termos` e `/privacidade`.
- Os testes locais de IDOR entre dois usuários estão implementados e aprovados; ainda falta executar a mesma prova com duas contas reais contra o PostgreSQL/Supabase de produção.
- O script `scripts/migrate_rls.py` cobre as 11 tabelas do modelo, incluindo `document_export_purchases`. A migração foi aplicada no PostgreSQL de produção e a consulta somente leitura confirmou RLS habilitado e uma política em cada tabela.
- A aplicação usa `SUPABASE_PUBLISHABLE_KEY`, não há `SERVICE_ROLE_KEY` no código, no `render.yaml` ou na lista de variáveis exibida no Render; o painel do Supabase separa as chaves e os valores permaneceram mascarados durante a auditoria; a conexão efetiva de produção foi verificada após o reinício com `Enforce SSL` ativo.
- A validação central de upload já confere extensão, tamanho, magic bytes e estrutura/decodificação; a validação em produção continua no P0.2.
- Processamentos temporários são removidos no fluxo e documentos gerados ficam fora da raiz em diretório `0700`; falta ligar expurgo de rascunhos/objetos do Storage.
- A sanitização central de texto cobre captura, e-mail/OCR, confirmação e análise; superfícies HTML ativas são renderizadas com escaping e o CSP não aceita atributos de estilo inline.
- O avaliador da Gemini delimita pergunta, contexto e resposta como dados não confiáveis, sanitiza o conteúdo e instrui o modelo a ignorar comandos embutidos; testes hostis cobrem essa fronteira.
- A verificação contra senhas comprometidas usa k-anonimato (somente prefixo de 5 caracteres do SHA-1, nunca a senha ou o hash completo) e `PWNED_PASSWORD_CHECK` está presente no Render. O fluxo MFA de login, desafio, revogação e expiração já está implementado; a tela de segurança em produção foi validada. O Supabase mostra `Prevent use of leaked passwords` desativado e informa que o recurso exige plano Pro ou superior; a checagem externa do aplicativo permanece ativa e o upgrade/configuração nativa segue como pendência P0.10.
- A rota do Mercado Pago é pública, consulta o provedor e faz transição idempotente para `PAID`; o endpoint de produção e o evento Pagamentos estão configurados no painel, `MERCADOPAGO_WEBHOOK_SECRET` está presente no Render e o deploy está Live. Falta executar replay/checkout controlado em produção.
- As rotas de download verificam o `owner_id` da candidatura e agora exigem uma compra `PAID` vinculada ao `application_id` exato; o checkout Mercado Pago recebe a candidatura e o teste cruzado confirma que uma compra de outra candidatura não libera o arquivo. Falta validar o replay/checkout e o cenário com duas contas no Supabase de produção.
- O normalizador de `DATABASE_URL` converte PostgreSQL para `psycopg` e força `sslmode=require` quando ausente; falta confirmar no Render a URL efetiva e a negociação TLS.
- Handlers globais já padronizam erros públicos e mantêm detalhes nos logs; falta revisar endpoints operacionais legados.
- OCR, parsing, confirmação e busca externa já saem do loop HTTP e têm timeout total de 30 segundos; falta separar monitores/IA em worker próprio e impor limites distribuídos de concorrência/CPU.
- O runbook `DISASTER_RECOVERY.md` documenta backup, restauração isolada e revogação/rotação emergencial; `scripts/backup_supabase.py` já cria dump customizado, valida com `pg_restore`, gera checksum e não expõe a URL na linha de comando. O ambiente atual ainda não possui `pg_dump`/`pg_restore`, portanto execução, agendamento e restauração real continuam pendentes.
- A prévia de intake classifica CLT, PJ, MEI, estágio, temporário e freelance e informa confiança para modalidade, salário e regime; esses campos agora persistem na fila, na vaga promovida, no monitor Gmail e nas respostas de vagas/exportação. A faixa salarial oferecida também é guardada em `salary_min/salary_max`, separada das preferências de pretensão do candidato.
- Falta separar claramente salário oferecido de pretensão salarial do candidato.
- Falta envio de recibo por e-mail após pagamento confirmado.
- A retenção local de documentos gerados usa prazo configurável e agora roda no startup e em rotina periódica; expurgo de Storage, prints persistidos e rascunhos abandonados continua pendente porque não há bucket ativo.
- A exportação/portabilidade JSON owner-scoped está disponível na área de Segurança; falta a exclusão definitiva da conta e o expurgo completo dos objetos relacionados no mesmo fluxo LGPD.
- Consentimento de Termos/Privacidade agora é versionado e recebe data UTC no cadastro; uma trilha imutável administrativa continua opcional para uma etapa futura.
- O monitor Gmail/Outlook ainda roda junto do processo web; falta worker distribuído independente.
- O monitor UptimeRobot não é controlado pelo código; alterações de intervalo, URL ou alertas precisam ser feitas no painel do UptimeRobot.
- A busca de páginas públicas já bloqueia hosts e IPs não globais, valida cada redirecionamento e limita o corpo recebido; a proteção contra SSRF precisa permanecer coberta por testes de regressão.
- O OCR usa arquivos temporários e os remove em `finally`; documentos gerados usam diretório privado e retenção configurável. Expurgo de Storage/rascunhos ainda falta.
- Não existe painel administrativo multiusuário.
- Não existe aprendizado baseado em entrevistas, aprovações e reprovações.
- O ciclo de resultado agora registra canal, retorno externo e identificadores de versão do currículo/carta no evento de candidatura enviada; falta acumular uma amostra real para atribuição estatisticamente confiável.
- O avaliador de entrevistas já existe, mas ainda não transforma os gaps da vaga em um roteiro de preparação contextualizado para cada candidatura.
- Não há acompanhamento automático da zona morta após a candidatura, com prazo, lembrete e sugestão de follow-up apropriado ao canal.
- A proteção contra golpes agora preserva a faixa, score e evidências ao promover a vaga para candidatura; vagas duvidosas exigem revisão explícita antes de abrir o anúncio. Falta ampliar a cobertura por origem e validar o fluxo em produção.
- As heurísticas de RH brasileiro ainda não estão formalizadas como regras versionadas e explicáveis do motor de análise.
- Não existe visão Kanban, extensão de navegador ou exportação operacional para CSV/Excel.

## Divisor de águas incorporado ao planejamento

As ideias de diferenciação foram incluídas como produto de resultado e hábito, sem antecipar a extensão antes de fechar segurança, métricas e fluxo de candidatura:

- **Copiloto de entrevistas baseado em gaps:** usar os requisitos ausentes e os pontos fracos da análise para gerar perguntas prováveis, respostas orientadas por evidências do currículo e um plano de estudo por vaga.
- **Acompanhamento da zona morta:** iniciar o relógio quando a candidatura for registrada, sugerir lembrete e follow-up conforme o canal e permitir registrar resposta, entrevista ou encerramento.
- **Prova social por conversão:** mostrar a sequência vagas analisadas → candidaturas enviadas → entrevistas qualificadas, segmentada por origem e versão de currículo/carta, sem prometer aumento antes de haver amostra suficiente.
- **Extensão de navegador 1-click:** permanece como aposta de escala no P2; deverá usar permissões mínimas, consentimento explícito e captação autorizada em cada site.

## Direção de produto incorporada ao planejamento

As orientações de produto foram lidas junto com o histórico técnico e foram incorporadas sem deslocar o P0 de segurança, privacidade e pagamentos. A ordem adotada é:

- **Resultado medido antes de escala:** registrar fonte, versão do currículo/carta, decisão, candidatura enviada, retorno, entrevista qualificada e desfecho. A métrica principal continua sendo entrevistas qualificadas por 100 candidaturas.
- **Proteção contra golpe como proposta central:** ampliar os sinais de vaga falsa, cobrança indevida, PJ disfarçado e inconsistências do anúncio para uma decisão de risco visível antes de abrir ou enviar a candidatura.
- **Conhecimento de RH como regra do produto:** transformar critérios de triagem, ATS, pretensão salarial, regime e sinais de vaga fantasma em heurísticas versionadas, justificadas e testáveis, complementando a IA.
- **Prova antes de promessa:** qualquer alegação de aumento de conversão deverá vir de dados observados no produto; não será apresentada como promessa antes de haver amostra e atribuição suficientes.

## Visão de evolução do produto

| O que o site é hoje | O que o site será após a Prioridade 0 | O que faz o site dominar o mercado |
| --- | --- | --- |
| Painel operacional com boa base visual e segurança em consolidação. | SaaS estável e seguro, com P0 concluído, checkout funcional e UX redonda. | Copiloto completo de carreira: análise, documentos, preparação para entrevistas e extensão de navegador. |

## Auditoria das sugestões recebidas

As sugestões abaixo foram comparadas com o código, os testes, os painéis já verificados e a fila desta página. O destino indica a forma necessária para realmente encerrar o item.

| Sugestão | Veredito | Destino correto e complemento necessário |
| --- | --- | --- |
| Reorganizar ações do cabeçalho, CTA único, menu de documentos e paginação | Já feito | Sem nova tarefa; manter regressão visual e paginação funcionando |
| Badges, estados vazios, busca e contadores | Parcialmente feito | Badges, estados vazios e busca cargo/empresa existem; busca por tecnologia fica junto das heurísticas em **P1.3** se houver necessidade real |
| Kanban, donut de score e exportação CSV/Excel operacional | Faz sentido, mas não é gate | **P2**; exportação de dados pessoais para LGPD é separada e permanece em **P1.6** |
| Onboarding sincronizado e opção de dispensar | Incompleto | Sincronização do estado real em **P1.13**; dispensar é melhoria opcional depois da sincronização |
| Extensão Chrome/LinkedIn/Gupy | Faz sentido como escala | **P2**, com permissões mínimas, consentimento e limites de cada plataforma |
| Foco, `aria-modal` e retorno de foco dos modais | Validado em produção | Modais de captação, preferências, segurança e drawer de candidatura abriram com foco inicial, mantiveram o Tab dentro da superfície e devolveram o foco ao disparador |
| Verificação de e-mail, headers e rate limiting | Código principal feito | Validações de produção ficam em **P0.4**, **P0.7** e **P0.9**; rate limiting distribuído só é necessário antes de múltiplas instâncias |
| IDOR e RLS obrigatório | Concluído para as rotas atuais | Migração RLS, testes locais e prova real com duas contas cobrem listagem, consulta, atualização, exportação JSON e downloads de currículo/carta; a conta B recebeu 404 ao tentar usar a candidatura da conta A |
| `SERVICE_ROLE_KEY` fora do cliente e menor privilégio | Revisão de código feita; painel do Supabase separa chave publicável e chave secreta e mantém os valores mascarados; Enforce SSL foi ativado no banco; função auxiliar `public.rls_auto_enable()` não pode mais ser executada por `PUBLIC`, `anon` ou `authenticated` | **P0.6** confirmado para chaves, TLS e privilégio da função; não criar nem expor chave mestra |
| Magic bytes, MIME real, diretório privado e parsing isolado | Validação real aprovada para intake; fronteira de download reforçada | Em produção, um PDF falso sem assinatura `%PDF-` foi rejeitado sem criar vaga e um PDF válido foi reconhecido no preview, permanecendo sem salvar até confirmação. As rotas de download agora rejeitam caminhos fora do diretório privado; falta confirmar limpeza/isolamento final em **P0.2** |
| Gmail `readonly` e tokens criptografados | Feito no código | Manter auditoria de escopos e revogação; não criar escopos maiores |
| Sanitização/XSS e prompt injection | Implementado no código | Sanitização central, fronteira de prompts e CSP sem `style-src-attr unsafe-inline`; ampliar casos por origem permanece em **P1.8** |
| Assinatura, replay e idempotência de webhook | Código reforçado e agora fail-closed | Mercado Pago exige HMAC com janela de 5 minutos, consulta server-to-server, moeda BRL, valor exato, `order_nsu`/`payment_id` e transição idempotente; credenciais e rejeição sem assinatura já foram validadas em produção, faltando replay/checkout real em **P0.5** |
| Mensagens de erro genéricas | Feito no código | Handlers, fila e callbacks OAuth não expõem stack trace, detalhes de banco ou respostas brutas de provedores; manter revisão ao adicionar endpoints |
| OCR/IA assíncronos e timeout de 30 segundos | Proteção principal feita | Worker separado é escala operacional e fica em **P2**; não deve bloquear o primeiro ciclo pago enquanto os timeouts forem aplicados |
| Backup diário, restauração e revogação | Runbook e rotina externa feitos | Instalar PostgreSQL client tools, executar/agendar o dump e testar restauração isolada em **P0.11** |
| Cloudflare, DNS redundante e DDoS | Condicional | Só entram em **P2** quando houver domínio próprio e necessidade de borda; Render e UptimeRobot já cobrem a operação atual |
| Termos, privacidade, consentimento, portabilidade e exclusão | Parcialmente feito | Páginas e aceite existem; consentimento versionado é **P1.7**, exportação/exclusão no mesmo fluxo é **P1.6**, textos legais em **P1.11** |
| Acesso anônimo às páginas legais | Corrigido: `/termos` e `/privacidade` (com barra final) foram adicionadas à lista pública do middleware e testadas sem sessão | P0 concluído e validado em produção |
| Retenção de 30/60 dias | Necessário, mas não é gate de pagamento | Diretório privado e limpeza local já existem; expurgo de Storage, prints e rascunhos fica em **P1.8**, com prazo configurável e registro da exclusão |
| Comprovante por e-mail | Faz sentido depois do checkout | **P1.10**, somente após webhook assinado, idempotente e pagamento confirmado |
| CLT/PJ/MEI, modalidade, salário e pretensão | A prévia agora devolve modalidade, regime e confiança; a vaga persistida ainda não guarda o regime como campo próprio | **P1.9** em andamento; separar salário oferecido de pretensão do candidato e persistir a confiança |
| Métrica de entrevistas por 100 candidaturas | Divisor de águas | **P1.1 entregue no código**: registra canal, retorno externo e versão do documento; o painel só aponta melhor canal/versão após cinco envios na mesma amostra |
| Proteção contra golpes | Deve ser destaque de produto | **P1.2 entregue no código**: a decisão de risco acompanha a candidatura, bloqueia o avanço de risco alto e pede confirmação auditável para risco duvidoso; falta ampliar sinais por origem e validar o deploy |
| Heurísticas de RH brasileiro | Diferencial válido | **P1.3**, versionadas, explicáveis e testadas junto da IA |
| Copiloto de entrevistas e follow-up da zona morta | Faz sentido após medir eventos | **P1.4/P1.5**, dependem do registro correto de candidatura, retorno e entrevista |
| Candidatura automática geral | Não deve ser liberada agora | Continua desativada até fechar P0 e validar termos/fluxos de cada plataforma; abrir anúncio e iniciar candidatura com confirmação do usuário é o comportamento seguro atual |
| InfinitePay | Fora do escopo ativo | Não criar tarefa nem critério de aceite para esse provedor |
| UptimeRobot | Já existe | Não recriar; apenas conferir painel, intervalo e alertas durante auditoria operacional |
| Senhas comprometidas | Implementação adequada, mas com limite | k-anonimato e variável do Render estão feitos; o teste publicado é **P0.10**. A decisão fail-open/fail-closed deve ser documentada, pois indisponibilidade do serviço hoje não bloqueia a senha |

### Auditoria visual e de intake — 17/09/2026

As telas anexadas foram tratadas como evidência de comportamento, não como instruções isoladas. O código e os testes foram comparados antes de abrir novas tarefas:

| Achado | Situação após a verificação | Prioridade correta |
| --- | --- | --- |
| CSS de Outlook/Gmail vazando no título | Corrigido no parser HTML do Gmail: `style`, `script`, `noscript` e `template` são ignorados antes da sanitização; teste de regressão adicionado | P0.2 concluído no código; manter validação operacional de uploads/intake |
| URL pura usada como título | Corrigido no intake: slug de URL vira título legível (`Analista Administrativo`) | P0.2 concluído no código |
| Razão social com prefixo numérico de CNPJ | Corrigido no intake removendo o prefixo sem apagar o sufixo societário | P0.2 concluído no código |
| Alertas “27 vagas abertas...” salvos como uma vaga | Corrigido no Gmail: alertas agrupados sem ao menos duas vagas identificáveis são ignorados como resumo, em vez de inventar uma oportunidade; o splitter mantém a separação por URLs/títulos, reconhece links de LinkedIn/Indeed/Gupy/Glassdoor/Jobbol e preserva a plataforma como origem da vaga quando identificada | **P1.3 parcialmente entregue**; ampliar regras específicas por provedor quando houver amostras reais |
| Cards, badges, paginação, busca e estado vazio da fila | Já implementados; a incoerência textual entre “Aguardando revisão” e “Capturar” é nomenclatura de produto a revisar junto das heurísticas | P1.3 se houver mudança de decisão; sem novo P0 |
| `/vagas` exibe erro sem ação | Corrigido com botão local `Tentar novamente`, sem exigir F5; backend já retorna mensagem pública estável | P1.15 concluído no código e a rota foi reaberta em produção sem erro, exibindo estado vazio e contadores `0` |
| Modal abre com textos repetidos “Carregando...” | Ainda não há skeleton screen; trocar por blocos de carregamento é melhoria de percepção, sem impacto de segurança | P1.15 |
| Cabeçalho escuro duplicado no dashboard e subpáginas | Dashboard mantém seu cabeçalho próprio; subpáginas, incluindo `/seguranca`, mantêm somente a navegação global e o breadcrumb | **P1.15 concluído e validado em produção** |
| Botões Aprovar/Recusar genéricos e subtítulo de alerta repetido | Decisão e status são dados distintos; renomear ações e reduzir o subtítulo exige revisar copy e transições | P1.3, junto do modelo de decisão; não implementar só por aparência |
| Botão Limpar próximo da ação principal | Corrigido: virou `Limpar formulário`, com aparência neutra, confirmação quando há rascunho/prévia e retorno de foco ao primeiro campo | **P1.15 concluído e validado em produção** |
| Visualização da senha no login/cadastro/alteração | Controles mostrar/ocultar já existem; a tela de Segurança também teve o texto auxiliar do MFA corrigido para ficar em linha própria | P1.15 |
| Placeholders de salário ausentes | Adicionados exemplos `Ex.: 8.000` e `Ex.: 12.000` nas configurações | P1.9 concluído no código |
| R$ 9,90 avulso, FAQ e prova social na landing | A linha do avulso pode ser adicionada com o preço real; FAQ é copy útil; números de prova social só entram quando vierem de métricas observadas | P1.16; métricas de conversão permanecem P1.1 |
| Queda da rota `/vagas` após o carregamento | Corrigido no `jobs-enhance.js`: o `MutationObserver` não reordena a lista em ciclo contínuo; a página foi revalidada em produção com lista, filtros, detalhes e análise carregados | P0.8 concluído para esta causa; manter teste de regressão operacional |

### Auditoria de UX/UI e Customer Success — 18/09/2026

As novas sugestões foram comparadas com o que já está publicado. Os percentuais abaixo medem implementação, teste e validação compatíveis com o escopo do item; não representam uma avaliação subjetiva de gosto visual.

| Frente sugerida | Estado atual | Conclusão estimada | Destino correto |
| --- | --- | ---: | --- |
| Layout, estrutura responsiva, dashboards, perfil e funil | Dashboards essenciais, busca, paginação, estados vazios, perfil e funil de candidaturas existem; métricas de conversão estão instrumentadas em **P1.1** | **95%** | Sem nova tarefa; manter regressões |
| Refinamento de componentes, microinterações e consistência visual | Ações do cabeçalho, botões neutros, skeleton do drawer, feedback de upload e foco dos modais já foram tratados; faltam microinterações gerais e uma revisão visual final | **80%** | **P1.17** |
| Favicon e identidade visual na aba do navegador | Favicon `AC` em SVG publicado e injetado no shell público, páginas legais e páginas autenticadas | **100%** | **Concluído em P1.17**; validar a aba após o próximo deploy |
| Hierarquia dos dados complexos do OCR durante a edição | A tela de Currículos agora agrupa experiências, competências, formação e idiomas em um resumo revisável; ainda falta uma edição inline mais rica dos campos extraídos | **80%** | **P1.17** |
| Onboarding guiado em três passos | A sincronização do card com perfil/preferências está entregue em **P1.13**; não há tour guiado de primeiro acesso | **35%** | **P1.17** |
| Feedback assíncrono de OCR e validação de arquivos | Mensagens específicas, região de status acessível e skeleton do drawer existem; faltam estados de progresso mais claros para todos os processamentos longos | **75%** | **P1.17** |
| Erros de validação orientados à ação | Handlers públicos e validações de upload já são seguros e específicos; falta revisar a cópia e a ação de recuperação em todas as telas assíncronas | **85%** | **P1.17** |
| Widget de suporte ou canal direto | Não existe widget integrado nem canal contextual dentro do painel | **0%** | **P1.18** |
| Central de ajuda e FAQ | FAQ básico já está na landing em **P1.16**; a central pública `/ajuda` agora cobre formatos aceitos, privacidade, pagamentos e solução de problemas | **80%** | **P1.18** |
| E-mails de Customer Success | Preferências persistentes de frequência e tipos de aviso agora estão disponíveis; recibo pós-pagamento aguarda SMTP de produção em **P1.10**, e os envios de boas-vindas, lembretes e mudanças de status ainda não existem | **45%** | **P1.19** |

Essas sugestões não alteram a ordem do P0: nenhuma delas substitui os gates de isolamento, uploads, MFA, confirmação de e-mail, Mercado Pago, senhas comprometidas e backup. O suporte e os e-mails entram depois desses gates porque dependem de uma operação pagante estável.

### Auditoria de job scraping e ingestão de fontes — 18/09/2026

As sugestões de raspagem foram comparadas com a implementação atual e classificadas por dependência, risco legal e necessidade operacional. A conclusão não autoriza scraping de plataformas protegidas nem uso imediato de proxies: primeiro entram fontes licenciadas ou páginas públicas permitidas, com limites claros e possibilidade de desligar cada conector.

| Proposta | Estado atual | Conclusão e prioridade |
| --- | --- | --- |
| Captura por Gmail/Outlook e entrada manual por texto/arquivo | Já existe; o monitor identifica fontes, separa alertas agrupados, sanitiza o conteúdo e envia o resultado para a fila. A captação manual pode buscar uma página HTML pública com SSRF, redirecionamento, tamanho e timeout limitados | **Coberto em P0/P1**; manter regressões e ampliar amostras por provedor em **P1.3/P1.8** |
| Parser estruturado de modalidade, CLT/PJ/MEI, salário e senioridade | Já existe no intake e na vaga promovida, com confiança por campo e distinção entre salário da vaga e preferências do candidato | **P1.9 em andamento**; enriquecer por fonte quando novos conectores forem aceitos |
| Deduplicação de vagas | Parcialmente existe: `QueueItem` usa hash de URL limpa ou cargo/empresa/local, com contagem de reaparições; o intake também cria `external_id` determinístico | **P2 — completar identidade canônica** com `external_id` da fonte, URL canônica e fingerprint de conteúdo; fuzzy matching só como fallback revisável |
| APIs oficiais ou agregadores (por exemplo Jooble/Adzuna) | Não há adaptadores nem contrato ativo mapeado | **P2.1 novo**; comparar licença, custo, cobertura Brasil, limites e atribuição antes de desenvolver. Só fontes autorizadas entram |
| Conectores para ATS públicos (Gupy e portais de carreira) | Os links são reconhecidos e podem ser lidos quando fornecidos pelo usuário, mas não existe coleta agendada por ATS | **P2.2 novo**; piloto de duas ou três fontes públicas estáveis, cada uma com parser e chave de desligamento próprios |
| Fetcher → parser → deduplicador → enriquecedor | As peças existem de forma síncrona para intake e Gmail; não há pipeline de descoberta contínua | **P2.3**; consolidar uma interface de ingestão para reuso das peças atuais e incluir senioridade, modalidade, regime, salário e proveniência |
| Agendamento e workers assíncronos | OCR/IA e monitores ainda compartilham o processo web; workers separados e limites distribuídos já estão no P2 | **P2.4**; incluir scheduler, filas, concorrência por fonte, backoff e timeout. Não é requisito para o primeiro ciclo pago |
| Saúde dos conectores e alerta abaixo de 80% | UptimeRobot cobre a saúde do serviço, mas não mede sucesso por fonte/conector | **P2.5 novo**; registrar tentativas, sucesso, bloqueios, latência e parsing inválido, com alerta e pausa automática quando a qualidade cair |
| Anti-bot, browser stealth e proxies rotativos | Não existe atualmente | **P2.6 condicional**; manter na fila como capacidade opcional para fontes autorizadas, depois de licença/Termos/robots e necessidade comprovada. Usar limites, identidade transparente, sem contornar CAPTCHA ou bloqueios deliberados, com desligamento por fonte |
| Rate limit e proteção da origem | Rate limiting da aplicação está no P0; falta orçamento específico por fonte para uma coleta futura | **P2.3/P2.4**; aplicar intervalos, User-Agent identificável, backoff e teto por domínio antes de qualquer coleta agendada |
| Legalidade, robots/Termos, atribuição e retenção do dado bruto | A LGPD e a retenção de artefatos já estão mapeadas, mas ainda não há um registro de fonte com base legal, licença, robots, atribuição e prazo de descarte | **P1.20 novo, antes de P2.1/P2.2**; aprovar cada fonte, registrar proveniência e limitar a retenção do HTML/texto bruto |

O desenho aprovado para a fila é, portanto: **P1.20** (legalidade e proveniência) → **P2.1** (APIs autorizadas) → **P2.2** (piloto ATS público) → **P2.3/P2.4** (pipeline, limites, scheduler e workers) → **P2.5** (observabilidade por fonte) → **P2.6** (proxies/stealth condicionados) → expansão gradual. Essa capacidade permanece planejada, mas só será ativada para fontes autorizadas e após os critérios legais, operacionais e de desligamento serem atendidos.

### Auditoria da proposta de DDL e worker de ingestão — 18/09/2026

Esta proposta foi tratada como desenho técnico para a fila, não como autorização para criar a tabela ou iniciar coletas. O modelo atual usa `jobs` para oportunidades do usuário e `queue_items` para a fila de decisão; ambos já têm proprietário, campos estruturados, sanitização e RLS. A proposta de `job_listings` representa um catálogo externo compartilhado e só deve ser adotada se essa distinção for necessária.

| Requisito técnico | O que já existe | Classificação e forma correta de completar |
| --- | --- | --- |
| Tabela `job_listings` com título, empresa, local, modalidade, regime, salário, URL, descrição e status | Não existe uma tabela separada; os campos equivalentes já estão em `jobs`/`queue_items`, com `contract_type`, `modality`, limites salariais, URL e descrição | **P2.3**; primeiro decidir se haverá catálogo compartilhado. Se a ingestão continuar por usuário, reutilizar os modelos existentes. Se houver catálogo global, criar uma tabela própria com `visibility`, `source_url/canonical_url`, proveniência, `first_seen_at/last_seen_at` e retenção, sem duplicar dados por acidente |
| Índice único `(source_name, external_id)` | `Job.external_id` é único e a fila usa `dedup_hash` por proprietário; não há chave composta por fonte e identificador externo | **P2.3 novo**; o catálogo global deve usar essa chave composta (ou constraint equivalente), normalização de fonte e tratamento explícito de identificador ausente |
| Valores controlados para `work_mode`, `contract_type` e `status` | O parser já normaliza modalidade, CLT/PJ/MEI e outros regimes, com confiança por campo; a fila registra a decisão e o status operacional | **P1.9/P2.3**; manter enumeração/validação no banco e separar `active/expired` da decisão da fila e do status da candidatura |
| RLS com leitura pública/autenticada e escrita só por serviço/admin | RLS está ativo nas 11 tabelas atuais, com políticas owner-scoped; não existe política para um catálogo público | **P0.1/P0.6 como gates de aceite da nova tabela, dentro da entrega P2.3**; preferir leitura autenticada ou uma view pública mínima. Escrita deve ocorrer apenas no backend/worker com segredo server-side; nunca expor chave de serviço no cliente |
| Worker que busca ATS/API pública | O `job_source_fetcher` lê JSON-LD de uma URL pública fornecida pelo usuário; Gmail/Outlook e intake funcionam no processo web | **P2.2/P2.4**; criar adaptadores por fonte e worker agendado somente após P1.20 e aprovação da fonte |
| Sanitização e extração de palavras-chave | `sanitize_untrusted_text`, parser de título/empresa e classificadores de modalidade, regime e salário já existem; casos de alerta e HTML têm regressão | **P1.9/P1.3 parcialmente coberto**; o worker deve reutilizar o mesmo parser central, sem uma segunda regra divergente |
| Upsert por `(source_name, external_id)` | `queue_service.enqueue` faz deduplicação por URL/hash e incrementa reaparições, mas não faz upsert de um catálogo por chave externa; o `external_id` de jobs promovidos é gerado de outra forma | **P2.3 novo**; implementar upsert transacional na constraint composta, atualizar `updated_at/last_seen_at`, marcar expiração e preservar histórico de origem |
| DDL/migração pronta para aplicação | Não há migração `job_listings` nem contrato de fonte ativo | **Não implementar agora**; elaborar a migração somente junto do primeiro conector aprovado, incluindo índices, constraints, RLS, teste IDOR e estratégia de rollback |

Decisão registrada: não criar `job_listings` apenas para satisfazer o formato sugerido. A ordem é **P1.20** (legalidade/proveniência) → **P2.1/P2.2** (fonte autorizada e piloto) → **P2.3** (modelo, constraint composta, upsert, parser reutilizado e deduplicação) → **P2.4** (worker/scheduler) → **P2.5** (saúde por fonte). Ao introduzir a tabela, a validação de RLS/IDOR e a revisão de segredos voltam a ser obrigatórias antes de publicar.


## Próximas prioridades

### P0 — antes de aceitar usuários pagantes

1. **IDOR/RLS real — concluído para as rotas atuais:** duas sessões reais foram separadas no navegador conectado; a conta B exibiu zero vagas/candidaturas, a abertura direta de `/dashboard?application_id=15` não revelou a candidatura da conta A e as rotas de exportação/download cruzadas retornaram 404 sem conteúdo pessoal. O download exige compra `PAID` vinculada à candidatura exata. Manter a regressão ao criar novas rotas.
2. **Uploads e arquivos — validação parcial:** PDF falso rejeitado e PDF válido reconhecido no preview sem salvar; rotas de download confinam o caminho ao diretório privado. O feedback global deixou de descartar respostas HTTP de erro, permitindo que a tela mostre a mensagem segura e específica do validador. Ainda conferir limpeza de temporários em **P0.2**.
3. **MFA — enrollment real concluído e opcionalidade confirmada:** uma conta sem fator acessou normalmente a área autenticada; numa segunda conta real, o enrollment TOTP e a confirmação do código foram concluídos. A interface agora consulta o status real e oferece desativação com confirmação. O login da conta com TOTP ativo não pediu código porque `MFA_LOGIN_ENFORCE=false`, comportamento coberto por regressão automatizada; challenge com código real, recuperação e expiração só devem ser exercitados se a exigência global for ativada em uma janela controlada.
4. **E-mail confirmado — configuração conferida:** o Supabase mostra `Confirm email` ligado e Email habilitado; permanece somente o teste operacional de recebimento/reenvio em mais de um provedor.
5. **Webhook Mercado Pago — código e configuração publicados:** endpoint de produção, evento Pagamentos, `MERCADOPAGO_ACCESS_TOKEN` e `MERCADOPAGO_WEBHOOK_SECRET` estão ativos; o código rejeita valor divergente e moeda diferente de BRL, exige HMAC/replay/idempotência, retorna 503 se o Access Token faltar e 401 para assinatura inválida. A validação externa pós-deploy retornou `401 Webhook Mercado Pago não autorizado.` para uma entrega sem assinatura. Falta replay/checkout controlado.
6. **Segredos, menor privilégio e TLS — concluído para o ambiente atual:** painel Supabase/Render sem chave mestra exposta, scanner do código versionado sem padrões de segredo, `Enforce SSL` ativo e aplicação forçando `sslmode=require`. Repetir a auditoria somente quando novas integrações forem adicionadas.
7. **CSP e superfícies de renderização — concluído:** scripts e elementos `<style>` usam nonce por resposta, todos os templates ativos foram migrados de atributos `style` para classes, a exceção `style-src-attr unsafe-inline` foi removida e o dashboard/rotas legais retornaram CSP endurecido em produção.
8. **Erros públicos — validado:** handlers globais e rotas sensíveis retornam mensagens estáveis; checagem externa sem sessão em `/applications/1`, `/preferences` e `/billing/document-export` retornou 401 sem stack trace.
9. **Rate limiting — código local concluído:** validar os limites publicados e configurar proteção distribuída na borda antes de múltiplas instâncias.
10. **Senhas comprometidas — código concluído, configuração externa pendente:** o teste k-anonimizado está no código e a variável do Render existe; o Security Advisor do Supabase ainda indica `Leaked Password Protection Disabled`, que deve ser ativado no painel e retestado.
11. **Backup e recuperação — automação preparada:** `scripts/backup_supabase.py` usa `DATABASE_URL` via ambiente, valida o dump e gera checksum/manifesto privado. O check real confirmou que faltam `pg_dump` e `pg_restore`; depois da instalação, executar/agendar o backup e testar a restauração isolada conforme `DISASTER_RECOVERY.md`.
12. **Acessibilidade de modais — concluído:** em produção, os modais “Captar vaga” e “Preferências”, a tela de Segurança e o drawer de candidatura abriram com foco inicial, fecharam com `Esc`, mantiveram o ciclo de Tab dentro da superfície e devolveram o foco ao disparador. O commit `8cc11fa` foi publicado e validado no Render.
13. **Páginas legais públicas — validado:** `/termos` e `/privacidade` retornaram 200 sem sessão em produção, antes do cadastro, com headers de segurança ativos.

### P1 — resultado, proteção, LGPD, IA e monetização

1. Fechar o loop de resultado: **entregue e validado em produção** em `/applications/metrics` e em `Minhas candidaturas`, com escopo por usuário, segmentação por origem/canal, registro de retorno externo e vínculo do envio à versão de currículo/carta. A interface mostra o funil em `—` enquanto não há dados e só apresenta melhor canal/versão após cinco envios na mesma amostra. Falta acumular dados reais antes de qualquer promessa de melhoria de conversão.
2. Transformar proteção contra golpe em etapa explícita de risco: **entregue no código**. Faixa, score e evidências acompanham a candidatura; risco alto não libera o avanço pelo painel e risco duvidoso pede confirmação do usuário, registrada na linha do tempo. Falta ampliar a cobertura por origem e validar em produção.
3. Formalizar heurísticas de RH brasileiro para triagem, ATS, pretensão salarial, regime e vaga fantasma; **a base já existe em `decision_engine`, `job_health` e no parser de captura**, com motivos explicáveis e testes parciais. Alertas Gmail agrupados sem vagas individuais agora são descartados como resumo, evitando filas artificiais; links de LinkedIn, Indeed, Gupy, Glassdoor e Jobbol são reconhecidos, e a plataforma detectada no alerta passa a ser a origem preservada da vaga, em vez de ficar genérica como Gmail/Outlook. Falta consolidar uma versão própria das heurísticas e ampliar casos por provedor antes de marcar concluído.
4. Criar o copiloto de entrevistas baseado nos gaps: **primeira versão entregue** em `/api/interviews/prep/{app_id}` e no detalhe da candidatura, com perguntas por gap, pontos fortes e orientação para responder apenas com fatos comprovados; avaliação de respostas pela IA continua como segunda camada.
5. Implementar o acompanhamento da zona morta: **primeira versão entregue** em `/api/applications/followups` e em `Minhas candidaturas`, identificando candidaturas sem retorno há 7 dias e preparando uma mensagem para revisão; envio e registro do retorno continuam manuais.
6. Implementar no mesmo sprint a exportação/portabilidade e a exclusão definitiva da conta, com confirmação forte, remoção de dados relacionados e política de retenção. **A exportação JSON owner-scoped já está disponível na área de Segurança; exclusão definitiva e expurgo em Storage continuam pendentes.**
7. **Consentimento versionado entregue:** o cadastro exige os dois aceites, registra `terms_version`, `privacy_version` e `consented_at` no metadata enviado ao Supabase Auth; uma trilha imutável administrativa continua opcional.
8. **Primeira camada entregue:** expurgo periódico de documentos gerados no armazenamento privado, com prazo configurável por `DOCUMENT_RETENTION_DAYS` e intervalo por `DOCUMENT_CLEANUP_INTERVAL_SECONDS`; expurgo de Storage/prints/rascunhos depende da adoção de bucket e de registros persistidos para esses artefatos.
9. Ampliar a fronteira de dados não confiáveis para todos os prompts de vagas, OCR, Gmail e PDFs e adicionar casos hostis específicos por origem; o avaliador de entrevistas já está coberto.
10. **Persistência estruturada entregue:** parser de intake classifica CLT/PJ/MEI/estágio/temporário/freelance, retorna confiança de regime, modalidade e salário, grava esses campos na fila e na vaga promovida e guarda os limites salariais oferecidos separados das preferências do candidato.
11. **Recibo pós-pagamento implementado:** checkout grava o destinatário e o webhook Mercado Pago envia comprovante SMTP uma única vez após a transição idempotente para `PAID`; falta apenas configurar/testar o SMTP transacional em produção.
12. Finalizar os textos legais com responsável, canal de contato, retenção e subprocessadores.
13. **Entregue:** sincronizar o card de onboarding com o perfil e as preferências reais, escondendo-o quando concluído e ajustando o CTA quando só o perfil estiver preenchido.
14. **Logout entregue no cabeçalho global:** subpáginas autenticadas agora exibem `Sair` por formulário POST; links legais continuam nas páginas públicas e no cadastro.
15. **Skeleton e proteção do formulário entregues:** o drawer de candidatura usa blocos animados durante a abertura, preservando textos para leitores de tela; `Limpar formulário` agora é uma ação neutra e confirma a perda quando existe rascunho ou prévia. O Banco de vagas foi reaberto em produção e exibiu o estado vazio/contadores normalmente, sem reproduzir o crash.
16. **Entregue:** landing explicita downloads avulsos de R$ 9,90 e inclui FAQ sobre candidatura manual, compatibilidade ATS e cancelamento conforme checkout; nenhuma prova social numérica foi inventada.
17. **UX de primeiro acesso e polimento final — entrega parcial publicada:** o dashboard agora oferece um tour guiado dispensável em três passos, com estado persistido no navegador e ações para currículos, preferências e captação. Também recebeu hover nos botões principais, pulso do status conectado, feedback de processamento na importação do currículo e respeito a `prefers-reduced-motion`. A tela de Currículos passou a agrupar o resultado do OCR por experiências, competências, formação e idiomas, o estúdio mostra progresso com spinner e `aria-busy` ao gerar a prévia, e o favicon `AC` foi publicado no shell público/autenticado; ainda faltam estados de progresso mais completos nas demais telas e a revisão final das mensagens de recuperação.
18. **Suporte e ajuda contextual — primeira entrega publicada:** `/ajuda` é uma central pública, acessível antes do login e também pelo menu de Ações do dashboard, com respostas sobre formatos, candidatura manual, privacidade, Mercado Pago, arquivos recusados e preferências. Faltam apenas um widget/canal de atendimento real e medir as dúvidas mais frequentes para evoluir a FAQ.
19. **E-mails de ciclo de vida — preparação publicada:** as preferências de frequência (`diário`, `imediato`, `semanal` ou `nenhum`) e os tipos de aviso para entrevistas, follow-up e expiração agora são persistidos junto às preferências da conta. A duplicidade antiga de controles foi removida e nenhum canal de suporte fictício é exibido. Depois de configurar o SMTP de produção em **P1.10**, adicionar boas-vindas, lembretes de candidaturas sem retorno e notificações de mudança de etapa, respeitando essas escolhas e sem envio automático de candidatura.
20. **Legalidade e proveniência de fontes de vagas — novo item de preparação:** antes de adicionar APIs, ATS ou qualquer coleta agendada, manter uma allowlist com Termos/robots/licença, base legal, atribuição, limites por domínio, origem do registro e prazo para apagar conteúdo bruto. Fontes bloqueadas ou sem autorização ficam fora; este gate antecede o P2 de escala.

### Próximo ciclo prático já classificado

1. **Gate de e-mail confirmado:** já implementado no backend e conferido no Supabase (Email habilitado e `Confirm email` ligado); falta somente o recebimento/reenvio operacional em mais de um provedor. Não é uma nova implementação P0.
2. **Idempotência de pagamentos:** permanece dentro do **P0.5**, junto da assinatura dos webhooks e da exposição pública correta das rotas. A chave deve registrar `order_nsu` e `payment_id` e permitir apenas uma transição válida para `PAID`.
3. **Expurgo automático de uploads:** permanece em **P1.8**, depois da validação do armazenamento privado; a rotina deve cobrir temporários, prints e rascunhos abandonados com prazo configurável de 30/60 dias.

### P2 — escala e diferenciação

1. **P2.1 — APIs autorizadas de vagas:** avaliar e integrar agregadores/parceiros somente após o gate P1.20, com licença, cobertura, custo, limites e atribuição documentados.
2. **P2.2 — Piloto de ATS públicos:** começar com duas ou três fontes públicas estáveis, como Gupy e portais de carreira, usando adaptadores pequenos e desligáveis; não iniciar por LinkedIn/Catho protegidos.
3. **P2.3 — Pipeline e orçamento por fonte:** consolidar fetcher, parser, deduplicador, enriquecedor e proveniência, com `external_id`/URL canônica/fingerprint, rate limit, backoff e limites de conteúdo.
4. **P2.4 — Workers e agendamento:** separar Gmail/Outlook, OCR/IA/documentos e ingestão de fontes em workers com filas, timeout, concorrência distribuída e retry controlado.
5. **P2.5 — Saúde dos conectores:** medir sucesso de busca, bloqueio, latência, parse válido e duplicidade por fonte; pausar e alertar quando a taxa cair abaixo do limite definido (referência inicial: 80%).
6. **P2.6 — Proxies e browser stealth condicionados:** avaliar rotação de saída e automação compatível somente para fontes autorizadas, com orçamento por domínio, limites de requisição, auditoria, respeito a robots/Termos e desligamento quando houver bloqueio ou queda de qualidade. Não contornar CAPTCHA nem controles de acesso.
7. Configurar domínio próprio, DNS autoritativo redundante e recuperação operacional; quando o domínio definitivo existir, avaliar proxy da Cloudflare para filtrar tráfego L7 antes do Render.
8. Adicionar Kanban de candidaturas e exportação CSV/Excel/JSON.
9. Criar extensão de navegador para captação autorizada.
10. Criar painel administrativo para acompanhar a operação e as métricas já instrumentadas.
11. Adicionar aprendizado baseado nos resultados das candidaturas depois que houver volume e atribuição confiáveis.

## Validações recentes

- Compilação de `app/auth.py`, `app/main.py` e `app/security.py` aprovada.
- 25 testes de autenticação e controles de segurança aprovados, incluindo cadastro/login/callback pendentes e redirecionamento de contas não confirmadas.
- Cabeçalhos de segurança confirmados no endpoint público `/health`.
- Deploy `e84fd60` confirmado como ativo no Render.
- Health check do Render e monitor externo UptimeRobot fazem parte da operação; credenciais e IDs dos monitores não são documentados por segurança.
- A suíte completa foi reexecutada após a liberação pública das páginas legais, a remoção do fallback de pagamento legado, o CSP endurecido, o vínculo transacional dos exports, o fail-closed do webhook, a preservação de respostas HTTP no feedback global, a rotina segura de backup, a proteção do rascunho no estúdio, a atribuição de resultado, a porta de risco antes da candidatura, o filtro de alertas agrupados, a limpeza de assuntos de alerta, a preservação da origem da plataforma e o reconhecimento dos links por provedor: **139 testes aprovados em 4,56 s**, incluindo autenticação, sanitização HTML, normalização de títulos, parser de e-mail, regressão de rotas legais, bloqueio do fallback fora do Mercado Pago, rastreamento de canal/retorno/versão, isolamento da revisão de risco e carregamento dos scripts de segurança. O teste direcionado de RLS/IDOR também passou. A verificação de produção confirmou `/health`, `/termos`, `/privacidade`, `/dashboard`, rejeição 401 do webhook sem assinatura e o diálogo de confirmação ao limpar um formulário preenchido; 11 logins sintéticos acionaram 429 no limite configurado. O registro histórico de 59 testes ficou desatualizado porque novos testes foram adicionados.
- A suíte foi repetida nesta rodada com todas as dependências de `requirements.txt` resolvidas em ambiente isolado: **143 testes passaram, 0 falhas**, incluindo cobertura de desafio MFA trocado, código inválido, status baseado no usuário autenticado, login opcional com fator verificado, exportação publicada, mensagens seguras na fila e callbacks OAuth sem eco de detalhes do provedor.
- Nesta rodada, os testes direcionados de upload, armazenamento privado e OCR passaram (**11 testes**) e a suíte completa permaneceu em **143 testes aprovados, 0 falhas**. O fluxo MFA também passou a verificar automaticamente que os cookies do desafio usam `HttpOnly`, `SameSite=Lax` e expiração de 5 minutos.
- A suíte direcionada do Mercado Pago passou em **12 testes**, cobrindo HMAC com janela de replay, rejeição sem assinatura/token, valor e moeda, transição `PAID` idempotente, replay conflitante, ausência do fallback InfinitePay e recibo sem duplicidade. O checkout e o replay com pagamento real continuam pendentes por dependerem de uma transação controlada no provedor.
- O onboarding guiado do dashboard foi publicado com dispensa persistente, três etapas e ações de atalho; o teste de shell foi ampliado e a suíte completa passou para **144 testes aprovados, 0 falhas**. O JavaScript inline do dashboard também passou na verificação de sintaxe.
- A URL pública `/dashboard` retornou HTTP 200 e já contém o diálogo `guidedOnboardingDialog`, confirmando a propagação do onboarding guiado em produção.
- O polimento visual do dashboard foi validado com a suíte de shell, verificação de sintaxe JavaScript e a suíte completa em **144 testes aprovados, 0 falhas**; transições e o pulso do status são desativados para usuários que preferem movimento reduzido.
- A importação em `/curriculos` passou a indicar processamento com spinner, `aria-busy` e mensagem orientada à etapa; a sintaxe do script, os testes de shell e a suíte completa permaneceram aprovados (**144/144**).
- A Central de Ajuda pública foi publicada em `/ajuda`, incluída na lista de rotas sem autenticação e ligada ao menu de Ações do dashboard; o teste de shell confirma conteúdo sobre formatos, privacidade, pagamentos e recuperação de erros. A suíte completa passou para **145 testes aprovados, 0 falhas**.
- A verificação externa pós-deploy confirmou `/ajuda` com HTTP 200 e conteúdo de formatos, privacidade e pagamentos no Render; a rota continua pública para leitura antes do login.
- O resumo hierárquico da importação de currículo passou nos testes de shell, na verificação de sintaxe JavaScript e na suíte completa: **146 testes aprovados, 0 falhas**.
- O Render marcou o deploy do commit `34c47b4` como **Live**; `/health` continua retornando HTTP 200 após a publicação da tela de Currículos.
- O estúdio de documentos passou a sinalizar a geração assíncrona com botão ocupado, spinner e mensagem orientada; a suíte completa ficou em **147 testes aprovados, 0 falhas** e a sintaxe do script foi validada com `node --check`.
- As preferências de e-mail de ciclo de vida passaram na suíte direcionada e na suíte completa: **149 testes aprovados, 0 falhas**; valores fora da lista são normalizados para `daily` e as escolhas não disparam mensagens sem SMTP configurado.
- A tela publicada de Configurações mostrou os controles de frequência e categorias de aviso no Render após o deploy `bab87b5`; nenhuma mensagem foi enviada durante a validação.
- A correção dos alertas passou em `node --check` e na suíte completa: **150 testes aprovados, 0 falhas**; a validação local confirma que o script não recria controles, mantém o badge crítico separado e não contém `mailto` de suporte não configurado.
- O favicon `AC` foi publicado no shell público, páginas legais e páginas autenticadas; o SVG foi validado como XML, `app/main.py` compilou e a suíte completa passou para **151 testes aprovados, 0 falhas**, incluindo 15 regressões de shell.
- A cobertura de P0.1 foi ampliada para garantir que a exportação de privacidade também exclua compras de outro proprietário; a suíte oficial permaneceu em **143 testes aprovados, 0 falhas**.
- A fila deixou de devolver exceções internas em ações individuais e em lote: erros inesperados agora ficam apenas nos logs e chegam ao cliente como mensagem estável. O commit `9461640` cobre essa fronteira com regressão automatizada; o P0.8 permanece concluído para as rotas revisadas.
- Os callbacks OAuth do Gmail e Outlook agora registram o motivo técnico somente no log e devolvem mensagens públicas estáveis; a suíte cobre que detalhes enviados pelo provedor não chegam ao navegador.
- A exportação JSON foi validada em produção nas duas sessões autenticadas: o botão `Baixar meus dados` iniciou o download com mensagem de estado e cada sessão recebeu apenas o próprio escopo; o commit `9b0211d` publicou o listener que faltava no frontend.
- A API de exportação foi exercitada diretamente no contexto autenticado das duas sessões reais: a conta A recebeu HTTP 200 com apenas seu perfil, 1 vaga, 1 candidatura e 5 compras; a conta B recebeu HTTP 200 com perfil ausente e zero vagas, candidaturas e compras. Em seguida, a conta B tentou baixar o currículo e a carta associados à candidatura da conta A e recebeu HTTP 404 nos dois endpoints, sem conteúdo pessoal. P0.1 fica concluído para as rotas atuais.
- No painel do Render, as variáveis legadas `INFINITEPAY_EXPORT_PRICE_CENTS` e `INFINITEPAY_HANDLE` foram removidas e o novo deploy do commit `69d033d` ficou ativo; Mercado Pago permanece como o único checkout configurado.
- A inspeção do ambiente de produção não encontrou variáveis `SMTP_*`; por isso o recibo pós-pagamento continua implementado no código, mas o envio transacional ainda aguarda a configuração do SMTP no Render (**P1.10**).
- A suíte automatizada em `tests/` foi reexecutada após o endurecimento do CSP, do vínculo transacional dos exports, do fail-closed do webhook, do feedback de upload, da automação de backup, da proteção contra limpeza acidental e da atribuição de resultado: **129 testes aprovados em 5,11 s**, com 6 avisos de depreciação sem falhas. Os scripts legados na raiz continuam fora da suíte porque dependem de servidores locais em 8001/8002.
- O recibo idempotente do Mercado Pago foi validado com SMTP simulado e retry sem duplicação; os testes direcionados de webhook/fila passaram (**13 testes**).
- A comparação salarial passou a usar limites estruturados da vaga quando disponíveis, com fallback para texto legado; Gmail também encaminha esses campos para a fila; a suíte completa ficou em **117 testes aprovados em 5,06 s**, com 6 avisos de depreciação sem falhas.
- A entrega P1.1 de métricas foi validada na suíte completa: **106 testes aprovados em 6,12 s**. O novo cenário confirma isolamento por usuário, contagem de candidaturas enviadas, entrevistas qualificadas e segmentação por origem; a interface de `Minhas candidaturas` exibe o funil sem alterar o fluxo existente.
- A primeira entrega de P1.2 foi validada na suíte completa: **107 testes aprovados em 5,68 s**. A fila passa a expor faixa/score de risco e sinais resumidos de golpe; o motor continua forçando descarte ou revisão conforme a banda, sem liberar automaticamente uma vaga suspeita.
- P1.3 recebeu versionamento explícito das heurísticas brasileiras: decisões manuais e alertas Gmail registram `br-rh-1` junto da versão do motor; a suíte completa permaneceu em **107 testes aprovados**.
- P1.4 recebeu um roteiro inicial de entrevista com escopo por usuário e perguntas derivadas dos gaps; a suíte completa passou para **109 testes aprovados em 9,85 s**.
- P1.5 recebeu o acompanhamento da zona morta com prazo de 7 dias, escopo por usuário e texto de follow-up sem envio automático; a suíte completa passou para **110 testes aprovados em 4,78 s**.
- P1.6 recebeu a primeira entrega de portabilidade: `/api/privacy/export` e botão de download em Segurança exportam perfil, vagas, candidaturas, eventos e pagamentos sem tokens; a suíte completa passou para **111 testes aprovados em 5,23 s**.
- A implantação do ciclo foi conferida no navegador: a landing exibe o FAQ e o preço avulso de R$ 9,90; `/seguranca` exibe exportação JSON e o botão global `Sair` após a propagação do deploy.
- A tela publicada de `Minhas candidaturas` foi conferida: o funil “Entrevistas qualificadas por 100 candidaturas enviadas” aparece com `—` sem amostra suficiente e mantém canal/versão ocultos até cinco envios, sem fabricar conclusão.
- Migração RLS de produção aplicada com `scripts/migrate_rls.py`: 11 tabelas com RLS ativo e uma política por tabela; `document_export_purchases_owner` confirmado como política `ALL`.
- Teste operacional com duas contas: conta A exibiu seus dados e conta B exibiu zero vagas/candidaturas; a tentativa de abrir diretamente `/dashboard?application_id=15` na conta B fechou o drawer sem revelar dados. A API autenticada também confirmou exportação owner-scoped e 404 para os downloads cruzados de currículo/carta. P0.1 fica concluído para as rotas atuais.
- Testes direcionados reexecutados nesta rodada: isolamento/RLS/arquivos cruzados (**3 aprovados**), validação de uploads por assinatura/estrutura (**4 aprovados**), fluxo MFA (**4 aprovados**) e assets estáticos públicos (**2 aprovados**). Essas evidências são locais; as validações externas do P0 continuam separadas por item.
- No avanço do P0.2, armazenamento privado/limpeza e intake de arquivos passaram (**5 testes**); em produção, um PDF falso e um DOCX falso foram rejeitados sem criar currículo. Após os commits `99c6019` e `f75c99c`, a tela passou a exibir somente a mensagem específica `O conteudo do arquivo nao corresponde ao formato informado.` e a região de status ficou acessível, sem o aviso global obsoleto. Nesta rodada, a produção rejeitou uma imagem inválida com HTTP 415 no upload de foto e HTTP 422 no preview de intake, sem persistir dados; a suíte agora também cobre a remoção dos temporários quando o OCR falha (**143 testes aprovados, 0 falhas**). Ainda falta validar uma imagem válida, o armazenamento privado e a limpeza periódica em operação.

## Auditoria do checklist de segurança e operação — 17/09/2026

| Item verificado | Evidência encontrada | Estado e prioridade |
| --- | --- | --- |
| Confirmação de e-mail | Gate no backend, tela pública de confirmação e reenvio limitado; no Supabase Auth, `Confirm email` está ligado, o provedor Email está habilitado, o Site URL aponta para o Render e há um redirect permitido para `/dashboard`; template usa `{{ .ConfirmationURL }}` | Implementado no código e configuração principal conferida; falta recebimento real em mais de um provedor em **P0.4** |
| Cookies e headers | Cookies `HttpOnly`, `Secure` configurável e `SameSite=Lax`; CSP nonceado sem `style-src-attr unsafe-inline`, HSTS, `nosniff`, `DENY` e políticas complementares | Código e header real validados em `/health`, `/termos`, `/privacidade` e `/dashboard` em produção |
| Rate limiting | Limites por IP/conta, testes locais de 429 e validação publicada com 10 respostas 401 e 11ª resposta 429; armazenamento é local ao processo | Proteção distribuída segue em **P0.9** |
| Isolamento/IDOR | Testes locais com dois usuários cobrem listagem, consulta, atualização e downloads; duas contas reais confirmaram a exportação JSON owner-scoped e receberam 404 nos downloads cruzados de currículo/carta | Código, testes locais, RLS e validação real das rotas atuais concluídos; manter a regressão em novas rotas |
| RLS e menor privilégio | Painel do Supabase confirma RLS ativo e uma política `ALL` para cada uma das 11 tabelas, incluindo `document_export_purchases_owner`; a política `applications_owner` exige relação com `jobs.owner_id = auth.uid()`; código cliente usa a chave publicável e o Render não exibe chave mestra | RLS aplicado e isolamento real por ID/exportação/download confirmado nas rotas atuais; não criar nova chave em **P0.6** |
| Segredos e TLS | Scanner do código versionado não encontrou chaves privadas, tokens hardcoded ou `SERVICE_ROLE_KEY`; painel mantém chaves mascaradas, `Enforce SSL` está ativo e o código usa `sslmode=require` | **P0.6 concluído** para o ambiente atual; repetir somente após novas integrações |
| Senhas comprometidas | Consulta k-anonimizada envia apenas o prefixo do hash SHA-1 para o serviço de verificação; `PWNED_PASSWORD_CHECK` aparece no Render sem expor valor; no provedor Email do Supabase, `Prevent use of leaked passwords` está desativado e marcado como disponível apenas no plano Pro+ | Código e Render confirmados; upgrade/configuração nativa do Supabase permanece pendência **P0.10** |
| Uploads | Validador central confirma magic bytes, estrutura e decodificação de fotos; PDF/DOCX conferem assinatura/estrutura | Código e testes locais aprovados; validação operacional em **P0.2** e expurgo externo em **P1.8** |
| Arquivos temporários | OCR remove temporários ao terminar; documentos gerados usam diretório privado `0700` e limpeza periódica por idade; rascunhos/objetos externos ainda não têm rotina própria | Camada local implementada em **P1.8**; expurgo de Storage/rascunhos só após adoção de bucket |
| MFA | Enrollment/status/unenroll e challenge/verify TOTP; login com fator verificado cria desafio temporário quando a exigência está ligada; duas contas reais exibem estados distintos (`enabled=false` e `enabled=true`), o login opcional não interrompe a conta com TOTP e um desafio ausente retornou 401 estável | Código, interface e opcionalidade publicados; login E2E com código real só entra em janela controlada se a exigência global for ativada em **P0.3** |
| Gmail/Outlook | Gmail usa `gmail.readonly`; refresh tokens são cifrados com Fernet; OAuth usa `state` assinado e expirável | Implementado; manter auditoria de configuração do provedor |
| XSS e prompt injection | Sanitizador central remove markup executável antes de persistir/analisar; prompt de entrevistas delimita dados não confiáveis e testes hostis verificam que tags/instruções não escapam | CSP e superfícies ativas endurecidos em **P0.7**; ampliar cobertura por origem permanece em **P1.8** |
| Webhook de pagamento | Rota pública do Mercado Pago valida `x-signature`/`x-request-id` com HMAC e janela de replay; sem Access Token retorna 503 e sem assinatura retorna 401; a validação pós-deploy retornou 401 e as credenciais aparecem mascaradas no Render | Código e configuração publicados; falta replay/checkout controlado em **P0.5** |
| Downloads e exportações | Rotas filtram a candidatura pelo usuário e exigem compra `PAID` do proprietário vinculada ao `application_id`; o checkout cria essa associação, o teste de candidatura sem compra retorna 402 e a exportação/download cruzado foi conferido com duas contas reais | Código, teste local e validação real das rotas atuais concluídos; manter cobertura para novas superfícies |
| Erros e informação interna | Handlers globais cobrem validação e exceções inesperadas; `/health` e IA retornam mensagens estáveis e registram detalhes apenas no log | Código e checagem externa sem sessão aprovados: rotas sensíveis retornaram 401 genérico sem stack trace |
| Tarefas pesadas | OCR, parsing, confirmação e busca externa usam threadpool com timeout total de 30 segundos; monitores ainda rodam no processo web e falta limite distribuído de concorrência/CPU | Código e testes locais aprovados; worker separado e limites distribuídos permanecem em **P2** |
| Backup e recuperação | `DISASTER_RECOVERY.md` cobre restauração isolada, RLS, UptimeRobot e revogação; `scripts/backup_supabase.py` cria e verifica dump customizado com SHA-256 sem expor a URL; o plano Free não inclui backups agendados nem PITR | Código e testes concluídos; faltam PostgreSQL client tools, agendamento e teste real de restauração em **P0.11** |
| SQL injection | Consultas de negócio usam SQLAlchemy com parâmetros; SQL dinâmico encontrado no script de RLS usa apenas nomes de tabelas constantes do próprio código | Coberto na revisão atual; manter regra de não interpolar entrada do usuário |
| SSRF | `job_source_fetcher` rejeita credenciais, resolve DNS, bloqueia IPs não globais, revalida redirecionamentos e limita resposta | Coberto na revisão atual; manter testes de regressão |
| Termos, privacidade e consentimento | Páginas e checkbox existem; o cadastro agora exige os dois aceites e registra versões/data UTC no metadata do usuário | Implementado em **P1.7**; trilha imutável administrativa é melhoria posterior; textos legais em **P1.11** |
| Exportação e exclusão LGPD | Exportação JSON owner-scoped está disponível na área de Segurança; exclusão definitiva, cascata e expurgo de objetos permanecem pendentes | **P1.6 parcialmente entregue** |
| Recibo por e-mail | Envio idempotente está implementado após confirmação do Mercado Pago; falta configurar e testar o SMTP transacional em produção | **P1.10 parcialmente entregue** |
| InfinitePay | Removido do código, do Render e do exemplo de ambiente | Fora do escopo ativo; não validar nem recomendar como provedor |
| UptimeRobot | Monitor externo de disponibilidade/health check já faz parte da operação e está documentado; IDs e alertas ficam no painel externo | Concluído operacionalmente; conferir painel quando houver auditoria, sem recriar configuração |
| Suíte completa | Dependências de `requirements.txt` resolvidas em ambiente isolado; a suíte oficial em `tests/` executou 143 testes sem falhas | **Concluído nesta verificação** |
| Acessibilidade dos modais | Script global registra disparador, foco inicial, retorno de foco, `aria-modal` e ciclo de Tab para `<dialog>` e modal customizado; produção confirmou captação, preferências, Segurança e drawer de candidatura | Validado em produção; foco inicial, `Esc`, retorno ao disparador e ciclo de Tab concluídos |

### Verificação direta do Supabase — 17/09/2026

- Projeto de produção identificado como `agente de candidaturas`, região São Paulo, plano Free; o painel voltou a exibir **Healthy** após o carregamento e o Advisor informou não haver problemas de segurança ou performance.
- Auth: confirmação de e-mail ligada; Site URL `https://agente-de-candidaturas.onrender.com`; redirect permitido para `https://agente-de-candidaturas.onrender.com/dashboard`; template de confirmação usa `{{ .ConfirmationURL }}`; SMTP customizado do Brevo está ativo. O recebimento real do e-mail ainda precisa de teste operacional.
- MFA: TOTP (aplicativo autenticador) habilitado; SMS MFA desabilitado. Isso mantém MFA como opção por conta, de acordo com `MFA_LOGIN_ENFORCE=false` no Render.
- Auth nativo: limites de cadastro/login, refresh, verificação de token e envio de e-mail estão configurados no painel. A proteção contra CAPTCHA está desligada e a opção nativa de bloquear senhas vazadas aparece desabilitada; o aplicativo mantém a checagem k-anonimizada externa em **P0.10**.
- RLS: 11 tabelas do schema `public` aparecem com RLS ativo e uma política de proprietário para o papel `authenticated`. Não alterar nem recriar essas políticas; o próximo teste é tentar acesso cruzado por ID/download com duas contas reais.
- Storage: não há buckets criados no projeto. A aplicação continua usando armazenamento privado local; expurgo de objetos externos só entra quando um bucket for adotado em **P1.8**.
- Chaves: o painel separa chave publicável de chave secreta e mantém os valores mascarados. Não foi criada, revelada, copiada ou alterada nenhuma chave durante a auditoria.
- Banco: `Enforce SSL` está ativo no Supabase e a aplicação reconectou ao painel após o reinício; o código continua forçando `sslmode=require`.
- Security Advisor: após revogar `EXECUTE` de `PUBLIC`, `anon` e `authenticated` na função auxiliar `public.rls_auto_enable()`, a verificação efetiva retornou `false/false` para os dois papéis e os dois avisos de função desapareceram. Resta apenas o aviso nativo de proteção contra senhas vazadas desativada, que permanece em **P0.10** porque o plano atual não oferece esse recurso nativo.
- Backups: o painel confirma que o plano Free não oferece backups diários agendados; PITR exige plano Pro. A rotina externa de dump está pronta e testada sem conexão real, mas **P0.11** permanece aberto até instalar `pg_dump`/`pg_restore`, agendar a execução e validar uma restauração isolada.

### Verificação externa do Render — 18/09/2026

- O deploy `cfb1c74` foi concluído com sucesso. O log do Render registrou `Application startup complete`, health checks `200` e serviço Live; a inicialização não executa mais a reflexão de colunas do PostgreSQL que causava timeout.
- `/health` retornou `200` com banco conectado; `/termos`, `/privacidade` e `/dashboard` retornaram `200` sem stack trace e com CSP nonceado, HSTS e `nosniff`.
- `/webhooks/mercadopago` retornou `401 Webhook Mercado Pago não autorizado.` para uma entrega sem assinatura, confirmando a rejeição pública após o deploy `75a72aa`.
- As rotas `/applications/1`, `/jobs/1`, `/vagas/1`, `/billing/document-export`, `/api/profile` e `/api/preferences` retornaram `401 Login necessario.` sem sessão. Isso confirma a barreira de autenticação, mas não substitui o teste IDOR com duas contas reais em **P0.1**.

### Validação de MFA em conta de teste — 18/09/2026

- A extensão do Chrome foi conectada ao Codex e permitiu controlar uma segunda sessão real, separada da conta A no navegador interno.
- Na conta B, o enrollment TOTP foi concluído na produção: a API gerou o fator, o código de seis dígitos foi verificado e a tela passou a indicar o autenticador como ativo. O MFA continua opcional porque `MFA_LOGIN_ENFORCE=false`.
- A API autenticada confirmou `enabled=true` e fator TOTP verificado na conta B; na conta A, confirmou `enabled=false` sem fatores. Uma chamada sem cookies de desafio ao endpoint de conclusão retornou HTTP 401 com a mensagem estável de desafio expirado, sem promover sessão.
- A conta com TOTP ativo entrou no dashboard sem prompt porque o ambiente mantém `MFA_LOGIN_ENFORCE=false`; o teste automatizado garante que um fator verificado não torna o login obrigatório enquanto essa política estiver desligada.
- A interface de Segurança tinha uma lacuna: após ativar o fator, não consultava `/auth/mfa/status` ao recarregar e não oferecia revogação, embora `DELETE /auth/mfa/{factor_id}` já existisse no backend. O script foi ajustado para carregar o estado real, mostrar erro sem falso “Não configurado” e permitir desativar o autenticador com confirmação.
- Após a primeira publicação, o status ainda consultava uma rota REST de fatores inexistente neste projeto. O backend passou a ler `factors` da resposta autenticada de `/auth/v1/user`, atualizando enrollment, status e login opcional sem depender do schema REST do banco; o deploy `de55ee4` foi confirmado como **Live** e a conta B exibiu `Ativo` com `Desativar autenticador`.
- Ainda falta o teste de ponta a ponta do desafio durante um novo login, incluindo expiração, código inválido, limite de tentativas, recuperação e revogação efetiva. Esse restante continua em **P0.3**; não reativar a exigência global antes dele.

### Validação de acessibilidade do drawer — 18/09/2026

- O deploy `8cc11fa` foi confirmado como **Deployed** no Render.
- Em produção, a abertura da candidatura colocou o foco no botão `Fechar`; `Esc` fechou o drawer e devolveu o foco à linha que o abriu.
- Após 18 avanços de `Tab`, o foco permaneceu dentro dos controles do drawer, sem escapar para a navegação ou para o conteúdo atrás do overlay.

## Variáveis e segredos

Os valores reais não pertencem a este documento. Devem permanecer somente no painel do Render ou no ambiente local protegido:

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`;
- `COOKIE_SECURE`, `AUTH_REQUIRED`, `APP_BASE_URL`;
- `MFA_LOGIN_ENFORCE` (temporariamente desabilitado no Render para destravar o acesso; o MFA por conta e a validação TOTP em produção continuam em **P0.3** antes de reativar a exigência global);
- `PWNED_PASSWORD_CHECK` (habilitado no Render para bloquear senhas presentes em vazamentos conhecidos);
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_STATE_SECRET`;
- `TOKEN_ENCRYPTION_KEY`;
- `GEMINI_API_KEY`;
- `MERCADOPAGO_WEBHOOK_SECRET` e credenciais do Mercado Pago.

## Histórico recente de entregas

| Commit | Entrega |
| --- | --- |
| `8dd0f36` | Gmail ignora alertas agrupados sem vagas individuais, evitando criar oportunidades artificiais; testes 132/132 |
| `9e01036` | Proteção contra golpes antes da candidatura: preserva sinais de risco, bloqueia risco alto e exige revisão auditável para vaga duvidosa; testes 131/131 |
| `fe2d92f` | Atribuição de candidatura por canal, retorno externo e versão de currículo/carta; proteção de amostra mínima no painel |
| `61a4ab1` | Regressão do painel para os controles de canal e retorno; suíte 129/129 |
| `4cddd50` | Ação neutra `Limpar formulário` com confirmação contra perda acidental, validada em produção; testes 128/128 |
| `2315bfc` | Remoção do segundo cabeçalho da tela de Segurança, validada em produção |
| `0f9f6e2` | Rotina segura e verificável de backup externo do Supabase Free |
| `f75c99c` | Feedback de upload acessível, sem status global obsoleto |
| `ca85397` | Remoção do aviso HTTP genérico duplicado |
| `99c6019` | Preservação da mensagem específica de validação de upload e correção visual da área de importação |
| `75a72aa` | Validação pós-deploy do webhook Mercado Pago e registro de configuração ativa |
| `f75f07f` | Webhook Mercado Pago fail-closed para Access Token ausente e assinatura inválida; testes 123/123 |
| `d7cf3c1` | Registro da limitação do plano Free para proteção nativa contra senhas vazadas |
| `3c6862e` | Validação de produção do Banco de vagas sem crash |
| `12e9c65` | Confirmação direta no Supabase de Email habilitado e `Confirm email` ativo |
| `579ee2c` | CSP endurecido sem `style-src-attr unsafe-inline` |
| `e293c8c` | Exports vinculados à candidatura e compra paga exata |
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

Toda nova recomendação deve ser comparada com esta fila antes de virar tarefa. Se já existir, atualiza-se o item correspondente; se for nova, entra na prioridade que corresponde ao risco e à dependência. Uma etapa só sai da fila depois de código, teste e validação operacional compatíveis com o seu status.

### Protocolo para novas mensagens

Qualquer nova mensagem, print, documento ou sugestão relacionada ao produto passa primeiro por uma análise de impacto. O fluxo é:

1. identificar o que já existe e o que já foi concluído;
2. verificar se a sugestão duplica, altera ou bloqueia uma tarefa existente;
3. classificar a entrada em P0, P1 ou P2 conforme risco, dependência e valor;
4. atualizar esta fila e o status correspondente;
5. continuar pelo próximo item executável da fila, sem interromper o restante do plano para tratar somente a última mensagem.

Quando a etapa depender de uma conta, credencial, painel externo ou validação manual, ela permanece marcada como bloqueio externo e a solicitação de acesso é feita apenas nesse ponto.
