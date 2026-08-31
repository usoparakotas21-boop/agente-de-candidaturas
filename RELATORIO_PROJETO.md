# JobPilot — Agente de Candidaturas

## Documentação completa do projeto

---

## 1. VISÃO GERAL

**JobPilot** é um agente de carreira que automatiza a captura, análise e gestão de vagas de emprego. O sistema:

- Captura vagas a partir de texto (manual, prints, e-mails)
- Analisa a qualidade e "saúde" da vaga (fraude, golpe, fantasma)
- Decide automaticamente se a vaga deve ser **aprovada**, **revisada** ou **descartada**
- Mantém uma fila de decisões para o usuário revisar
- Gera currículos e cartas personalizadas (em desenvolvimento)
- Gerencia candidaturas com histórico de status

---

## 2. ESTRUTURA DE DIRETÓRIOS

---

## 3. FUNCIONALIDADES IMPLEMENTADAS

### ? Concluídas e funcionando

| Funcionalidade | Descrição | Status |
|----------------|-----------|--------|
| **API FastAPI** | Servidor com rotas REST | ? |
| **Banco de dados** | SQLite (local) com suporte a PostgreSQL | ? |
| **Modelos** | `candidates`, `jobs`, `applications`, `queue_items`, etc. | ? |
| **Captura de vaga por texto** | `/intake/text` com extração de título, empresa, localização | ? |
| **Fila de decisão** | `queue_items` com status `PENDENTE`, `PROMOVIDO`, `RECUSADO` | ? |
| **Motor de decisão** | Decide entre `AUTOMATICA`, `REVISAR`, `DESCARTAR` | ? |
| **Saúde da vaga** | Avalia fraudes, golpes, qualidade do anúncio | ? |
| **Promoção automática** | Itens `REVISAR` viram `jobs` (quando aprovados) | ? |
| **Listagem da fila** | `/queue/` com paginação e filtros | ? |
| **Aprovação/Recusa** | `/queue/{id}/approve`, `/queue/{id}/reject` | ? |
| **Dashboard** | Página HTML com estatísticas e listas (modo local) | ? |
| **Jobs** | Listagem `/jobs` e criação via fila | ? |
| **Autenticação** | Desabilitada em modo local para facilitar testes | ? |

### ?? Em desenvolvimento ou pendentes

| Funcionalidade | Status |
|----------------|--------|
| **Extração a partir de prints/PDFs** | Parcial (OCR integrado, mas precisa de ajustes) |
| **Geração de currículo personalizado** | Código existe, mas não testado no fluxo atual |
| **Carta de apresentação** | Código existe, mas não testado |
| **Integração com Gmail** | Código existe, mas não ativado (requer configuração) |
| **Análise de aderência (score)** | Código existe, mas não está sendo usado no enfileiramento |
| **Testes automáticos** | Não implementados |

---

## 4. TECNOLOGIAS UTILIZADAS

- **Linguagem:** Python 3.11+
- **Framework:** FastAPI
- **ORM:** SQLAlchemy
- **Banco de Dados:** SQLite (local) / PostgreSQL (Supabase)
- **Processamento de documentos:** python-docx, PyPDF2, Pillow, pytesseract
- **Integração com APIs:** httpx, google-api-python-client, cryptography
- **Frontend:** HTML, CSS, JavaScript (puro, sem framework)

---

## 5. COMO EXECUTAR O PROJETO

### Pré-requisitos
- Python 3.11+ instalado
- Git (opcional)

### Passos

