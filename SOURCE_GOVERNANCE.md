# Governança de fontes de vagas

**Estado:** gate pré-ingestão P1.20. Nenhuma fonte externa está aprovada para coleta automática neste momento.
**Revisado em:** 21/09/2026.

## Escopo atual

O `app/job_source_fetcher.py` só busca, sob ação do usuário, a página pública de uma vaga específica para extrair JSON-LD. Isso não é um crawler de descoberta nem concede autorização para coleta periódica. `app/ats_registry.py` identifica domínios conhecidos para classificar a origem; estar nessa lista não autoriza scraping.

Não criar adaptador, scheduler ou worker de descoberta até uma fonte e o uso pretendido terem uma aprovação registrada aqui e no registro de políticas do código. Vaga publicada/publicamente acessível não significa, por si só, licença para republicar a descrição integral, armazená-la por prazo indefinido ou processá-la com IA.

## Avaliação inicial de fontes oficiais

| Fonte | Evidência oficial encontrada | Decisão para o projeto |
| --- | --- | --- |
| Lever Postings API | A documentação descreve uma API de postings por quadro de uma empresa, sem busca de texto completo entre empresas, e diz que postings publicados são visíveis publicamente e podem ser raspados por terceiros. | Melhor candidata técnica para um piloto por quadro. Continua **não aprovada** até documentar direitos de exibição comercial, transformação por IA e cache do conteúdo, atribuição, limites e remoção; manter link canônico para candidatura. |
| Greenhouse Job Board API | Endpoints GET de vagas publicadas são públicos e não exigem autenticação; a documentação apresenta o uso como construção de páginas de carreira da própria empresa. | Acesso público ao endpoint não prova licença de agregação comercial. Só avançar com autorização do empregador/quadro ou termos que cubram o produto. |
| Gupy External Career Page | O fluxo documentado exige Bearer Token gerado na conta da empresa e destina o endpoint a exibir as próprias vagas publicadas numa página externa da empresa. | Não é uma API pública geral de busca. Só usar com token e autorização de cada empresa participante; manter o token no servidor. |
| Adzuna e Jooble | Cobertura brasileira, uso comercial, requisitos de atribuição e direitos de armazenamento/transformação ainda não estão aprovados para este produto. | Não integrar antes de confirmação escrita dos termos aplicáveis ao Brasil e ao modelo comercial. |

