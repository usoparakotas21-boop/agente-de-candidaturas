# Projeto — Agente de Candidaturas

Última atualização: 13/08/2026  
Versão: 0.18.0  
Estado: autenticação, isolamento por usuário, Supabase, importação de currículo e captação por texto, print e PDF funcionais

## Entrega da versão 0.18.0

- Extração automática do link visível em prints, mesmo quando aparece sem `https://`.
- Leitura prioritária de dados estruturados `JobPosting` em páginas públicas.
- Recuperação de empresa e cargo pelo endereço público quando a página não responde.
- Vagas com confiança igual ou superior a 85% são cadastradas e analisadas sem intervenção.
- A revisão aparece somente quando as estratégias automáticas não atingem confiança suficiente.
- Acesso externo protegido contra endereços locais, respostas não HTML, excesso de redirecionamentos e páginas acima de 2 MB.

## Correção da versão 0.17.1

- Campos ainda ocultos da revisão não bloqueiam mais o primeiro envio do print.
- Empresa e cargo continuam validados depois que a prévia é exibida.

## Entrega da versão 0.17.0

- Prints e PDFs passam por uma prévia antes de alterar o banco.
- Empresa, cargo, localização, modalidade, salário, link e descrição podem ser corrigidos.
- O score só é calculado depois da confirmação dos dados.
- Removida a comparação aproximada que podia atualizar outra vaga com cargo semelhante.

## Correção da versão 0.16.4

- O OCR prioriza a região ampliada antes da imagem completa.
- Cabeçalhos como "Descrição da vaga", "Requisitos" e "Benefícios" não podem ser usados como empresa.

## Correção da versão 0.16.3

- Reenviar o mesmo print atualiza a vaga reconhecida anteriormente.
- Empresa, cargo, descrição e score são recalculados sem criar duplicata.
- Vagas arquivadas voltam para análise quando o arquivo é reenviado.

## Correção da versão 0.16.2

- Cargos quebrados em duas linhas pelo print são reunidos automaticamente.
- Termos como Generalista, Júnior, Pleno e Sênior deixam de ser confundidos com a empresa.

## Correção da versão 0.16.1

- Recorte automático da coluna principal em prints com página muito afastada.
- Ampliação da região do anúncio antes do reconhecimento de texto.
- Palavras de navegação como "Entra" deixam de ser tratadas como empresa.
- Prints com pouco texto reconhecido são recusados em vez de receber score artificial.

## Entrega da versão 0.16.0

- Upload de prints PNG, JPG, JPEG e WEBP de oportunidades.
- OCR local, sem enviar o conteúdo da vaga a serviços externos.
- Entrada de PDF textual no mesmo captador.
- Extração, filtro de duplicidade, cadastro e análise executados em um fluxo.
- Limites de 10 MB, 30 milhões de pixels e 20 páginas.
- Arquivos temporários removidos logo após a leitura.

## Entrega da versão 0.15.0

- Detalhamento visual do score por requisitos, experiência, senioridade,
  tecnologia e localização.
- Cada requisito informa se foi comprovado diretamente, por experiência
  relacionada ou se não foi encontrado.
- Cálculo existente preservado; a mudança aumenta a transparência sem alterar
  artificialmente a pontuação.

## Entrega da versão 0.14.0

- Nova entrada unificada `POST /intake/text` para textos copiados de e-mail,
  LinkedIn, Gupy, Indeed e páginas de carreira.
- Identificação automática de empresa, cargo, localização, modalidade, salário,
  URL e descrição.
- Cadastro da vaga, criação da candidatura e análise de aderência executados no
  mesmo fluxo.
- Impressão digital da oportunidade evita que alertas repetidos criem duplicatas.
- Novo botão **Captar vaga** no dashboard.
- Limite de 80 mil caracteres e nenhum acesso automático à URL informada,
  reduzindo riscos de abuso e SSRF.

## Entrega da versão 0.13.0

