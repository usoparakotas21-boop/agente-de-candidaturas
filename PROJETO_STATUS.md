# Projeto — Agente de Candidaturas

Última atualização: 31/08/2026  
Versão atual confirmada no código: **0.24.0**  
Diretório principal: `C:\agente_curriculos`  
Estado: aplicação local funcional, com autenticação, banco Supabase, importação e personalização de currículo, captação de vagas por texto/arquivo e leitura automática do Gmail.

> Este documento foi criado para permitir que uma pessoa ou outro assistente retome o projeto sem reconstruí-lo do zero. Ele não contém senhas, tokens nem chaves privadas.

## 1. Visão do produto

Criar um agente de carreira hospedado na nuvem e disponível 24 horas, capaz de trabalhar com mínima interferência do usuário:

1. captar oportunidades automaticamente;
2. filtrar as vagas usando as preferências do candidato;
3. analisar aderência ao perfil profissional;
4. adaptar o currículo sem inventar informações;
5. gerar currículo e carta de apresentação;
6. candidatar-se automaticamente quando houver autorização e segurança;
7. solicitar intervenção somente para CAPTCHA, perguntas sensíveis, declarações ou casos de baixa confiança;
8. acompanhar candidatura, entrevista, reprovação e aprovação;
9. aprender quais fontes e versões de currículo produzem mais entrevistas.

### Posicionamento recomendado

**Um agente brasileiro de carreira que encontra oportunidades em qualquer canal, entende cada vaga, adapta documentos com informações comprovadas e se candidata dentro das regras definidas pelo usuário.**

Métrica principal futura: **entrevistas qualificadas por 100 candidaturas**, e não somente quantidade de candidaturas enviadas.

## 2. Estado atual

### Funcional

- API FastAPI e dashboard responsivo.
- Login e logout usando Supabase Auth.
- Sessão protegida por cookie HttpOnly.
- Isolamento dos dados por usuário (`owner_id`).
- Banco PostgreSQL no Supabase quando `DATABASE_URL` está configurada.
- SQLite local em `data/agente.db` como fallback de desenvolvimento.
- Importação de currículo DOCX e PDF textual.
- Estruturação do perfil, experiências e competências.
- Cadastro manual de vagas.
- Captação unificada por texto copiado.
- Captação por print e PDF.
- OCR local para imagens.
- Tentativa de recuperar informações de páginas públicas e dados `JobPosting`.
- Detecção de duplicidade.
- Análise de aderência, score, forças, gaps e recomendação.
- Detalhamento explicável do score.
- Geração e download de currículo personalizado em DOCX.
- Geração, persistência e download de carta de apresentação em DOCX.
- Histórico de status e linha do tempo da candidatura.
- OAuth individual do Gmail com escopo somente leitura.
- Refresh token do Gmail criptografado no banco.
- Leitor automático do Gmail a cada cinco minutos.
- Botão de sincronização imediata dos e-mails.
- Registro de mensagens processadas para evitar repetição.
- Separação de e-mails-resumo em vagas individuais usando os links de cada cartão.
- Conversão do HTML dos alertas em texto limpo, preservando a posição das URLs.
- Confiança separada para cargo, empresa, descrição e URL.
- Barreira de qualidade antes da persistência automática pelo Gmail.
- Registro da decisão e dos motivos de cada vaga encontrada no e-mail.
- Motor de decisão v0.22.0 com três estados: `AUTOMATICA`, `REVISAR` e `DESCARTAR`.
- Confiança de captura abaixo de 80% impede decisão `AUTOMATICA`.
- Confiança de captura ausente também impede decisão `AUTOMATICA`.
- Modalidade preferida ausente gera `REVISAR`.
- Localização preferida ausente gera `REVISAR`.
- Decisão `AUTOMATICA` exige score mínimo, autorização do usuário, confiança de captura >= 80% e ausência de pendências.
- Motivos da decisão automática passaram a explicar os principais gates utilizados.
- Fila persistente com aprovação, recusa, promoção automática e endpoints de consulta.
- Extrator de vagas por texto validado para campos rotulados, URLs sem protocolo, títulos em múltiplas linhas e identificação estável de duplicidade.
- Suíte automatizada com 38 testes aprovados em 31/08/2026.