```powershell
# 1. Navegar até o diretório do projeto
cd C:\agente_curriculos

# 2. Ativar o ambiente virtual
.\.venv\Scripts\Activate.ps1

# 3. (Opcional) Instalar dependências
pip install -r requirements.txt

# 4. Iniciar o servidor
uvicorn app.main:app --port 8002 --reload

**Cole APENAS isso** no PowerShell (desde o `@'` até o final, incluindo o `'@ | Out-File ...`). O arquivo será criado.

@'
# JobPilot — Agente de Candidaturas

## Documentação completa do projeto

---

## 1. VISÃO GERAL

**JobPilot** é um agente de carreira que automatiza a captura, análise e gestão de vagas de emprego. O sistema:

- Captura vagas a partir de texto (manual, prints, e-mails)
- Analisa a qualidade e "saúde" da vaga (fraude, golpe, fantasma)
- Decide automaticamente se a vaga deve ser **aprovada**, **revisada** ou **descartada**
- Mantém uma fila de decisões para o usuário revisar
- Gera currículos e cartas personalizadas (em desenvolvimento)
- Gerencia candidaturas com histórico de status

---

## 2. ESTRUTURA DE DIRETÓRIOS
C:\agente_curriculos
+-- app/
¦ +-- main.py # Aplicação FastAPI (ponto de entrada)
¦ +-- models.py # Modelos SQLAlchemy (tabelas)
¦ +-- database.py # Conexão com banco (SQLite/PostgreSQL)
¦ +-- auth.py # Autenticação (desabilitada em modo local)
¦ +-- queue_service.py # Lógica da fila (enqueue, approve, reject)
¦ +-- queue_routes.py # Rotas da API para a fila (/queue/)
¦ +-- job_intake.py # Extração de dados da vaga (título, empresa, etc.)
¦ +-- job_quality.py # Avaliação de qualidade e decisão
¦ +-- job_health.py # Avaliação de saúde da vaga (fraude/golpe)
¦ +-- job_health_integration.py # Integração do health com a fila
¦ +-- job_source_fetcher.py # Busca de dados em páginas públicas
¦ +-- job_file_intake.py # OCR e leitura de prints/PDFs
¦ +-- gmail_integration.py # OAuth e integração com Gmail
¦ +-- gmail_monitor.py # Monitoramento automático de e-mails
¦ +-- analyzer.py # Análise de aderência e score
¦ +-- resume_.py # Importação, personalização e geração de currículos
¦ +-- cover_letter.py # Geração de carta de apresentação
¦ +-- static/
¦ +-- dashboard.html # Página do dashboard (modo local)
+-- data/
¦ +-- agente.db # Banco de dados SQLite (todos os dados)
+-- .venv/ # Ambiente virtual Python
+-- requirements.txt # Dependências do projeto
+-- PROJETO_STATUS.md # Status atual do projeto
+-- RELATORIO_PROJETO.md # Este documento

---

## 3. FUNCIONALIDADES IMPLEMENTADAS

### ? Concluídas e funcionando

| Funcionalidade | Descrição | Status |
|----------------|-----------|--------|
| **API FastAPI** | Servidor com rotas REST | ? |
| **Banco de dados** | SQLite (local) com suporte a PostgreSQL | ? |
| **Modelos** | `candidates`, `jobs`, `applications`, `queue_items`, etc. | ? |
| **Captura de vaga por texto** | `/intake/text` com extração de título, empresa, localização | ? |
| **Fila de decisão** | `queue_items` com status `PENDENTE`, `PROMOVIDO`, `RECUSADO` | ? |
| **Motor de decisão** | Decide entre `AUTOMATICA`, `REVISAR`, `DESCARTAR` | ? |
| **Saúde da vaga** | Avalia fraudes, golpes, qualidade do anúncio | ? |
| **Promoção automática** | Itens `REVISAR` viram `jobs` (quando aprovados) | ? |
| **Listagem da fila** | `/queue/` com paginação e filtros | ? |
| **Aprovação/Recusa** | `/queue/{id}/approve`, `/queue/{id}/reject` | ? |
| **Dashboard** | Página HTML com estatísticas e listas (modo local) | ? |
| **Jobs** | Listagem `/jobs` e criação via fila | ? |
| **Autenticação** | Desabilitada em modo local para facilitar testes | ? |

### ?? Em desenvolvimento ou pendentes

| Funcionalidade | Status |
|----------------|--------|
| **Extração a partir de prints/PDFs** | Parcial (OCR integrado, mas precisa de ajustes) |
| **Geração de currículo personalizado** | Código existe, mas não testado no fluxo atual |
| **Carta de apresentação** | Código existe, mas não testado |
| **Integração com Gmail** | Código existe, mas não ativado (requer configuração) |
| **Análise de aderência (score)** | Código existe, mas não está sendo usado no enfileiramento |
| **Testes automáticos** | Não implementados |

---

## 4. TECNOLOGIAS UTILIZADAS

- **Linguagem:** Python 3.11+
- **Framework:** FastAPI
- **ORM:** SQLAlchemy
- **Banco de Dados:** SQLite (local) / PostgreSQL (Supabase)
- **Processamento de documentos:** python-docx, PyPDF2, Pillow, pytesseract
- **Integração com APIs:** httpx, google-api-python-client, cryptography
- **Frontend:** HTML, CSS, JavaScript (puro, sem framework)

---

## 5. COMO EXECUTAR O PROJETO

### Pré-requisitos
- Python 3.11+ instalado
- Git (opcional)

### Passos

```powershell
# 1. Navegar até o diretório do projeto
cd C:\agente_curriculos

