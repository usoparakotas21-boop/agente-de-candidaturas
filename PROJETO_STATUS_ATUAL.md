# Agente de Candidaturas — status atual

**Atualizado em:** 17/09/2026  
**Versão declarada da API:** 0.24.0  
**Commit publicado:** `a2821fe` — `Allow public access to legal pages`
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

- Checkout de exportação integrado com Mercado Pago, que é o único provedor de pagamento no escopo ativo.
- Rotas e variáveis antigas de InfinitePay permanecem apenas como legado técnico e não fazem parte do fluxo de produção nem do critério de aceite.
- Webhooks consultam o status no provedor antes de liberar a exportação.
- Compras são associadas ao usuário e ao `order_nsu`.
- `receipt_url` é persistida quando o provedor informa o endereço do recibo.
- Ainda não existe envio automático de comprovante por e-mail.

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

- O gate de confirmação de e-mail está implementado; falta validar em produção as configurações de confirmação, os templates/redirecionamentos do Supabase e o fluxo em mais de um provedor de e-mail.
- InfinitePay está fora do escopo ativo; não deve gerar novas recomendações ou critérios de aceite.
- O card de onboarding aparece de forma estática no dashboard e ainda não acompanha sempre o estado real de `/profile` e `/preferences`.
- Logout existe, mas falta torná-lo mais óbvio no cabeçalho global em todas as telas.
- Rate limiting é local ao processo; ainda falta proteção distribuída no edge quando houver múltiplas instâncias.
- CSP usa `unsafe-inline` porque as telas atuais contêm scripts e estilos inline; a política precisa ser endurecida depois da migração para nonces ou arquivos externos.
- Os testes locais de IDOR entre dois usuários estão implementados e aprovados; ainda falta executar a mesma prova com duas contas reais contra o PostgreSQL/Supabase de produção.
- O script `scripts/migrate_rls.py` cobre as 11 tabelas do modelo, incluindo `document_export_purchases`. A migração foi aplicada no PostgreSQL de produção e a consulta somente leitura confirmou RLS habilitado e uma política em cada tabela.
- A aplicação usa `SUPABASE_PUBLISHABLE_KEY`, não há `SERVICE_ROLE_KEY` no código, no `render.yaml` ou na lista de variáveis exibida no Render; ainda falta a conferência equivalente no painel do Supabase e a verificação da conexão efetiva de produção.
- A validação central de upload já confere extensão, tamanho, magic bytes e estrutura/decodificação; a validação em produção continua no P0.2.
- Processamentos temporários são removidos no fluxo e documentos gerados ficam fora da raiz em diretório `0700`; falta ligar expurgo de rascunhos/objetos do Storage.
- A sanitização central de texto já cobre captura, e-mail/OCR, confirmação e análise; superfícies de renderização restantes continuam na revisão do P0.7.
- O avaliador da Gemini delimita pergunta, contexto e resposta como dados não confiáveis, sanitiza o conteúdo e instrui o modelo a ignorar comandos embutidos; testes hostis cobrem essa fronteira.
- A verificação contra senhas comprometidas usa k-anonimato (somente prefixo de 5 caracteres do SHA-1, nunca a senha ou o hash completo) e `PWNED_PASSWORD_CHECK` está presente no Render. O fluxo MFA de login, desafio, revogação e expiração já está implementado, aguardando validação real do Supabase.
- A rota do Mercado Pago é pública, consulta o provedor e faz transição idempotente para `PAID`; falta configurar o segredo, validar HMAC e executar replay controlado em produção.
- As rotas de download verificam o `owner_id` da candidatura e exigem uma compra `PAID` para o usuário, mas ainda falta amarrar a autorização a uma transação/exportação específica e validar esse cenário com dois usuários.
- O normalizador de `DATABASE_URL` converte PostgreSQL para `psycopg` e força `sslmode=require` quando ausente; falta confirmar no Render a URL efetiva e a negociação TLS.
- Handlers globais já padronizam erros públicos e mantêm detalhes nos logs; falta revisar endpoints operacionais legados.
- OCR, parsing, confirmação e busca externa já saem do loop HTTP e têm timeout total de 30 segundos; falta separar monitores/IA em worker próprio e impor limites distribuídos de concorrência/CPU.
- O runbook `DISASTER_RECOVERY.md` documenta backup, restauração isolada e revogação/rotação emergencial; ainda falta confirmar os backups do projeto Supabase, executar o teste real e registrar a evidência fora do Git.
- Modalidade, salário e localização têm parsing parcial; regime CLT, PJ, MEI, estágio e não informado ainda não são campos estruturados completos.
- Falta separar claramente salário oferecido de pretensão salarial do candidato.
- Falta envio de recibo por e-mail após pagamento confirmado.
- Falta retenção configurável e expurgo automático após 30/60 dias para temporários, prints e rascunhos abandonados.
- Falta exportação/portabilidade e exclusão definitiva da conta no mesmo fluxo LGPD.
- Falta registrar versão e data do consentimento aceito pelo usuário.
- O monitor Gmail/Outlook ainda roda junto do processo web; falta worker distribuído independente.
- O monitor UptimeRobot não é controlado pelo código; alterações de intervalo, URL ou alertas precisam ser feitas no painel do UptimeRobot.
- A busca de páginas públicas já bloqueia hosts e IPs não globais, valida cada redirecionamento e limita o corpo recebido; a proteção contra SSRF precisa permanecer coberta por testes de regressão.
- O OCR usa arquivos temporários e os remove em `finally`; documentos gerados usam diretório privado e retenção configurável. Expurgo de Storage/rascunhos ainda falta.
- Não existe painel administrativo multiusuário.
- Não existe aprendizado baseado em entrevistas, aprovações e reprovações.
- O produto ainda não fecha o ciclo de resultado: não há atribuição confiável entre versão do currículo, canal, candidatura e entrevista qualificada.
- O avaliador de entrevistas já existe, mas ainda não transforma os gaps da vaga em um roteiro de preparação contextualizado para cada candidatura.
- Não há acompanhamento automático da zona morta após a candidatura, com prazo, lembrete e sugestão de follow-up apropriado ao canal.
- A proteção contra golpes já aparece como sinal na análise, mas ainda não é uma porta de entrada claramente posicionada nem um fluxo completo de risco antes da candidatura.
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
| Foco, `aria-modal` e retorno de foco dos modais | Código feito | Validação manual com teclado permanece em **P0.12** |
| Verificação de e-mail, headers e rate limiting | Código principal feito | Validações de produção ficam em **P0.4**, **P0.7** e **P0.9**; rate limiting distribuído só é necessário antes de múltiplas instâncias |
| IDOR e RLS obrigatório | Parcialmente feito | Migração RLS e testes locais estão feitos; prova com duas contas reais continua em **P0.1** |
| `SERVICE_ROLE_KEY` fora do cliente e menor privilégio | Revisão de código feita | Conferir painel do Supabase e conexão TLS em **P0.6**; não há motivo para adicionar essa chave ao app |
| Magic bytes, MIME real, diretório privado e parsing isolado | Parcialmente feito | Validador e diretório privado estão feitos; ensaio real e confirmação de isolamento ficam em **P0.2** |
| Gmail `readonly` e tokens criptografados | Feito no código | Manter auditoria de escopos e revogação; não criar escopos maiores |
| Sanitização/XSS e prompt injection | Parcialmente feito | Sanitização central e fronteira do prompt de entrevistas estão feitas; ampliar casos por origem em **P1.8** e concluir `style-src` em **P0.7** |
| Assinatura, replay e idempotência de webhook | Parcialmente feito | Mercado Pago tem HMAC no código, mas falta segredo e replay real. Tudo fica em **P0.5** |
| Mensagens de erro genéricas | Feito no código | Apenas revisar endpoints legados em **P0.8**; não expor stack trace ou detalhes de provedor |
| OCR/IA assíncronos e timeout de 30 segundos | Proteção principal feita | Worker separado é escala operacional e fica em **P2**; não deve bloquear o primeiro ciclo pago enquanto os timeouts forem aplicados |
| Backup diário, restauração e revogação | Runbook feito | Evidência de backup e teste real permanecem em **P0.11** |
| Cloudflare, DNS redundante e DDoS | Condicional | Só entram em **P2** quando houver domínio próprio e necessidade de borda; Render e UptimeRobot já cobrem a operação atual |
| Termos, privacidade, consentimento, portabilidade e exclusão | Parcialmente feito | Páginas e aceite existem; consentimento versionado é **P1.7**, exportação/exclusão no mesmo fluxo é **P1.6**, textos legais em **P1.11** |
| Acesso anônimo às páginas legais | Corrigido: `/termos` e `/privacidade` (com barra final) foram adicionadas à lista pública do middleware e testadas sem sessão | P0 concluído no código; validar as URLs públicas no deploy |
| Retenção de 30/60 dias | Necessário, mas não é gate de pagamento | Diretório privado e limpeza local já existem; expurgo de Storage, prints e rascunhos fica em **P1.8**, com prazo configurável e registro da exclusão |
| Comprovante por e-mail | Faz sentido depois do checkout | **P1.10**, somente após webhook assinado, idempotente e pagamento confirmado |
| CLT/PJ/MEI, modalidade, salário e pretensão | Necessário para análise brasileira | **P1.9**; separar salário oferecido de pretensão do candidato e exibir confiança da extração |
| Métrica de entrevistas por 100 candidaturas | Divisor de águas | **P1.1**, antes de prometer aumento de conversão; exige atribuição por canal e versão do documento |
| Proteção contra golpes | Deve ser destaque de produto | **P1.2**; transformar sinais atuais em decisão de risco visível antes da candidatura |
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
| Alertas “27 vagas abertas...” salvos como uma vaga | O splitter atual já separa blocos por URLs/títulos detectáveis, mas não decompõe todo resumo sem links individuais | P1.3, junto das heurísticas de parsing por provedor; não duplicar como tarefa P0 |
| Cards, badges, paginação, busca e estado vazio da fila | Já implementados; a incoerência textual entre “Aguardando revisão” e “Capturar” é nomenclatura de produto a revisar junto das heurísticas | P1.3 se houver mudança de decisão; sem novo P0 |
| `/vagas` exibe erro sem ação | Corrigido com botão local `Tentar novamente`, sem exigir F5; backend já retorna mensagem pública estável | P1.15 concluído no código; testar no navegador durante a validação visual |
| Modal abre com textos repetidos “Carregando...” | Ainda não há skeleton screen; trocar por blocos de carregamento é melhoria de percepção, sem impacto de segurança | P1.15 |
| Cabeçalho escuro duplicado em Currículos/Configurações | Removido o cabeçalho interno; permanece a navegação global adicionada pelo shell | P1.15 concluído no código |
| Botões Aprovar/Recusar genéricos e subtítulo de alerta repetido | Decisão e status são dados distintos; renomear ações e reduzir o subtítulo exige revisar copy e transições | P1.3, junto do modelo de decisão; não implementar só por aparência |
| Botão Limpar próximo da ação principal | Ação continua disponível, mas deve virar link/ação neutra com confirmação quando houver conteúdo | P1.15 |
| Placeholders de salário ausentes | Adicionados exemplos `Ex.: 8.000` e `Ex.: 12.000` nas configurações | P1.9 concluído no código |
| R$ 9,90 avulso, FAQ e prova social na landing | A linha do avulso pode ser adicionada com o preço real; FAQ é copy útil; números de prova social só entram quando vierem de métricas observadas | P1.16; métricas de conversão permanecem P1.1 |