### Ainda não concluído

- Hospedagem pública 24 horas.
- Worker distribuído para executar o monitor fora do processo web.
- Exibir a fila de decisão no dashboard para `AUTOMATICA`, `REVISAR` e `DESCARTAR`.
- Envio automático geral de candidaturas.
- Integrações oficiais adicionais com plataformas de vagas.
- Pagamentos e liberação de planos.
- Painel administrativo multiusuário.
- Auditoria de segurança final e preparação para LGPD.
- Aprendizado baseado em entrevistas, reprovações e aprovações.
- Redesign visual final.

## 3. Problemas conhecidos

1. Templates incomuns de alerta, sem links individuais nem títulos reconhecíveis, ainda podem exigir revisão manual.
2. A decisão `REVISAR` já impede a persistência automática, mas ainda precisa de uma fila visível no dashboard.
3. Na primeira sincronização da versão 0.20.0, algumas mensagens geraram `HTTPException`. Elas foram registradas como processadas para evitar repetição infinita.
4. O score pode mudar quando o currículo importado altera o perfil estruturado. A interface deve explicar quais dados causaram a mudança.
5. O monitor atual só funciona enquanto o servidor local estiver ligado. Ele ainda não funciona com o computador desligado.
6. A persistência de `DATABASE_URL` deve ser verificada em um novo PowerShell. A conexão não pode depender apenas de uma variável criada na sessão anterior.

## 4. Próximo passo recomendado

Continuar o **motor de qualidade e decisão**, antes de ampliar o envio automático:

1. concluído: dividir e-mails-resumo em vagas individuais e validar os campos capturados;
2. concluído: aplicar gates de confiança, preferências e decisão explicável;
3. concluído: persistir a fila com decisões `AUTOMATICA`, `REVISAR` e `DESCARTAR`;
4. próximo: exibir e operar essa fila pelo dashboard;
5. depois: combinar a fila revisada com o fluxo de candidatura;
6. somente depois iniciar a automação de envio.

## 5. Arquitetura atual

```text
Navegador / celular
        |
        v
Dashboard HTML + JavaScript
        |
        v
FastAPI
   |----------- Supabase Auth
   |----------- PostgreSQL Supabase
   |----------- Gmail API (readonly)
   |----------- OCR local
   |----------- Analisador de aderência
   |----------- Gerador de DOCX
        |
        v
Currículos, cartas, vagas e histórico
```

### Tecnologias

- Python e FastAPI.
- SQLAlchemy.
- PostgreSQL/Supabase.
- SQLite para fallback local e testes.
- Supabase Auth.
- Gmail API com OAuth 2.0.
- `python-docx` para documentos Word.
- Leitura de PDF textual.
- OCR local para prints.
- HTML, CSS e JavaScript sem framework no dashboard atual.

## 6. Serviços externos configurados

### Supabase

- Projeto criado e conectado.
- Referência pública do projeto: `cmmdjnonbedekizbvify`.
- Supabase Auth testado com usuário real.
- Banco PostgreSQL testado.
- Migração inicial executada.
- Tabelas principais existentes no Supabase.
- RLS foi introduzido na versão 0.12.0; revisar novamente antes da publicação.

### Google Cloud

- Projeto: `agente-de-candidaturas`.
- Gmail API ativada.
- Tela de consentimento configurada para testes.
- Escopo usado: `gmail.readonly`.
- Cliente OAuth Web criado.
- Redirecionamento local usado: `http://127.0.0.1:8001/auth/gmail/callback`.
- O cliente que teve seu segredo exposto foi excluído e substituído.
- O JSON do cliente atual foi baixado e usado pelo instalador.

> Nunca registrar neste arquivo o Client Secret, a senha do Supabase, a URI completa do banco, tokens OAuth ou a chave de criptografia.

## 7. Estrutura principal