# 2. Ativar o ambiente virtual
.\.venv\Scripts\Activate.ps1

# 3. (Opcional) Instalar dependências
pip install -r requirements.txt

# 4. Iniciar o servidor
uvicorn app.main:app --port 8002 --reload

**Parte 2 (copie e cole após a primeira parte):**

```powershell
@'

---

## 6. PRÓXIMOS PASSOS RECOMENDADOS

### ?? Prioridade alta

1. **Corrigir aprovação via API**  
   - Ajustar `queue_routes.py` para passar `owner_id=None` corretamente.
   - Testar `POST /queue/{id}/approve` no Swagger.

2. **Integrar análise de aderência (score)**  
   - Chamar `analyze_job` durante o enfileiramento.
   - Salvar `score` no `queue_items`.

3. **Validar extração de título/empresa em diferentes formatos**  
   - Testar com textos reais de vagas (LinkedIn, Gupy, etc.).

### ?? Prioridade média

4. **Melhorar o design do dashboard**  
   - Aplicar templates como Tailwind UI, Cruip ou Horizon UI.
   - Adicionar gráficos e métricas visuais.

5. **Criar testes automáticos**  
   - Unit tests para `job_quality`, `job_health`, `queue_service`.
   - Testes de integração para os endpoints principais.

6. **Configurar autenticação real**  
   - Ativar Supabase Auth para múltiplos usuários.
   - Separar dados por `owner_id` com RLS.

### ?? Prioridade baixa (futuro)

7. **Integrar com Gmail automaticamente**  
   - Configurar variáveis de ambiente (`GMAIL_AUTO_SYNC=true`).
   - Testar com e-mails reais.

8. **Hospedar em nuvem**  
   - Railway, Heroku ou Fly.io.
   - Configurar banco PostgreSQL no Supabase.

9. **Adicionar envio de candidaturas**  
   - Automatizar o preenchimento de formulários (após as camadas de qualidade).

---

## 7. HISTÓRICO DE DESENVOLVIMENTO (RESUMIDO)

| Data | Marco |
|------|-------|
| Ago/2026 | Criação do projeto com FastAPI e SQLite |
| Ago/2026 | Implementação dos modelos iniciais (candidates, jobs, applications) |
| Ago/2026 | Adição do motor de decisão e fila (`queue_items`) |
| Ago/2026 | Desenvolvimento da saúde da vaga (`job_health.py`) |
| Ago/2026 | Melhorias na extração de título/empresa (`parse_job_text`) |
| Ago/2026 | Desativação da autenticação para testes locais |
| Ago/2026 | Criação do dashboard sem login |
| Ago/2026 | Teste completo do fluxo: captura ? fila ? aprovação ? job criado |

---

## 8. PROBLEMAS CONHECIDOS E SOLUÇÕES

| Problema | Solução adotada |
|----------|-----------------|
| Autenticação bloqueava rotas da fila | Desabilitamos o middleware e usamos `owner_id="local_user"` |
| Parsing de JSON no PowerShell | Usamos Swagger ou scripts Python para testes |
| `owner_id` nulo na fila | Fallback para `"local_user"` |
| Título e empresa não extraídos corretamente | Reescrevemos `parse_job_text` com novos padrões |
| Dashboard com tela de login | Substituímos por versão local sem autenticação |

---

## 9. COMO CONTRIBUIR / RETOMAR O PROJETO

1. Leia este documento.
2. Execute o servidor localmente.
3. Teste os endpoints principais via Swagger.
4. Se for modificar código, **faça backup** antes.
5. Documente as alterações no `PROJETO_STATUS.md`.

---

**Última atualização:** 17/08/2026  
**Versão:** 0.24.0 (modo local)  
**Autor:** Paulo Henrique Santos Oliveira