## Próximas prioridades

### P0 — antes de aceitar usuários pagantes

1. **IDOR/RLS real — bloqueado por validação externa:** usar duas contas no Supabase/PostgreSQL de produção e comprovar acesso negado a vagas, candidaturas e exportações de outra conta. RLS e testes locais já estão prontos.
2. **Uploads e arquivos — código concluído, validação externa pendente:** executar casos reais de PDF/DOCX/imagem, conferir magic bytes, diretório privado e remoção de temporários.
3. **MFA — código concluído, validação externa pendente:** testar TOTP, recuperação, expiração, revogação e login bloqueado no Supabase real.
4. **E-mail confirmado — código concluído, validação externa pendente:** conferir configuração, template, redirect e reenvio limitado no Supabase.
5. **Webhook Mercado Pago — bloqueado por configuração de provedor:** configurar `MERCADOPAGO_WEBHOOK_SECRET`, validar HMAC/replay e executar checkout controlado.
6. **Segredos, menor privilégio e TLS — revisão de código concluída:** confirmar no Supabase/Render a ausência de chave mestra exposta, executar scanner de segredos e verificar a conexão PostgreSQL efetiva com TLS.
7. **CSP e superfícies de renderização — código parcial:** concluir a migração de `style-src 'unsafe-inline'` e revisar as telas restantes após a sanitização central.
8. **Erros públicos — código concluído:** revisar endpoints operacionais legados para garantir mensagens estáveis e detalhes somente nos logs.
9. **Rate limiting — código local concluído:** validar os limites publicados e configurar proteção distribuída na borda antes de múltiplas instâncias.
10. **Senhas comprometidas — código e configuração do Render concluídos:** executar o teste controlado no serviço publicado sem registrar a senha usada.
11. **Backup e recuperação — runbook concluído:** confirmar backup diário, retenção e teste de restauração isolada conforme `DISASTER_RECOVERY.md`.
12. **Acessibilidade de modais — código concluído:** fazer a validação manual final com teclado em `<dialog>` e drawers.
13. **Páginas legais públicas — código concluído:** validar no deploy que `/termos` e `/privacidade` retornam HTML sem sessão e antes do cadastro.