- Tela **Meu currículo** protegida por autenticação.
- Importação segura de DOCX e PDF textual, com limites de tamanho e estrutura.
- Extração de contato, resumo, experiências, competências, formação e idiomas.
- Perfil profissional estruturado e isolado por usuário no Supabase.
- Currículos personalizados deixaram de usar dados fixos de outro candidato.

## Entrega da versão 0.12.0

- Isolamento multiusuário por `owner_id` em candidatos e vagas.
- Consultas e documentos filtrados pelo usuário autenticado.
- Políticas RLS aplicadas no Supabase.

## Entrega da versão 0.11.0

- Banco migrado do SQLite para PostgreSQL no Supabase.
- Login com Supabase Auth e sessão protegida por cookie HttpOnly.
- Dashboard e endpoints protegidos por autenticação.

## Entrega da versão 0.10.0

- Resultado completo da análise salvo no SQLite.
- Score, recomendação, breakdown, forças, gaps e requisitos sobrevivem a reinícios.
- Migração automática e não destrutiva adiciona `analysis_data` ao banco existente.
- Dashboard exibe recomendação, forças e gaps sem exigir nova análise.
- Geração de currículo ou carta também atualiza a análise persistida.
- Teste automatizado confirma a recuperação dos dados após recarregar o painel.

## Entrega da versão 0.9.0

- Texto e caminho do DOCX da carta salvos na candidatura.
- Migração automática e não destrutiva do banco SQLite existente.
- Evento de geração da carta registrado na linha do tempo.
- Novo endpoint `GET /applications/{application_id}/cover-letter/document`.
- Botão **Baixar última carta** exibido no dashboard após a primeira geração.
- Teste de persistência e novo download do DOCX incluído.

## 1. Objetivo

Criar um agente de candidaturas para Paulo Henrique Santos Oliveira capaz de:

1. cadastrar e consultar vagas;
2. analisar aderência ao perfil;
3. calcular score, pontos fortes e gaps;
4. personalizar o currículo;
5. gerar um currículo executivo em DOCX;
6. devolver o arquivo para download;
7. futuramente acompanhar o histórico das candidaturas.

## 2. Projeto

- Diretório original: `C:\agente_curriculos`
- Ambiente virtual: `C:\agente_curriculos\.venv`
- API: FastAPI
- Banco: SQLite com SQLAlchemy
- Documento: `python-docx`

## 3. Como executar