```text
C:\agente_curriculos
├── app
│   ├── main.py
│   ├── auth.py
│   ├── database.py
│   ├── models.py
│   ├── analyzer.py
│   ├── job_intake.py
│   ├── job_quality.py
│   ├── job_file_intake.py
│   ├── job_source_fetcher.py
│   ├── resume_importer.py
│   ├── resume_personalizer.py
│   ├── resume_generator.py
│   ├── resume_document.py
│   ├── cover_letter.py
│   ├── gmail_integration.py
│   ├── gmail_monitor.py
│   └── static\dashboard.html
├── data\agente.db
├── scripts\migrate_sqlite_to_supabase.py
├── tests
├── resumes
├── output
├── backups
└── PROJETO_STATUS.md
```

### Responsabilidade dos arquivos

- `app/main.py`: aplicação, endpoints e coordenação dos fluxos.
- `app/auth.py`: autenticação Supabase e cookie de sessão.
- `app/database.py`: escolha entre Supabase/PostgreSQL e SQLite.
- `app/models.py`: modelos e relacionamentos do banco.
- `app/analyzer.py`: score, forças, gaps e recomendação.
- `app/job_intake.py`: extração e normalização de texto de vaga.
- `app/job_quality.py`: separação de alertas, confiança por campo e barreira de qualidade.
- `app/job_file_intake.py`: leitura de prints e PDFs.
- `app/job_source_fetcher.py`: leitura segura de páginas públicas.
- `app/resume_importer.py`: importação de DOCX e PDF textual.
- `app/resume_personalizer.py`: adequação do conteúdo à vaga.
- `app/resume_generator.py`: construção do currículo personalizado.
- `app/resume_document.py`: layout e geração do DOCX.
- `app/cover_letter.py`: criação da carta de apresentação.
- `app/gmail_integration.py`: conexão OAuth e criptografia do token.
- `app/gmail_monitor.py`: consulta periódica, filtro e ingestão de mensagens.
- `app/static/dashboard.html`: interface atual.

## 8. Modelos persistidos

- `candidates`: perfil do candidato e currículo importado.
- `experiences`: experiências profissionais.
- `skills`: competências.
- `jobs`: vagas captadas.
- `job_analysis`: resultado detalhado da análise.
- `applications`: candidatura, scores e documentos.
- `application_events`: linha do tempo.
- `email_integrations`: integração Gmail e refresh token criptografado.
- `processed_email_messages`: mensagens já tratadas e resultado do processamento.

## 9. Variáveis de ambiente

Somente os nomes podem ficar documentados:

### Banco e autenticação

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `AUTH_REQUIRED`
- `COOKIE_SECURE`

### Google e Gmail

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `APP_BASE_URL`
- `TOKEN_ENCRYPTION_KEY`
- `OAUTH_STATE_SECRET`
- `GMAIL_AUTO_SYNC`
- `GMAIL_POLL_SECONDS`
- `GMAIL_INITIAL_DELAY_SECONDS`
- `GMAIL_MAX_RESULTS`
- `GMAIL_JOB_QUERY`

O instalador da versão 0.20.0 persistiu as variáveis do Gmail no escopo do usuário do Windows. Mesmo assim, validar a configuração em uma nova sessão antes de continuar.

## 10. Como iniciar amanhã

Abra um PowerShell novo e execute:

```powershell
Set-Location C:\agente_curriculos
.\.venv\Scripts\Activate.ps1
python -m py_compile app\main.py app\database.py app\gmail_integration.py app\gmail_monitor.py
python -m unittest discover -s tests -v
uvicorn app.main:app --reload --port 8001
```

Abrir:

- Dashboard: <http://127.0.0.1:8001/dashboard>
- Swagger: <http://127.0.0.1:8001/docs>

Para encerrar corretamente:

```text
Ctrl+C
```

### Verificação da configuração sem revelar valores

```powershell
$nomes = @(
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "TOKEN_ENCRYPTION_KEY"
)

foreach ($nome in $nomes) {
    $valor = [Environment]::GetEnvironmentVariable($nome, "User")
    if ([string]::IsNullOrWhiteSpace($valor)) {
        Write-Host "${nome}: AUSENTE"
    } else {
        Write-Host "${nome}: CONFIGURADA"
    }
}
```