### P1 — resultado, proteção, LGPD, IA e monetização

1. Fechar o loop de resultado: persistir eventos de candidatura e retorno, versionar currículo/carta e origem, registrar entrevistas qualificadas e criar a primeira visão de conversão por 100 candidaturas.
2. Transformar proteção contra golpe em etapa explícita de risco, com sinais, explicação, bloqueio ou revisão e registro do resultado.
3. Formalizar heurísticas de RH brasileiro para triagem, ATS, pretensão salarial, regime e vaga fantasma; cada regra deve ser versionada, explicável e coberta por teste.
4. Criar o copiloto de entrevistas baseado nos gaps: perguntas prováveis, roteiro de resposta com fatos comprovados e plano de preparação por vaga.
5. Implementar o acompanhamento da zona morta: prazos, lembretes, follow-up por canal e registro do retorno ou encerramento.
6. Implementar no mesmo sprint a exportação/portabilidade e a exclusão definitiva da conta, com confirmação forte, remoção de dados relacionados e política de retenção.
7. Registrar versão, data e evidência do consentimento de Termos e Privacidade.
8. Criar rotina de expurgo automático de temporários, prints e rascunhos após prazo configurável de 30/60 dias.
9. Ampliar a fronteira de dados não confiáveis para todos os prompts de vagas, OCR, Gmail e PDFs e adicionar casos hostis específicos por origem; o avaliador de entrevistas já está coberto.
10. Estruturar CLT/PJ/MEI/estágio, modalidade e salário com confiança de extração e exibição na análise.
11. Enviar comprovante simples por e-mail depois da confirmação idempotente do pagamento.
12. Finalizar os textos legais com responsável, canal de contato, retenção e subprocessadores.
13. Sincronizar o card de onboarding com o perfil e as preferências reais.
14. Exibir links legais e logout no cabeçalho/rodapé global.
15. Finalizar estados de carregamento e ações destrutivas de UX: skeleton no detalhe, `Limpar` como ação neutra com confirmação e teste visual do retry do Banco de vagas.
16. Ajustar a landing sem inventar prova social: explicitar o download avulso de R$ 9,90 e publicar FAQ somente com comportamentos realmente suportados.