Fontes primárias: [Lever Postings API](https://github.com/lever/postings-api), [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html), [Gupy — fluxo de Página de Carreira Externa](https://developers.gupy.io/v2.0/docs/fluxo-de-p%C3%A1gina-de-carreira-externa). A LGPD define tratamento de forma ampla, incluindo coleta, classificação, utilização, armazenamento e extração, e exige finalidade, adequação e necessidade; consultar o [texto oficial da LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm) ao definir campos e retenção. A avaliação de endpoint público versus licença comercial é uma inferência conservadora das finalidades descritas pelos fornecedores, não uma afirmação de que a API pública, sozinha, autoriza republicação comercial.

## Inventário individual e estado da autorização — 21/09/2026

### Lista prioritária escolhida pelo proprietário

O proprietário selecionou **LinkedIn, InfoJobs, Vagas.com, Sólides, Jobbol, Catho, Gupy, Empregos.com.br e Glassdoor** como fontes desejadas. Abaixo fica o resultado da verificação das páginas oficiais localizadas nesta revisão. Em todos os casos, o estado operacional da Candidatura Certa é **pendente de autorização**: nenhuma delas está liberada para descoberta automática.

| Fonte | Evidência oficial consultada e implicação para o uso pretendido | Próximo requisito de autorização |
| --- | --- | --- |
| LinkedIn (`linkedin.com`) | Os [termos de crawling](https://www.linkedin.com/legal/crawling-terms) proíbem crawling sem permissão expressa e limitam usos aprovados; uso alternativo em outro serviço de internet requer aprovação separada, e os termos vedam contornar controles ou mascarar IP/User-Agent. O [User Agreement](https://www.linkedin.com/legal/user-agreement) também restringe métodos automatizados não autorizados. | Solicitar autorização escrita que cubra especificamente o produto Candidatura Certa, exibição de vagas, uso comercial, campos, cache e processamento. Sem aprovação expressa para esse modelo, não automatizar. Proxies/stealth não podem ser usados para contornar os controles. |
| InfoJobs (`infojobs.com.br`) | O [Aviso Legal para Empresas](https://www.infojobs.com.br/legal/aviso-legal-para-empresas__15726.aspx) veda leitura por robôs/programas automáticos e cópia do conteúdo; a exceção exige autorização expressa dos titulares/InfoJobs. A licença de usuário descrita é limitada ao uso pessoal ligado ao portal. | Obter autorização expressa/licença comercial específica para crawler/agregador e os usos pretendidos; até lá, bloqueado. |
| Vagas.com (`vagas.com.br`) | Os [Termos de Uso para candidatos](https://www.vagas.com.br/candidatos/termos-de-uso) descrevem a busca e candidatura no próprio portal. O VaaS citado no material institucional envia vagas de sistemas externos **para** a Vagas.com e direciona o candidato ao sistema original; não é uma API de descoberta para terceiros nem autorização para republicar vagas. | Pedir acordo/API de parceria para consumo e exibição no Candidatura Certa, definindo campos, atribuição, link de candidatura, cache e uso comercial. |
| Sólides (`vagas.solides.com.br`) | A [Sólides Vagas](https://vagas.solides.com.br/) é um portal público de oportunidades. A [documentação da Jobs API](https://developer.api.solides.jobs/) lista endpoints de vagas, mas não foi localizada licença que conceda a um agregador externo o direito de coletar e redistribuir anúncios de empresas parceiras. | Solicitar ao fornecedor um acesso/API e autorização contratual que cubra agregação e exibição comercial. Não reutilizar credenciais de candidato nem presumir que a API documentada concede essa licença. |
| Jobbol (`jobbol.com.br`) | Os [Termos para candidatos](https://candidatos.jobbol.com.br/termos-uso), atualizados em 26/08/2026, proíbem mecanismos automatizados (bots, scripts e extensões) para acessar, interagir ou sobrecarregar a plataforma, salvo autorização expressa. | Solicitar exceção/licença escrita ou feed oficial para agregação comercial. Sem isso, não coletar automaticamente. |
| Catho (`catho.com.br`) | Os [termos oficiais da API pública](https://assets.catho.com.br/consents-prod/terms/termos-de-uso-api-publica-v1.pdf) tratam de integração para contratantes e vedam atividade semelhante a robô para replicar o banco de dados. O documento não autoriza a Candidatura Certa a operar um agregador de vagas. | Negociar parceria/API com autorização explícita para descoberta e exibição de vagas; não usar a API fora do escopo contratual. |
| Gupy (`gupy.io`) | O [fluxo oficial de Página de Carreira Externa](https://developers.gupy.io/v2.0/docs/fluxo-de-p%C3%A1gina-de-carreira-externa) usa Bearer Token gerado na conta da empresa para exibir as vagas dessa empresa em página externa própria. Não é uma credencial geral para buscar vagas de todas as empresas na Gupy. | Para cada empresa participante, obter consentimento/contrato e token com escopo autorizado; acordar exibição, campos, transformação, cache e link canônico. |
| Empregos.com.br (`empregos.com.br`) | O [contrato do candidato](https://candidato.empregos.com.br/contrato.aspx) e a [política de privacidade](https://www.empregos.com.br/politica-de-privacidade.aspx) descrevem o uso do portal e de seus dados, mas não concedem à Candidatura Certa licença de coleta/agregação de anúncios. O contrato reconhece parcerias comerciais, sem estabelecer uma licença geral para terceiros. | Pedir acordo comercial/API/feed que autorize o uso pretendido, os campos, a atribuição, a retenção e o encaminhamento ao anúncio original. |
| Glassdoor (`glassdoor.com`) | Os [Termos de Uso](https://www.glassdoor.com/about/terms-2022-12-01/) restringem uso automatizado, scraping/mineração e uso comercial sem permissão expressa/acordo separado. | Obter autorização escrita e acordo comercial específico para scraping/agregação e exibição. Sem isso, bloqueado. |

**Resumo da lista prioritária:** 9 selecionadas; **0 autorizadas** no projeto. LinkedIn, InfoJobs, Jobbol, Catho e Glassdoor têm restrições expressas no material oficial consultado; Sólides, Gupy, Vagas.com e Empregos.com.br exigem autorização/acordo que cubra claramente a republicação comercial, pois os recursos documentados não concedem licença geral à Candidatura Certa. Essa triagem registra os textos oficiais consultados e não substitui revisão jurídica dos acordos finais.

O catálogo `app/ats_registry.py` contém domínios para **reconhecer e classificar** a origem de uma vaga. Para cada domínio, o registro é: **nenhuma autorização de coleta automática arquivada; fonte bloqueada**. A presença no catálogo não representa integração, consentimento, licença nem aprovação. A autorização deve ser concedida pelo proprietário do quadro/empresa ou coberta por licença comercial aplicável ao produto e ao uso pretendido.

| Fonte/domínio reconhecido | Estado para descoberta/coleta automática | Evidência exigida antes de habilitar |
| --- | --- | --- |
| Gupy — `gupy.io` | Bloqueada; sem permissão por empresa/quadro registrada. | Token emitido por empresa participante e autorização escrita que cubra coleta pela Candidatura Certa, campos, exibição, cache e processamento pretendidos. O fluxo oficial da Gupy descreve uma página externa da própria empresa, não uma licença geral de agregação. |
| Sólides — `solides.com`, `solides.com.br` (inclui `vagas.solides.com.br`) | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita do proprietário de cada quadro e escopo de uso. |
| Vagas.com — `vagas.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita aplicável à descoberta e exibição comercial. |
| Kenoby — `kenoby.com` | Bloqueada; sem autorização registrada. | Confirmar entidade/serviço atual, endpoint vigente e autorização aplicável antes de qualquer coleta. |
| TAQE — `taqe.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita do proprietário do conteúdo. |
| Abler — `abler.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita por quadro/empresa participante. |
| InHire — `inhire.app` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita por quadro/empresa participante. |
| Revelo — `revelo.com.br` | Bloqueada; sem autorização registrada. | Confirmar endpoint e termos vigentes, mais licença/autorização para o modelo comercial. |
| Empregos.com.br — `empregos.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita para coleta, exibição, cache e atribuição. |
| InfoJobs — `infojobs.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita; nenhuma automação de navegador está aprovada. |
| Catho — `catho.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita; nenhuma automação de navegador está aprovada. |
| Jobbol — `jobbol.com.br` | Bloqueada; os termos atuais vedam automação de acesso/interação sem autorização expressa. | Obter autorização escrita/feed oficial que permita agregação comercial, ou manter desativada. |
| Bebee — `bebee.com.br` | Bloqueada; sem autorização registrada. | Confirmar a fonte/endpoint vigente e documentar licença/autorização para o uso comercial. |
| Trabalha Brasil — `trabalhabrasil.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita para coleta e republicação dos campos pretendidos. |
| Curriculum — `curriculum.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita para o uso pretendido. |
| Apinfo — `apinfo.com.br` | Bloqueada; sem autorização registrada. | Licença/API oficial ou autorização escrita para o uso pretendido. |
| LinkedIn — `linkedin.com` | Bloqueada; nenhum acordo/API foi registrado. | Acordo e acesso oficial que permitam expressamente a coleta automatizada e o uso comercial; não contornar login, CAPTCHA, rate limit ou controles anti-bot. |
| Indeed — `indeed.com` | Bloqueada; nenhum acordo/API foi registrado. | Acordo e acesso oficial que permitam expressamente a coleta automatizada e o uso comercial; não contornar controles de acesso. |
| Glassdoor — `glassdoor.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável a coleta, exibição comercial, cache e atribuição. |
| Monster — `monster.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável ao território brasileiro e ao produto. |
| CareerBuilder — `careerbuilder.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável ao território brasileiro e ao produto. |
| ZipRecruiter — `ziprecruiter.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial que cubra território, uso comercial, campos, atribuição e retenção. |
| SimplyHired — `simplyhired.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial que cubra o produto e o uso pretendido. |
| Dice — `dice.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável ao uso comercial e ao território. |
| Wellfound — `wellfound.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável à coleta e exibição pela plataforma. |
| Remotive — `remotive.io` | Bloqueada; sem autorização registrada. | Confirmar termos e licença atuais da API/feed para uso comercial, atribuição, cache e transformação. |
| We Work Remotely — `weworkremotely.com` | Bloqueada; sem autorização registrada. | Licença/API/feed oficial que autorize agregação e exibição comercial. |
| Remote OK — `remoteok.io` | Bloqueada; sem autorização registrada. | Confirmar licença atual do feed/API e requisitos de atribuição, cache e exibição comercial. |
| FlexJobs — `flexjobs.com` | Bloqueada; sem autorização registrada. | Acordo/API oficial aplicável; acesso público a páginas não é autorização. |

As APIs **Lever Postings**, **Greenhouse Job Board**, **Adzuna** e **Jooble** também permanecem como candidatas separadas, não como fontes habilitadas: Lever e Greenhouse expõem dados de quadros específicos, mas não há no projeto uma autorização para agregação comercial; para Adzuna e Jooble, licença, cobertura no Brasil, atribuição, armazenamento e transformação ainda não foram comprovados. Em Gupy, autorização/token deve ser por empresa participante, nunca um token genérico presumido.

**Resultado do inventário:** 30/30 domínios de ATS catalogados com decisão explícita; **0/30 autorizados**; 0 credenciais de fonte registradas; nenhuma descoberta ou coleta automática habilitada. Nenhuma permissão foi inferida de `robots.txt`, página pública, endpoint sem autenticação, existência de integração de e-mail ou link enviado pela pessoa usuária.

O importador acionado pela pessoa usuária para analisar **uma vaga específica** e os conectores de e-mail autorizados pela própria pessoa permanecem fluxos separados. Eles não autorizam descoberta em lote nem coleta periódica no site de origem.

## Registro obrigatório antes de ativar uma fonte

Cada fonte/quadro precisa de uma entrada revisada com:

- identificador estável da fonte, fornecedor, empresa/proprietário do quadro e domínios exatos;
- endpoint e campos permitidos; propósito e público a que a permissão se aplica;
- URL e data da versão dos Termos/licença/contrato, evidência da autorização do proprietário e hash de uma cópia arquivada quando permitido;
- permissão explícita para exibição comercial, transformação com IA, cache e republicação dos campos pretendidos;
- regra de atribuição, link canônico para candidatura e requisitos de marca;
- revisão de `robots.txt` e de restrições do endpoint; isso complementa, mas não substitui, autorização/termos/licença;
- orçamento por host: intervalo mínimo, concorrência, backoff, limites diários e identificador de agente transparente;
- campos pessoais permitidos, minimização, prazo de retenção e mecanismo para expirar/retirar vaga e purgar dados brutos;
- responsável pela revisão, data de reavaliação e condição de desligamento.
- a aprovação expira após 180 dias; uma mudança nos Termos, escopo, endpoint ou entidade proprietária exige revisão imediata.

## Padrões de execução

1. **Deny by default:** fonte sem política explicitamente aprovada não pode entrar em coleta automatizada. A lista de domínios ATS conhecidos é somente classificatória.
2. **Aprovar cada uso separadamente:** `require_approved_source` exige por padrão direitos de `automated_fetch` **e** `commercial_display`. Qualquer worker deve acrescentar os demais usos que realizar — por exemplo `ai_processing`, `description_caching` e `redistribution` — em `required_uses`. Um direito de buscar não concede os outros.
3. **Minimizar e atribuir:** preferir cargo, empresa, local, modalidade, data, identificador externo e link canônico. Não persistir HTML ou e-mails de recrutadores por padrão; guardar conteúdo bruto somente se necessário, licenciado e com TTL curto documentado.
4. **Respeitar limites e revogação:** aplicar rate limit por domínio, backoff e validade do anúncio. Interromper a fonte se os termos mudarem, a permissão for revogada ou houver resposta de bloqueio/limite; não tentar contornar autenticação, CAPTCHA ou bloqueio deliberado.
5. **Proxies e stealth:** permanecem apenas como opção condicional para fontes autorizadas quando necessário e permitido pelos termos. Não usar para contornar CAPTCHA, autenticação, rate limits ou controles de acesso.
6. **Revalidar:** revisar a autorização e os termos antes de ampliar o piloto, alterar campos/uso, habilitar cache maior ou acrescentar uma empresa/quadro.

## Envio automático de candidaturas — autorização separada

O direito de descobrir ou exibir uma vaga **não** autoriza enviar currículo, carta, respostas de triagem ou dados de contato ao empregador. Cada conector de candidatura deve exigir o uso separado `automated_submission`, aprovação para o ATS/quadro e escopo de endpoint, campos, anexos, retenção e confirmação de recebimento. O envio também precisa de consentimento explícito da pessoa candidata para cada destino e oportunidade selecionados; o limite ou score configurado pelo usuário não substitui esse consentimento.

As APIs oficiais encontradas não são credenciais gerais para candidaturas em portais de terceiros: o [LinkedIn Apply Connect](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect/create-apply-connect-jobs?view=li-lts-2025-04) é restrito a parceiros aprovados; o [Indeed Send Candidates API](https://docs.indeed.com/send-candidates-api/) sincroniza candidaturas de parceiros; e o [Lever Apply to a posting](https://hire.lever.co/developer/documentation) requer chave de API da conta empregadora com acesso ao endpoint. Portanto, nenhuma delas habilita envio a todos os empregadores ou aos nove portais escolhidos sem acordos e credenciais concedidos por cada empresa/integradora.

Automação de navegador, extensão, proxies ou stealth não podem ser usados para contornar termos, autenticação, CAPTCHA, limites ou controles dos portais. O complemento assistivo `chrome-extension/` apenas preenche campos vazios e reconhecidos após a pessoa abrir a aba, marcar consentimento naquela página e clicar para preencher; não lê páginas em segundo plano, não envia formulários nem satisfaz o direito `automated_submission`. Ele só deve ser usado em páginas nas quais o preenchimento assistido seja permitido; se o portal proibir automação ou apresentar um controle/bloqueio, a pessoa continua manualmente. Sem API/integração oficial e autorização que cubram a submissão, o envio final permanece com a pessoa candidata.

## Próxima etapa

Concluir a fundação de código deny-by-default, sem aprovar fontes implicitamente. Depois, selecionar um quadro participante e documentar a autorização e o uso permitido antes de P2.1/P2.2. Até lá, nenhuma ingestão em massa nem tabela global `job_listings` deve ser ativada.