```powershell
cd C:\agente_curriculos
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000>
- Swagger: <http://127.0.0.1:8000/docs>

## 4. Estado funcional

| Recurso | Estado |
|---|---|
| Inicialização da API | Funcional |
| Cadastro e consulta de vagas | Funcional |
| Análise e score | Funcional |
| Identificação de requisitos, forças e gaps | Funcional |
| Personalização do currículo | Funcional |
| Geração manual de DOCX | Funcional |
| Fluxo automático por `job_id` | Implementado na versão 0.5.0 |
| Download direto do DOCX | Implementado na versão 0.5.0 |
| Histórico de candidaturas | Implementado na versão 0.6.0 |
| Dashboard local | Implementado na versão 0.7.0 |
| Cadastro, análise e geração pelo dashboard | Implementado na versão 0.8.0 |

## 5. Entrega da versão 0.8.0

O dashboard passou a executar o fluxo diário completo:

1. botão **Nova vaga** com formulário;
2. cadastro da oportunidade e criação automática do histórico;
3. botão **Analisar vaga**;
4. exibição de score, pontos fortes e gaps;
5. botão **Gerar e baixar currículo**;
6. download imediato do DOCX personalizado;
7. novo download do último documento sem gerar outra cópia.

Novo endpoint:

| Método | Caminho | Finalidade |
|---|---|---|
| GET | `/applications/{application_id}/document` | Baixar novamente o último currículo |

O navegador mantém apenas o estado temporário da interface. Vagas, scores,
andamento e caminho do documento continuam persistidos no SQLite.

## 6. Entrega da versão 0.7.0

### Dashboard de vagas e candidaturas

Nova tela:

```text
http://127.0.0.1:8000/dashboard
```

O painel apresenta:

- total de vagas, oportunidades de alta prioridade, currículos gerados e entrevistas;
- busca por empresa ou cargo;
- filtro por etapa da candidatura;
- score de aderência e data da última atualização;
- distribuição das oportunidades por status;
- painel lateral com scores e linha do tempo;
- atualização de status e observações diretamente no navegador;
- layout responsivo para computador e celular.

O dashboard usa a própria API e o banco SQLite existentes. Nenhum dado de
candidatura é armazenado somente no navegador.

## 7. Entrega da versão 0.6.0

### Histórico persistente de candidaturas

Cada vaga possui agora uma candidatura vinculada e um histórico auditável de
mudanças. Os estados disponíveis são:

```text
IDENTIFICADA → ANALISADA → PERSONALIZADA → CURRICULO_GERADO
→ CANDIDATURA_ENVIADA → ENTREVISTA → APROVADO / RECUSADO → ARQUIVADA
```

O fluxo atualiza o estado automaticamente:

- cadastro da vaga: `IDENTIFICADA`;
- análise da vaga: `ANALISADA`;
- geração do DOCX: `CURRICULO_GERADO`.

Também são persistidos os scores de análise e personalização, recomendação e
caminho do último documento gerado. Vagas existentes são adicionadas ao histórico
automaticamente durante a inicialização da API.

Novos endpoints:

| Método | Caminho | Finalidade |
|---|---|---|
| GET | `/applications` | Listar candidaturas; aceita filtro `status` |
| GET | `/applications/{application_id}` | Consultar candidatura e eventos |
| PATCH | `/applications/{application_id}/status` | Alterar estado e registrar observação |

## 8. Entrega da versão 0.5.0

### Fluxo integrado

Novo endpoint:

```http
POST /jobs/{job_id}/generate-document
```

Ele executa automaticamente:

```text
VAGA → ANÁLISE → PERSONALIZAÇÃO → CURRÍCULO → DOCX → DOWNLOAD
```

O retorno é o próprio arquivo DOCX. Os cabeçalhos `X-Analysis-Score` e
`X-Personalization-Score` informam os scores calculados.

### Outras correções

- O endpoint `POST /analyze-job` voltou a executar e retornar a análise; antes,
  ele montava o perfil mas terminava sem resposta.
- Vagas inexistentes agora retornam HTTP 404 de forma consistente.
- O perfil do candidato passou a ser carregado do banco; o perfil mestre é usado
  como fallback se ainda não houver candidato cadastrado.
- A duplicação do perfil dentro de `main.py` foi removida.
- O currículo destaca competências relevantes para a vaga.
- As experiências são ordenadas por relevância, sem excluir o histórico real.
- A versão da API foi atualizada de `0.4.0` para `0.5.0`.

## 9. Endpoints principais

| Método | Caminho | Finalidade |
|---|---|---|
| GET | `/` | Estado e versão da API |
| POST | `/jobs` | Cadastrar vaga |
| GET | `/jobs` | Listar vagas |
| GET | `/jobs/{job_id}` | Consultar vaga |
| POST | `/analyze-job` | Analisar uma descrição enviada diretamente |
| POST | `/jobs/{job_id}/analyze` | Analisar uma vaga cadastrada |
| POST | `/generate-document` | Gerar DOCX a partir de currículo informado |
| POST | `/jobs/{job_id}/generate-document` | Executar o fluxo completo e baixar o DOCX |
| GET | `/applications` | Listar e filtrar candidaturas |
| GET | `/applications/{application_id}` | Consultar histórico de uma candidatura |
| PATCH | `/applications/{application_id}/status` | Atualizar o andamento |
| GET | `/dashboard` | Abrir o painel visual local |
| GET | `/applications/{application_id}/document` | Baixar o DOCX existente |

## 10. Estrutura relevante

- `app/main.py`: endpoints e orquestração do fluxo.
- `app/analyzer.py`: análise, score, requisitos, forças e gaps.
- `app/resume_personalizer.py`: seleção das áreas, competências e experiências.
- `app/resume_generator.py`: montagem do currículo personalizado.
- `app/resume_document.py`: geração e layout do DOCX.
- `app/models.py`: modelos do banco.
- `app/database.py`: conexão SQLite.
- `app/static/dashboard.html`: interface visual de acompanhamento.
- `tests/test_integrated_flow.py`: testes do fluxo, histórico, download e erros 404.

## 11. Validação

Executado com sucesso em 13/08/2026:

- compilação de todos os módulos Python alterados;
- personalização de uma vaga de Coordenador de Recursos Humanos;
- geração real de DOCX;
- validação da estrutura ZIP/DOCX;
- inspeção do conteúdo: cargo-alvo, competências prioritárias, experiências,
  formação e idiomas preservados.

Também foi criada uma suíte `unittest` para validar o endpoint integrado no
ambiente virtual do projeto:

```powershell
python -m unittest discover -s tests -v
```

## 12. Perfil do candidato

- Nome: Paulo Henrique Santos Oliveira
- Localização: Salvador/BA
- Área: Recursos Humanos e Departamento Pessoal
- Experiência: mais de 10 anos
- Diferenciais: gestão de equipes, folha, recrutamento, treinamento, Power BI,
  indicadores, e-Social, relações trabalhistas, redução de custos e ISO 9001.

Os dados completos de contato, experiências, formação e idiomas permanecem no
banco e no perfil mestre de `app/resume_document.py`.

## 13. Próximos passos recomendados

1. Executar a suíte completa no ambiente virtual Python 3.14 do projeto.
2. Adicionar carta de apresentação personalizada.
3. Adicionar filtros por período e faixa de score.
4. Gerar carta de apresentação personalizada.
5. Automatizar backup dos documentos gerados.

## 14. Regra de continuidade

Não reconstruir o projeto do zero. Antes de alterar código, revisar os módulos
listados na seção 7, preservar os dados reais e executar os testes de sintaxe,
integração e geração de DOCX. Atualizar este arquivo após cada entrega relevante.

## 15. Entrega 0.19.0 - conexão segura com Gmail

- OAuth 2.0 individual por usuário com o escopo `gmail.readonly`.
- Botão `Conectar Gmail` no painel.
- Confirmação automática do endereço Gmail autorizado.
- Refresh token armazenado criptografado no banco, nunca no navegador.
- Client Secret e chave de criptografia somente em variáveis de ambiente.
- Estado OAuth assinado, vinculado ao usuário e válido por dez minutos.
- Nenhuma senha do Gmail é armazenada pelo sistema.

Esta etapa conecta e valida a caixa de entrada. A próxima entrega deve usar essa
conexão para buscar periodicamente alertas de vagas, eliminar duplicidades,
extrair links e encaminhar automaticamente as oportunidades ao analisador.

## 16. Entrega 0.20.0 - leitor automático do Gmail

- Consulta automática a cada cinco minutos, com intervalo configurável.
- Busca inicial após quinze segundos da inicialização do servidor.
- Pesquisa limitada a alertas e termos relacionados a vagas.
- Leitura de mensagens MIME em texto e HTML usando `gmail.readonly`.
- Extração de links presentes no corpo HTML.
- Filtro determinístico para descartar mensagens sem sinais de oportunidade.
- Identificação da origem: LinkedIn, Indeed, Gupy, InfoJobs, BeBee, Catho e
  Glassdoor.
- Cadastro e análise automática pelo fluxo já existente em `/intake/text`.
- Registro do ID imutável de cada mensagem para impedir processamento repetido.
- Botão `Buscar e-mails` para sincronização imediata e conferência manual.
- Nenhuma mensagem é alterada, marcada como lida, enviada ou excluída.

Variáveis adicionadas pelo instalador:

- `GMAIL_AUTO_SYNC=true`
- `GMAIL_POLL_SECONDS=300`

Próxima evolução: executar o monitor em serviço hospedado 24 horas, adicionar
uma página de preferências de busca e substituir o agendamento local por um
worker distribuído quando houver mais de uma instância na nuvem.