### Próximo ciclo prático já classificado

1. **Gate de e-mail confirmado:** já implementado no backend; o próximo trabalho é somente validar a configuração real do Supabase, templates, redirecionamentos e reenvio em produção. Não é uma nova implementação P0.
2. **Idempotência de pagamentos:** permanece dentro do **P0.5**, junto da assinatura dos webhooks e da exposição pública correta das rotas. A chave deve registrar `order_nsu` e `payment_id` e permitir apenas uma transição válida para `PAID`.
3. **Expurgo automático de uploads:** permanece em **P1.8**, depois da validação do armazenamento privado; a rotina deve cobrir temporários, prints e rascunhos abandonados com prazo configurável de 30/60 dias.

### P2 — escala e diferenciação

- Separar Gmail/Outlook em worker próprio e monitorar falhas.
- Separar OCR/IA e tarefas de documentos em worker próprio com limites distribuídos de concorrência/CPU; os timeouts HTTP atuais continuam sendo a proteção do P0.
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
- A suíte completa foi reexecutada após a liberação pública das páginas legais: **100 testes aprovados em 4,069 s**, incluindo autenticação, sanitização HTML, normalização de títulos, parser de e-mail e regressão de rotas legais. O registro histórico de 59 testes ficou desatualizado porque novos testes foram adicionados.
- Migração RLS de produção aplicada com `scripts/migrate_rls.py`: 11 tabelas com RLS ativo e uma política por tabela; `document_export_purchases_owner` confirmado como política `ALL`.