Esse comando informa apenas se cada variável existe. Ele não mostra segredos.

## 11. Endpoints principais

| Método | Caminho | Finalidade |
|---|---|---|
| GET | `/` | Estado e versão da API |
| GET | `/dashboard` | Dashboard |
| POST | `/login` | Login Supabase |
| GET | `/me` | Usuário atual |
| POST | `/logout` | Encerrar sessão |
| GET | `/profile` | Consultar perfil |
| POST | `/profile/resume` | Importar currículo |
| POST | `/jobs` | Cadastrar vaga |
| GET | `/jobs` | Listar vagas |
| GET | `/jobs/{job_id}` | Consultar vaga |
| POST | `/intake/text` | Captar vaga por texto |
| POST | `/intake/file` | Captar por arquivo |
| POST | `/intake/file/preview` | Gerar prévia da captura |
| POST | `/intake/confirm` | Confirmar captura revisada |
| POST | `/jobs/{job_id}/analyze` | Analisar vaga cadastrada |
| POST | `/jobs/{job_id}/generate-document` | Gerar currículo personalizado |
| POST | `/jobs/{job_id}/cover-letter` | Gerar carta em texto |
| POST | `/jobs/{job_id}/cover-letter/document` | Gerar carta DOCX |
| GET | `/applications` | Listar candidaturas |
| GET | `/applications/{id}` | Consultar candidatura e eventos |
| PATCH | `/applications/{id}/status` | Atualizar andamento |
| GET | `/applications/{id}/document` | Baixar último currículo |
| GET | `/applications/{id}/cover-letter/document` | Baixar última carta |
| GET | `/auth/gmail/start` | Iniciar autorização Gmail |
| GET | `/auth/gmail/callback` | Retorno OAuth do Google |
| GET | `/auth/gmail/status` | Consultar conexão Gmail |
| POST | `/gmail/sync` | Buscar e-mails imediatamente |

## 12. Testes

A pasta `tests` contém **30 casos de teste** distribuídos em:

- `test_integrated_flow.py`: 10 testes de fluxo, documentos, histórico e dashboard.
- `test_job_source_fetcher.py`: 2 testes de páginas públicas e JSON-LD.
- `test_job_file_intake.py`: 4 testes de arquivos, limites e OCR.
- `test_job_intake.py`: 8 testes de extração, normalização e duplicidade.
- `test_job_quality.py`: 6 testes de separação, links e decisão de qualidade.
- `test_gmail_monitor.py`: 1 teste de conversão do HTML e preservação dos links.

Os 10 testes integrados foram executados com sucesso em 13/08/2026. Como houve evolução posterior até a versão 0.20.0, executar novamente a suíte completa na retomada.

```powershell
Set-Location C:\agente_curriculos
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
```

## 13. Histórico resumido

| Versão | Entrega principal |
|---|---|
| 0.5 | Fluxo integrado de análise, personalização e DOCX |
| 0.6 | Candidaturas e histórico persistente |
| 0.7 | Dashboard |
| 0.8 | Operações completas pelo dashboard |
| 0.9 | Persistência da carta de apresentação |
| 0.10 | Persistência do resultado completo da análise |
| 0.11 | Supabase PostgreSQL e autenticação |
| 0.12 | Isolamento multiusuário e RLS |
| 0.13 | Importação de currículo DOCX/PDF |
| 0.14 | Captação unificada por texto |
| 0.15 | Explicação detalhada do score |
| 0.16 | Captura por print/PDF e OCR local |
| 0.17 | Prévia e confirmação antes de cadastrar |
| 0.18 | Recuperação automática de páginas e confiança |
| 0.19 | OAuth Gmail individual e seguro |
| 0.20 | Monitor automático do Gmail |
| 0.21 | Separação de alertas e motor de qualidade por campo |
| 0.22 | Motor de decisão com gates de confiança, preferências e decisões AUTOMATICA/REVISAR/DESCARTAR |

