# Governança de fontes de vagas

**Estado:** gate pré-ingestão P1.20. Nenhuma fonte externa está aprovada para coleta automática neste momento.
**Revisado em:** 20/09/2026.

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
2. **Minimizar e atribuir:** preferir cargo, empresa, local, modalidade, data, identificador externo e link canônico. Não persistir HTML ou e-mails de recrutadores por padrão; guardar conteúdo bruto somente se necessário, licenciado e com TTL curto documentado.
3. **Respeitar limites e revogação:** aplicar rate limit por domínio, backoff e validade do anúncio. Interromper a fonte se os termos mudarem, a permissão for revogada ou houver resposta de bloqueio/limite; não tentar contornar autenticação, CAPTCHA ou bloqueio deliberado.
4. **Proxies e stealth:** permanecem apenas como opção condicional para fontes autorizadas quando necessário e permitido pelos termos. Não usar para contornar CAPTCHA, autenticação, rate limits ou controles de acesso.
5. **Revalidar:** revisar a autorização e os termos antes de ampliar o piloto, alterar campos/uso, habilitar cache maior ou acrescentar uma empresa/quadro.

## Próxima etapa

Concluir a fundação de código deny-by-default, sem aprovar fontes implicitamente. Depois, selecionar um quadro participante e documentar a autorização e o uso permitido antes de P2.1/P2.2. Até lá, nenhuma ingestão em massa nem tabela global `job_listings` deve ser ativada.