## Auditoria do checklist de segurança e operação — 17/09/2026

| Item verificado | Evidência encontrada | Estado e prioridade |
| --- | --- | --- |
| Confirmação de e-mail | Gate no backend, tela pública de confirmação e reenvio limitado; testes de contas não confirmadas passam | Implementado no código; validação do template, redirect e recebimento real do Supabase permanece em **P0.4** |
| Cookies e headers | Cookies `HttpOnly`, `Secure` configurável e `SameSite=Lax`; middleware publica CSP com nonce por resposta para scripts, HSTS em HTTPS, `nosniff`, `DENY` e políticas complementares | `script-src` endurecido; migração de `style-src unsafe-inline` segue em **P0.7** |
| Rate limiting | Limites por IP/conta e testes de 429 aprovados; armazenamento é local ao processo | Proteção distribuída segue em **P0.9** |
| Isolamento/IDOR | Testes locais com dois usuários cobrem listagem, consulta, atualização e downloads; a prova com duas contas reais no Supabase ainda não foi executada | Código, testes locais e RLS publicados; prova real permanece em **P0.1** |
| RLS e menor privilégio | Consulta de produção confirmou RLS ativo nas 11 tabelas e uma política por tabela, incluindo `document_export_purchases_owner`; código cliente usa a chave publicável e o Render não exibe chave mestra | RLS aplicado; prova real de isolamento e conferência equivalente no Supabase permanecem em **P0.1/P0.6** |
| Senhas comprometidas | Consulta k-anonimizada envia apenas o prefixo do hash SHA-1 para o serviço de verificação; `PWNED_PASSWORD_CHECK` aparece no Render sem expor valor | Código e configuração do Render confirmados; testar comportamento do serviço publicado em **P0.10** |
| Uploads | Validador central confirma magic bytes, estrutura e decodificação de fotos; PDF/DOCX conferem assinatura/estrutura | Código e testes locais aprovados; validação operacional em **P0.2** e expurgo externo em **P1.8** |
| Arquivos temporários | OCR remove temporários ao terminar; documentos gerados usam diretório privado `0700` e limpeza de artefatos por idade; rascunhos/objetos externos ainda não têm rotina própria | Código e testes locais aprovados; expurgo de Storage/rascunhos em **P1.8** |
| MFA | Enrollment/status/unenroll e challenge/verify TOTP; login com fator verificado cria desafio temporário, conclusão promove a sessão e logout revoga sessão pendente | Código e testes locais aprovados; validar TOTP, recuperação e expiração em produção em **P0.3** |
| Gmail/Outlook | Gmail usa `gmail.readonly`; refresh tokens são cifrados com Fernet; OAuth usa `state` assinado e expirável | Implementado; manter auditoria de configuração do provedor |
| XSS e prompt injection | Sanitizador central remove markup executável antes de persistir/analisar; prompt de entrevistas delimita dados não confiáveis e testes hostis verificam que tags/instruções não escapam | Sanitização e primeira fronteira implementadas; CSP/superfícies restantes em **P0.7**, ampliar cobertura por origem em **P1.8** |
| Webhook de pagamento | Rota pública do Mercado Pago valida `x-signature`/`x-request-id` com HMAC e janela de replay; o handler consulta o provedor e permite uma única transição para `PAID`, rejeitando conflito de transação | Código e testes locais aprovados; `MERCADOPAGO_WEBHOOK_SECRET` ainda não aparece no Render e falta replay controlado em **P0.5** |
| Downloads e exportações | Rotas filtram a candidatura pelo usuário e exigem uma compra `PAID` do proprietário; testes de acesso cruzado passam, mas a autorização ainda não está vinculada a uma transação/exportação específica | Teste local aprovado; refinamento transacional em **P0.1** |
| Erros e informação interna | Handlers globais cobrem validação e exceções inesperadas; `/health` e IA retornam mensagens estáveis e registram detalhes apenas no log | Implementado; revisar endpoints operacionais restantes em **P0.8** |
| Tarefas pesadas | OCR, parsing, confirmação e busca externa usam threadpool com timeout total de 30 segundos; monitores ainda rodam no processo web e falta limite distribuído de concorrência/CPU | Código e testes locais aprovados; worker separado e limites distribuídos permanecem em **P2** |
| Backup e recuperação | `DISASTER_RECOVERY.md` cobre restauração isolada, validação de RLS, UptimeRobot e revogação/rotação sem registrar segredos | Runbook concluído; confirmar backup diário e executar restauração real em **P0.11** |
| SQL injection | Consultas de negócio usam SQLAlchemy com parâmetros; SQL dinâmico encontrado no script de RLS usa apenas nomes de tabelas constantes do próprio código | Coberto na revisão atual; manter regra de não interpolar entrada do usuário |
| SSRF | `job_source_fetcher` rejeita credenciais, resolve DNS, bloqueia IPs não globais, revalida redirecionamentos e limita resposta | Coberto na revisão atual; manter testes de regressão |
| Termos, privacidade e consentimento | Páginas e checkbox existem; versão/data/evidência do consentimento não são persistidas | Consentimento em **P1.7**; textos legais em **P1.11** |
| Exportação e exclusão LGPD | Não há fluxo de portabilidade e exclusão definitiva | **P1.6** |
| Recibo por e-mail | `receipt_url` pode ser persistida, mas não há envio automático | **P1.10** |
| InfinitePay | Variáveis legadas podem existir no ambiente histórico | Fora do escopo ativo; não validar nem recomendar como provedor |
| UptimeRobot | Monitor externo de disponibilidade/health check já faz parte da operação e está documentado; IDs e alertas ficam no painel externo | Concluído operacionalmente; conferir painel quando houver auditoria, sem recriar configuração |
| Suíte completa | Dependência `psycopg[binary]` instalada no ambiente local; descoberta completa executou 96 testes | **Concluído nesta verificação** |
| Acessibilidade dos modais | Script global registra disparador, foco inicial, retorno de foco, `aria-modal` e ciclo de Tab para `<dialog>` e modal customizado | Código e suíte local aprovados; validação manual com teclado em **P0.12** |