## 14. Regras de segurança

1. Nunca colocar senhas, Client Secrets, tokens, chaves ou a URI completa do banco no Git, no Markdown ou em conversas.
2. Não publicar `.env`, `client_secret*.json`, arquivos de token ou backups do banco.
3. Manter o Gmail com o menor escopo possível: `gmail.readonly`.
4. Não contornar CAPTCHA nem mecanismos de segurança das plataformas.
5. Preferir APIs e integrações autorizadas.
6. Aplicar RLS e testar isolamento entre dois usuários antes da publicação.
7. Usar HTTPS e `COOKIE_SECURE=true` em produção.
8. Separar processo web e worker na nuvem.
9. Criptografar tokens e limitar acesso ao banco.
10. Criar exclusão de conta, exportação e retenção de dados compatíveis com LGPD.
11. Executar uma auditoria específica de segurança antes de aceitar usuários pagantes.

## 15. Backup

O código principal está em `C:\agente_curriculos`. Backups anteriores também existem em:

- `C:\agente_curriculos\backups`
- pasta `Documents` do usuário, em arquivos ZIP criados manualmente.

Não incluir `.venv` em backups comuns. Ela pode ser recriada. Priorizar:

- `app`
- `tests`
- `scripts`
- `data` somente em backup privado
- `resumes` somente em backup privado
- `PROJETO_STATUS.md`
- arquivos `requirements*.txt`, quando existirem

Credenciais devem ser recuperadas dos respectivos serviços ou guardadas separadamente em local protegido.

## 16. Instrução para outro assistente

Ao receber este documento:

1. não reconstruir o projeto do zero;
2. trabalhar sobre `C:\agente_curriculos`;
3. ler este arquivo e depois inspecionar os módulos relevantes;
4. não substituir arquivos inteiros sem comparar as alterações existentes;
5. preservar dados, currículos, autenticação e integrações;
6. nunca pedir que o usuário cole um segredo em uma conversa;
7. executar compilação e testes antes e depois de mudanças;
8. atualizar este documento após cada entrega relevante;
9. priorizar o motor de qualidade e decisão descrito na seção 4;
10. manter como objetivo a mínima interferência do usuário, sem violar regras ou segurança das plataformas.

## 17. Decisões de produto já tomadas

- O sistema deverá operar na nuvem 24 horas.
- O computador do usuário não poderá ser necessário para a automação final.
- O acesso deverá funcionar em celular e computador.
- O usuário fornecerá um currículo mestre uma única vez e poderá atualizá-lo.
- O sistema deverá personalizar currículo e carta para cada vaga.
- Prints e PDFs continuarão aceitos, mas não serão a única origem.
- Alertas por e-mail serão uma origem automática importante.
- O produto começará com serviços gratuitos e depois migrará para planos pagos de baixo custo.
- Pagamento deverá liberar o plano automaticamente por webhook no futuro.
- Segurança, invasão e vazamento de dados serão tratados antes do lançamento.
- O redesign visual será feito depois da consolidação do fluxo principal.
- Automação de alto volume não será o diferencial principal.
- O diferencial pretendido é autonomia com qualidade, explicação, contexto brasileiro e informações profissionais comprovadas.

### v0.22.0 — Motor de decisão

- `capture_confidence` ausente não permite `AUTOMATICA`.
- `capture_confidence < 80` resulta em `REVISAR`.
- Modalidade exigida mas ausente resulta em `REVISAR`.
- Localização exigida mas ausente resulta em `REVISAR`.
- `AUTOMATICA` somente ocorre quando todos os gates necessários passam.
- Motivos da decisão automática foram ampliados para registrar os gates relevantes.
- Backup realizado antes da alteração:
  - `backups\decision_engine_before_v0220.py`
  - `backups\test_decision_engine_before_v0220.py`
  - `backups\PROJETO_STATUS_before_v0220.md`
- Teste específico do motor de decisão executado com sucesso.
- Suíte completa do projeto executada com sucesso.