## Variáveis e segredos

Os valores reais não pertencem a este documento. Devem permanecer somente no painel do Render ou no ambiente local protegido:

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`;
- `COOKIE_SECURE`, `AUTH_REQUIRED`, `APP_BASE_URL`;
- `MFA_LOGIN_ENFORCE` (habilitado no Render para exigir challenge quando houver fator TOTP verificado);
- `PWNED_PASSWORD_CHECK` (habilitado no Render para bloquear senhas presentes em vazamentos conhecidos);
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_STATE_SECRET`;
- `TOKEN_ENCRYPTION_KEY`;
- `GEMINI_API_KEY`;
- `MERCADOPAGO_WEBHOOK_SECRET` e credenciais/tokens da InfinitePay.

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

Toda nova recomendação deve ser comparada com esta fila antes de virar tarefa. Se já existir, atualiza-se o item correspondente; se for nova, entra na prioridade que corresponde ao risco e à dependência. Uma etapa só sai da fila depois de código, teste e validação operacional compatíveis com o seu status.

### Protocolo para novas mensagens

Qualquer nova mensagem, print, documento ou sugestão relacionada ao produto passa primeiro por uma análise de impacto. O fluxo é:

1. identificar o que já existe e o que já foi concluído;
2. verificar se a sugestão duplica, altera ou bloqueia uma tarefa existente;
3. classificar a entrada em P0, P1 ou P2 conforme risco, dependência e valor;
4. atualizar esta fila e o status correspondente;
5. continuar pelo próximo item executável da fila, sem interromper o restante do plano para tratar somente a última mensagem.

Quando a etapa depender de uma conta, credencial, painel externo ou validação manual, ela permanece marcada como bloqueio externo e a solicitação de acesso é feita apenas nesse ponto.
