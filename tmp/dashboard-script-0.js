
    async function initializeAuth() {
      try {
        const response = await fetch("/auth/me");
        if (!response.ok) {
          if (response.status === 403) {
            const detail = await response.json().catch(() => ({}));
            if (detail.code === "email_not_verified") {
              window.location.href = "/auth/verification-required";
              return;
            }
          }
          $("authGate").hidden = false;
          showAuthMode("login");
          return;
        }

        const payload = await response.json();
        $("authGate").hidden = true;
        $("appShell").hidden = false;
        if (payload.user) {
          $("userEmail").textContent = payload.user.email || "Usuario autenticado";
          $("logoutButton").hidden = false;
        }
        const requestedApplication = new URLSearchParams(window.location.search).get("application_id");
        if (requestedApplication) {
          // Open a clear loading state immediately so navigation from Minhas candidaturas
          // never looks like it returned to the dashboard by mistake.
          showApplicationLoading();
          window.history.replaceState({}, "", "/dashboard");
        }
        await Promise.all([loadApplications(), loadQueue(), loadGmailStatus(), loadDocumentExport()]);
        const requestedItem = applications.find(item => String(item.id) === String(requestedApplication || ""));
        if (requestedItem) {
          openApplication(requestedItem.id);
        } else if (requestedApplication) {
          closeDrawer();
          toast("Não foi possível localizar essa candidatura.");
        }
        if (new URLSearchParams(window.location.search).get("gmail") === "connected") {
          window.history.replaceState({}, "", "/dashboard");
          toast("Gmail conectado com sucesso.");
        }
      } catch {
        $("authGate").hidden = false;
        $("loginError").textContent = "Nao foi possivel verificar o login.";
      }
    }

    function showAuthMode(mode) {
      const signup = mode === "signup";
      $("loginForm").hidden = signup;
      $("signupForm").hidden = !signup;
      $("showLoginTab").classList.toggle("active", !signup);
      $("showSignupTab").classList.toggle("active", signup);
      $("loginError").textContent = "";
      $("signupError").textContent = "";
    }

    async function completeAuthRedirect() {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      const accessToken = fragment.get("access_token");
      const refreshToken = fragment.get("refresh_token");
      if (!accessToken) return false;
      const recovery = fragment.get("type") === "recovery";
      try {
        const response = await fetch("/auth/session", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({
            access_token: accessToken,
            refresh_token: refreshToken,
            expires_in: Number(fragment.get("expires_in") || 3600),
          }),
        });
        if (!response.ok) throw new Error(await responseError(response, "Link inválido ou expirado."));
        window.history.replaceState({}, "", window.location.pathname);
        if (recovery) {
          await initializeAuth();
          $("resetPasswordDialog").showModal();
        }
        return true;
      } catch (error) {
        window.history.replaceState({}, "", window.location.pathname);
        $("authGate").hidden = false;
        $("loginError").textContent = error.message;
        return false;
      }
    }

    async function bootstrapAuth() {
      await completeAuthRedirect();
      if (!$("resetPasswordDialog").open) await initializeAuth();
    }

    async function loadGmailStatus() {
      const button = $("gmailButton");
      button.disabled = true;
      try {
        const response = await fetch("/auth/gmail/status");
        if (!response.ok) throw new Error("status indisponivel");
        const payload = await response.json();
        button.hidden = !payload.configured;
        $("gmailSyncButton").hidden = !payload.connected;
        if (payload.connected) {
          button.textContent = payload.email
            ? `Gmail: ${payload.email}`
            : "Gmail conectado";
          button.title = "Clique para autorizar novamente esta conta";
        } else {
          button.textContent = "Conectar Gmail";
          button.title = "Autorizar leitura das oportunidades recebidas por e-mail";
        }
      } catch {
        button.hidden = true;
      } finally {
        button.disabled = false;
      }
    }

    async function syncGmailNow() {
      const button = $("gmailSyncButton");
      button.disabled = true;
      button.textContent = "Buscando...";
      try {
        const response = await fetch("/auth/gmail/sync", {method: "POST"});
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Nao foi possivel consultar o Gmail.");
        }
        await loadApplications();
        toast(
          `${payload.captured} vaga(s) capturada(s), ${payload.review || 0} para revisar, ` +
          `${payload.duplicate} repetida(s) e ${payload.ignored} ignorada(s) ` +
          `(de ${payload.found || 0} e-mail(s) encontrados).`
        );
      } catch (error) {
        toast(error.message);
      } finally {
        button.disabled = false;
        button.textContent = "Buscar e-mails";
      }
    }

    async function login(event) {
      event.preventDefault();
      $("loginButton").disabled = true;
      $("loginError").textContent = "";
      $("loginStatus").textContent = "";
      try {
        const response = await fetch("/auth/login", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            email: $("loginEmail").value.trim(),
            password: $("loginPassword").value,
          }),
        });
        if (!response.ok) throw new Error(await responseError(response, "E-mail ou senha inválidos."));
        $("loginPassword").value = "";
        await initializeAuth();
      } catch (error) {
        $("loginError").textContent = error.message;
      } finally {
        $("loginButton").disabled = false;
      }
    }

    async function signup(event) {
      event.preventDefault();
      $("signupError").textContent = "";
      $("signupStatus").textContent = "";
      if ($("signupPassword").value !== $("signupPasswordConfirm").value) {
        $("signupError").textContent = "As senhas não coincidem.";
        return;
      }
      $("signupButton").disabled = true;
      try {
        const response = await fetch("/auth/signup", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({
            name: $("signupName").value.trim(),
            email: $("signupEmail").value.trim(),
            password: $("signupPassword").value,
          }),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível criar a conta."));
        const payload = await response.json();
        $("signupPassword").value = "";
        $("signupPasswordConfirm").value = "";
        $("signupStatus").textContent = payload.message;
        if (payload.authenticated) await initializeAuth();
      } catch (error) {
        $("signupError").textContent = error.message;
      } finally {
        $("signupButton").disabled = false;
      }
    }

    async function forgotPassword() {
      const email = $("loginEmail").value.trim() || $("signupEmail").value.trim();
      if (!email) {
        $("loginError").textContent = "Informe seu e-mail primeiro.";
        showAuthMode("login");
        return;
      }
      $("loginError").textContent = "";
      try {
        const response = await fetch("/auth/forgot-password", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({email}),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível solicitar a recuperação."));
        const payload = await response.json();
        $("loginStatus").textContent = payload.message;
      } catch (error) {
        $("loginError").textContent = error.message;
      }
    }

    async function resendConfirmation() {
      const email = $("signupEmail").value.trim();
      if (!email) {
        $("signupError").textContent = "Informe o e-mail do cadastro.";
        return;
      }
      $("signupError").textContent = "";
      try {
        const response = await fetch("/auth/resend-confirmation", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({email}),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível reenviar a confirmação."));
        const payload = await response.json();
        $("signupStatus").textContent = payload.message;
      } catch (error) {
        $("signupError").textContent = error.message;
      }
    }

    async function saveNewPassword(event) {
      event.preventDefault();
      $("resetPasswordError").textContent = "";
      if ($("newPassword").value !== $("newPasswordConfirm").value) {
        $("resetPasswordError").textContent = "As senhas não coincidem.";
        return;
      }
      $("saveNewPassword").disabled = true;
      try {
        const response = await fetch("/auth/password", {
          method: "PUT",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({password: $("newPassword").value}),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível alterar a senha."));
        $("resetPasswordDialog").close();
        $("resetPasswordForm").reset();
        toast("Senha alterada com sucesso.");
      } catch (error) {
        $("resetPasswordError").textContent = error.message;
      } finally {
        $("saveNewPassword").disabled = false;
      }
    }

    async function logout() {
      await fetch("/auth/logout", {method: "POST"});
      applications = [];
      queueItems = [];
      selectedQueueIds.clear();
      selectedId = null;
      $("appShell").hidden = true;
      $("authGate").hidden = false;
      $("userEmail").textContent = "";
      $("logoutButton").hidden = true;
      showAuthMode("login");
    }

    const statusLabels = {
      IDENTIFICADA: "Identificada", ANALISADA: "Analisada", PERSONALIZADA: "Personalizada",
      CURRICULO_GERADO: "Currículo gerado", CANDIDATURA_ENVIADA: "Candidatura enviada",
      ENTREVISTA: "Entrevista", APROVADO: "Aprovado", RECUSADO: "Recusado", ARQUIVADA: "Arquivada"
    };
    const decisionLabels = {AUTOMATICA: "Automática", CAPTURAR: "Capturar", REVISAR: "Revisar", DESCARTAR: "Descartar"};
    const statuses = Object.keys(statusLabels);
    let applications = [];
    let queueItems = [];
    let queuePage = 1;
    let queuePageSize = 10;
    let queueSummary = {};
    const selectedQueueIds = new Set();
    let selectedId = null;
    let capturePreview = null;
    let documentExport = {allowed: false, price: "", checkout_url: "", checkout_ready: false};
    const analysisCache = {};

    const $ = id => document.getElementById(id);
    const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const formatDate = value => value ? new Intl.DateTimeFormat("pt-BR", {day:"2-digit", month:"short", year:"numeric"}).format(new Date(value)) : "—";
    const scoreClass = score => score == null ? "" : score >= 85 ? "high" : score >= 55 ? "mid" : "low";
    const badgeClass = status => ({APROVADO:"green", ENTREVISTA:"amber", RECUSADO:"red", ARQUIVADA:"gray", CURRICULO_GERADO:"blue", CANDIDATURA_ENVIADA:"blue"}[status] || "gray");
    const decisionBadgeClass = decision => ({AUTOMATICA:"green", CAPTURAR:"green", REVISAR:"amber", DESCARTAR:"red"}[decision] || "gray");
    const csvValues = value => String(value || "").split(/[,;\n]/).map(item => item.trim()).filter(Boolean);
    function applicationPlatform(url) {
      try {
        const host = new URL(url).hostname.toLowerCase();
        if (host.includes("indeed")) return ["Indeed", "Confira os campos e conclua o envio na página do Indeed."];
        if (host.includes("infojobs")) return ["InfoJobs", "Confira os campos e conclua o envio na página do InfoJobs."];
        if (host.includes("jobbol")) return ["Jobbol", "Confira os campos e conclua o envio na página do Jobbol."];
        if (host.includes("linkedin")) return ["LinkedIn", "Confira os campos e conclua o envio na página do LinkedIn."];
        return [host.replace(/^www\./, "") || "site da vaga", "Confira os campos e conclua o envio na página da empresa."];
      } catch { return ["site da vaga", "Confira os campos e conclua o envio na página da empresa."]; }
    }

    function populateStatusOptions() {
      statuses.forEach(status => {
        const option = document.createElement("option"); option.value = status; option.textContent = statusLabels[status];
        $("statusFilter").appendChild(option);
        $("newStatus").appendChild(option.cloneNode(true));
      });
    }

    async function loadApplications(showMessage = false) {
      $("refreshButton").disabled = true;
      try {
        const response = await fetch("/applications");
        if (!response.ok) throw new Error("Não foi possível carregar as candidaturas.");
        const payload = await response.json();
        applications = payload.applications || [];
        renderMetrics(); renderDistribution(); renderTable();
        if (selectedId) openApplication(selectedId);
        if (showMessage) toast("Dados atualizados.");
      } catch (error) { toast(error.message); }
      finally { $("refreshButton").disabled = false; }
    }

    async function loadDocumentExport() {
      try {
        const response = await fetch("/billing/document-export");
        if (!response.ok) return;
        documentExport = await response.json();
        $("generateButton").textContent = documentExport.allowed ? "Gerar e baixar currículo" : "Pré-visualizar currículo";
        const notice = $("documentExportNotice");
        if (!documentExport.allowed) {
          notice.hidden = false;
          notice.textContent = documentExport.price
            ? `Prévia gratuita ativa. O download do currículo + carta está disponível por pagamento avulso (${documentExport.price}).`
            : "Prévia gratuita ativa. O download do currículo + carta exige o plano Pro ou pagamento avulso.";
        }
      } catch { /* a prévia continua disponível mesmo sem carregar a oferta */ }
    }

    async function loadQueue(showMessage = false) {
      $("queueRefreshButton").disabled = true;
      const params = new URLSearchParams();
      if ($("queueDecisionFilter").value) params.set("decision", $("queueDecisionFilter").value);
      if ($("queueStatusFilter").value) params.set("status", $("queueStatusFilter").value);
      try {
        const suffix = params.toString() ? `?${params}` : "";
        const [itemsResponse, summaryResponse] = await Promise.all([
          fetch(`/queue/${suffix}`),
          fetch("/queue/summary"),
        ]);
        if (!itemsResponse.ok || !summaryResponse.ok) {
          throw new Error("Não foi possível carregar a fila.");
        }
        const payload = await itemsResponse.json();
        const summary = await summaryResponse.json();
        queueItems = payload.items || [];
        selectedQueueIds.clear();
        renderQueue(summary);
        if (showMessage) toast("Fila atualizada.");
      } catch (error) {
        toast(error.message);
      } finally {
        $("queueRefreshButton").disabled = false;
      }
    }

    function filteredQueueItems() {
      const query = $("queueSearchInput").value.trim().toLocaleLowerCase("pt-BR");
      if (!query) return queueItems;
      return queueItems.filter(item => `${item.title || ""} ${item.company || ""} ${(item.decision_reasons || []).join(" ")}`.toLocaleLowerCase("pt-BR").includes(query));
    }

    function renderQueuePagination(total, totalPages) {
      const pagination = $("queuePagination");
      if (!total) { pagination.innerHTML = ""; return; }
      const pages = [];
      const start = Math.max(1, Math.min(queuePage - 2, totalPages - 4));
      const end = Math.min(totalPages, Math.max(5, queuePage + 2));
      for (let page = start; page <= end; page += 1) pages.push(page);
      pagination.innerHTML = `<button class="queue-page-button" type="button" data-queue-page="1" aria-label="Primeira página" ${queuePage === 1 ? "disabled" : ""}>|&lt;</button><button class="queue-page-button" type="button" data-queue-page="${queuePage - 1}" aria-label="Página anterior" ${queuePage === 1 ? "disabled" : ""}>&lt;</button>${pages.map(page => `<button class="queue-page-button" type="button" data-queue-page="${page}" aria-label="Página ${page}" ${page === queuePage ? 'aria-current="page"' : ""}>${page}</button>`).join("")}<button class="queue-page-button" type="button" data-queue-page="${queuePage + 1}" aria-label="Próxima página" ${queuePage === totalPages ? "disabled" : ""}>&gt;</button><button class="queue-page-button" type="button" data-queue-page="${totalPages}" aria-label="Última página" ${queuePage === totalPages ? "disabled" : ""}>&gt;|</button>`;
      pagination.querySelectorAll("[data-queue-page]").forEach(button => button.addEventListener("click", () => {
        const nextPage = Number(button.dataset.queuePage);
        if (nextPage < 1 || nextPage > totalPages || nextPage === queuePage) return;
        queuePage = nextPage;
        selectedQueueIds.clear();
        renderQueue(queueSummary);
      }));
    }

    function renderQueue(summary) {
      queueSummary = summary;
      $("queueAutomaticToday").textContent = summary.automatica?.hoje || 0;
      $("queueReviewPending").textContent = summary.revisar?.pendente || 0;
      $("queueDiscardPending").textContent = summary.descartar?.pendente || 0;
      $("queueExpiredTotal").textContent = summary.expirado?.total || 0;
      const filtered = filteredQueueItems();
      const total = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / queuePageSize));
      queuePage = Math.min(queuePage, totalPages);
      const first = total ? ((queuePage - 1) * queuePageSize) : 0;
      const visible = filtered.slice(first, first + queuePageSize);
      $("queueRows").innerHTML = visible.map(item => {
        const pending = item.status === "PENDENTE";
        const reasons = (item.decision_reasons || []).slice(0, 3).join(" . ");
        const title = escapeHtml(item.title || "Cargo não identificado");
        const titleMarkup = item.url
          ? `<a class="job-title queue-job-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${title}</a>`
          : `<div class="job-title">${title}</div>`;
        return `
          <tr>
            <td><input class="queue-check queue-item-check" type="checkbox" data-id="${item.id}" aria-label="Selecionar ${escapeHtml(item.title || "item")}" ${pending ? "" : "disabled"}></td>
            <td>${titleMarkup}<div class="company">${escapeHtml(item.company || "Empresa não identificada")}</div><div class="queue-reasons">${escapeHtml(reasons || "Sem motivos registrados")}</div></td>
            <td><span class="badge ${decisionBadgeClass(item.decision)}">${decisionLabels[item.decision] || escapeHtml(item.decision)}</span></td>
            <td><span class="score ${scoreClass(item.confidence_overall)}">${item.confidence_overall == null ? "-" : item.confidence_overall + "%"}</span></td>
            <td><span class="badge ${queueStatusBadgeClass(item.status)}">${queueStatusLabel(item.status)}</span></td>
            <td><div class="queue-actions">${pending ? `
              <button class="queue-action approve" type="button" data-queue-action="approve" data-id="${item.id}">Aprovar</button>
              <button class="queue-action reject" type="button" data-queue-action="reject" data-id="${item.id}">Recusar</button>
            ` : "Resolvido"}</div></td>
          </tr>`;
      }).join("");
      $("queueEmptyState").hidden = total > 0;
      $("queueEmptyMessage").textContent = queueItems.length && !total ? "Nenhuma vaga corresponde aos filtros atuais." : "Novas oportunidades captadas aparecerão aqui.";
      $("queueEmptyCapture").hidden = queueItems.length > 0;
      if (total) {
        const last = Math.min(first + queuePageSize, total);
        $("queuePageSummary").textContent = `Mostrando ${first + 1}–${last} de ${total} vaga${total === 1 ? "" : "s"}`;
      } else {
        $("queuePageSummary").textContent = "Nenhuma vaga para exibir";
      }
      renderQueuePagination(total, totalPages);
      $("queueSelectAll").checked = false;
      updateQueueBulkBar();

      document.querySelectorAll(".queue-item-check").forEach(input => {
        input.addEventListener("change", () => {
          const id = Number(input.dataset.id);
          input.checked ? selectedQueueIds.add(id) : selectedQueueIds.delete(id);
          updateQueueBulkBar();
        });
      });
      document.querySelectorAll("[data-queue-action]").forEach(button => {
        button.addEventListener("click", () => queueAction(Number(button.dataset.id), button.dataset.queueAction));
      });
    }

    const queueStatusLabel = status => ({PENDENTE:"Pendente", PROMOVIDO:"Aprovado", RECUSADO:"Recusado", EXPIRADO:"Expirado"}[status] || status);
    const queueStatusBadgeClass = status => ({PENDENTE:"amber", PROMOVIDO:"green", RECUSADO:"red", EXPIRADO:"gray"}[status] || "gray");

    function updateQueueBulkBar() {
      const count = selectedQueueIds.size;
      $("queueBulkBar").hidden = count === 0;
      $("queueSelectedCount").textContent = `${count} ${count === 1 ? "item selecionado" : "itens selecionados"}`;
    }

    async function queueAction(id, action) {
      const verb = action === "approve" ? "aprovar" : "recusar";
      if (!window.confirm(`Deseja ${verb} esta oportunidade?`)) return;
      let body;
      if (action === "reject") {
        const reason = window.prompt("Motivo da recusa (opcional):", "") ?? "";
        body = JSON.stringify({reason});
      }
      try {
        const response = await fetch(`/queue/${id}/${action}`, {
          method: "POST",
          headers: body ? {"Content-Type":"application/json"} : undefined,
          body,
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível atualizar a fila."));
        await Promise.all([loadQueue(), loadApplications()]);
        toast(action === "approve" ? "Oportunidade aprovada." : "Oportunidade recusada.");
      } catch (error) {
        toast(error.message);
      }
    }

    async function queueBulkAction(action) {
      const ids = [...selectedQueueIds];
      if (!ids.length) return;
      const verb = action === "approve" ? "aprovar" : "recusar";
      if (!window.confirm(`Deseja ${verb} ${ids.length} oportunidade(s)?`)) return;
      try {
        const response = await fetch("/queue/bulk", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ids, action}),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível processar a seleção."));
        const payload = await response.json();
        const failures = (payload.results || []).filter(item => !item.success).length;
        await Promise.all([loadQueue(), loadApplications()]);
        toast(failures ? `Concluído com ${failures} falha(s).` : "Seleção processada.");
      } catch (error) {
        toast(error.message);
      }
    }

    function renderMetrics() {
      $("totalMetric").textContent = applications.length;
      $("automaticMetric").textContent = applications.filter(item => item.queue_decision === "AUTOMATICA").length;
      $("reviewMetric").textContent = applications.filter(item => item.queue_decision === "REVISAR").length;
      $("discardMetric").textContent = applications.filter(item => item.queue_decision === "DESCARTAR").length;
    }

    function renderDistribution() {
      const active = statuses.map(status => ({status, count: applications.filter(item => item.status === status).length})).filter(item => item.count > 0);
      const max = Math.max(...active.map(item => item.count), 1);
      $("distribution").innerHTML = active.length ? active.map(item => `
        <div class="dist-row"><div class="dist-meta"><span>${statusLabels[item.status]}</span><strong>${item.count}</strong></div>
        <div class="bar"><span style="width:${(item.count / max) * 100}%"></span></div></div>`).join("") : '<div class="empty">Sem dados para exibir.</div>';
    }

    function renderTable() {
      const query = $("searchInput").value.trim().toLocaleLowerCase("pt-BR");
      const status = $("statusFilter").value;
      const decision = $("decisionFilter").value;
      const filtered = applications.filter(item => {
        const text = `${item.company} ${item.job_title}`.toLocaleLowerCase("pt-BR");
        return (!query || text.includes(query)) && (!status || item.status === status) && (!decision || item.queue_decision === decision);
      });
      $("applicationRows").innerHTML = filtered.map(item => `
        <tr data-id="${item.id}" tabindex="0">
          <td><div class="job-title">${escapeHtml(item.job_title)}</div><div class="company">${escapeHtml(item.company)}</div></td>
          <td><span class="badge ${decisionBadgeClass(item.queue_decision)}">${decisionLabels[item.queue_decision] || "Revisar"}</span></td>
          <td><span class="badge ${badgeClass(item.status)}">${statusLabels[item.status] || escapeHtml(item.status)}</span></td>
          <td><span class="score ${scoreClass(item.analysis_score)}">${item.analysis_score == null ? "—" : Math.round(item.analysis_score)}</span></td>
          <td>${formatDate(item.updated_at)}</td>
        </tr>`).join("");
      $("emptyState").hidden = filtered.length > 0;
      document.querySelectorAll("#applicationRows tr").forEach(row => {
        row.addEventListener("click", () => openApplication(Number(row.dataset.id)));
        row.addEventListener("keydown", event => { if (event.key === "Enter") openApplication(Number(row.dataset.id)); });
      });
    }

    function openApplication(id) {
      const item = applications.find(entry => entry.id === id); if (!item) return;
      selectedId = id;
      setApplicationDrawerLoading(false);
      $("drawerStatus").textContent = statusLabels[item.status] || item.status;
      $("drawerStatus").className = `badge ${badgeClass(item.status)}`;
      $("drawerTitle").textContent = item.job_title;
      $("drawerCompany").textContent = item.company;
      const originalJobButton = $("openOriginalJob");
      originalJobButton.hidden = !item.job_url;
      originalJobButton.dataset.url = item.job_url || "";
      const actionCard = $("applicationActionCard");
      actionCard.hidden = !item.job_url || ["CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"].includes(item.status);
      $("startApplicationButton").dataset.url = item.job_url || "";
      const [platform, platformMessage] = applicationPlatform(item.job_url);
      $("applicationPlatformNote").textContent = item.job_url ? `Plataforma detectada: ${platform}. ${platformMessage}` : "";
      $("markApplicationSentButton").hidden = true;
      $("markApplicationSentButton").disabled = true;
      $("drawerScore").textContent = item.analysis_score == null ? "—" : Math.round(item.analysis_score);
      $("drawerPersonalization").textContent = item.personalization_score == null ? "—" : Math.round(item.personalization_score);
      $("drawerDecision").textContent = decisionLabels[item.queue_decision] || "Revisar";
      $("drawerRecommendation").textContent = item.recommendation || "Aguardando análise";
      const reasons = item.decision_reasons || [];
      $("decisionReasons").innerHTML = reasons.length
        ? reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")
        : "<li>Aguardando análise e preferências.</li>";
      $("downloadButton").hidden = !documentExport.allowed || !item.document_path;
      $("downloadSavedCoverLetterButton").hidden = !documentExport.allowed || !item.cover_letter_path;
      $("downloadCoverLetter").hidden = !documentExport.allowed;
      $("newStatus").value = item.status;
      $("statusNote").value = "";
      $("timeline").innerHTML = [...item.events].reverse().map(event => `
        <div class="event"><strong>${statusLabels[event.status] || escapeHtml(event.status)}</strong>
        <time>${formatDate(event.created_at)}</time>${event.note ? `<p>${escapeHtml(event.note)}</p>` : ""}</div>`).join("");
      renderAnalysis(item.id);
      $("drawer").classList.add("open"); $("backdrop").classList.add("open"); $("drawer").setAttribute("aria-hidden", "false");
    }

    function setApplicationDrawerLoading(loading) {
      const drawer = $("drawer");
      drawer.classList.toggle("loading", loading);
      drawer.setAttribute("aria-busy", loading ? "true" : "false");
      $("drawerLoadingMessage").hidden = !loading;
      ["analyzeButton", "generateButton", "coverLetterButton", "downloadButton", "downloadSavedCoverLetterButton", "saveStatus"].forEach(id => {
        $(id).disabled = loading;
      });
      $("openOriginalJob").disabled = loading;
      $("startApplicationButton").disabled = loading;
      $("markApplicationSentButton").disabled = loading || $("markApplicationSentButton").hidden;
      $("newStatus").disabled = loading;
      $("statusNote").disabled = loading;
    }

    function showApplicationLoading() {
      selectedId = null;
      $("drawerStatus").textContent = "Abrindo…";
      $("drawerStatus").className = "badge blue";
      $("drawerTitle").textContent = "Abrindo candidatura";
      $("drawerCompany").textContent = "Estamos carregando os detalhes da oportunidade.";
      $("openOriginalJob").hidden = true;
      $("openOriginalJob").dataset.url = "";
      $("applicationActionCard").hidden = true;
      $("startApplicationButton").dataset.url = "";
      $("applicationPlatformNote").textContent = "";
      $("markApplicationSentButton").hidden = true;
      $("markApplicationSentButton").disabled = true;
      $("drawerScore").textContent = "—";
      $("drawerPersonalization").textContent = "—";
      $("drawerDecision").textContent = "Carregando…";
      $("drawerRecommendation").textContent = "Aguarde só um instante.";
      $("decisionReasons").innerHTML = "<li>Buscando os dados da candidatura…</li>";
      $("timeline").innerHTML = "<div class=\"event\"><strong>Carregando detalhes</strong><p>A candidatura será exibida aqui em instantes.</p></div>";
      $("analysisCard").hidden = true;
      $("drawer").classList.add("open");
      $("backdrop").classList.add("open");
      $("drawer").setAttribute("aria-hidden", "false");
      setApplicationDrawerLoading(true);
    }

    function renderAnalysis(applicationId) {
      const item = applications.find(entry => entry.id === applicationId);
      const analysis = analysisCache[applicationId] || item?.analysis;
      $("analysisCard").hidden = !analysis;
      if (!analysis) return;
      const strengths = analysis.strengths || [];
      const gaps = analysis.gaps || [];
      $("strengthList").innerHTML = strengths.length ? strengths.map(item => `<li>${escapeHtml(item)}</li>`).join("") : "<li>Nenhum ponto forte listado.</li>";
      $("gapList").innerHTML = gaps.length ? gaps.map(item => `<li>${escapeHtml(item)}</li>`).join("") : "<li>Nenhum gap identificado.</li>";
      const breakdown = analysis.score_breakdown || {};
      const factors = [
        ["Requisitos", breakdown.requirements, 60, true],
        ["Experiência", breakdown.experience, 10, false],
        ["Senioridade", breakdown.seniority, 15, false],
        ["Tecnologia", breakdown.technology, 10, false],
        ["Localização", breakdown.location, 5, false]
      ];
      $("scoreBreakdown").innerHTML = factors.map(([label, value, maximum, wide]) => `
        <div class="score-factor ${wide ? "wide" : ""}">
          <span>${label}</span><strong>${value == null ? "—" : Number(value).toFixed(value % 1 ? 1 : 0)} / ${maximum}</strong>
        </div>`).join("");

      const evidenceLabels = {
        COMPROVADO_DIRETAMENTE: ["Evidência direta", "direct"],
        COMPROVADO_POR_EXPERIENCIA_RELACIONADA: ["Evidência relacionada", "related"],
        NAO_ENCONTRADO: ["Não encontrada", "missing"]
      };
      const requirements = analysis.requirements || [];
      $("requirementRows").innerHTML = requirements.length
        ? requirements.map(item => {
            const evidence = evidenceLabels[item.status] || [item.status, "missing"];
            return `<div class="requirement-row"><span>${escapeHtml(item.requirement)}</span><span class="evidence ${evidence[1]}">${evidence[0]}</span></div>`;
          }).join("")
        : '<div class="requirement-row"><span>Nenhum requisito específico identificado.</span></div>';
    }

    function closeDrawer() {
      $("drawer").classList.remove("open"); $("backdrop").classList.remove("open"); $("drawer").setAttribute("aria-hidden", "true");
      $("drawer").removeAttribute("aria-busy");
      setApplicationDrawerLoading(false);
    }

    async function saveStatus() {
      if (!selectedId) return;
      $("saveStatus").disabled = true;
      try {
        const response = await fetch(`/applications/${selectedId}/status`, {
          method: "PATCH", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({status: $("newStatus").value, note: $("statusNote").value.trim()})
        });
        if (!response.ok) throw new Error("Não foi possível atualizar a candidatura.");
        const updated = await response.json();
        applications = applications.map(item => item.id === updated.id ? updated : item);
        renderMetrics(); renderDistribution(); renderTable(); openApplication(updated.id); toast("Andamento atualizado.");
      } catch (error) { toast(error.message); }
      finally { $("saveStatus").disabled = false; }
    }

    async function responseError(response, fallback) {
      try { const payload = await response.json(); return payload.detail || fallback; }
      catch { return fallback; }
    }

    async function openProfile() {
      $("profileDialog").showModal();
      $("resumeFile").value = "";
      $("uploadProfileButton").disabled = false;
      $("uploadProfileButton").textContent = "Importar currículo";
      $("resumeFileLabel").textContent = "Currículo DOCX ou PDF textual (máximo 5 MB)";
      $("profileStatus").textContent = "Carregando perfil...";
      try {
        const response = await fetch("/profile");
        if (!response.ok) throw new Error("Não foi possível consultar o perfil.");
        const profile = await response.json();
        const hasResume = Boolean(profile.resume_filename);
        $("uploadProfileButton").textContent = hasResume ? "Substituir currículo" : "Importar currículo";
        $("resumeFileLabel").textContent = hasResume
          ? "Selecione um novo DOCX ou PDF para substituir o atual (máximo 5 MB)"
          : "Currículo DOCX ou PDF textual (máximo 5 MB)";
        $("profileStatus").textContent = profile.configured
          ? `${profile.name} • ${profile.experiences} experiências • ${profile.skills} competências • ${profile.resume_filename || "currículo ainda não importado"}`
          : "Nenhum currículo importado para este usuário.";
      } catch (error) {
        $("profileStatus").textContent = error.message;
      }
    }

    async function openPreferences() {
      $("preferencesDialog").showModal();
      $("preferencesStatus").textContent = "Carregando preferências...";
      try {
        const response = await fetch("/preferences");
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível consultar as preferências."));
        const preferences = await response.json();
        $("preferenceRoles").value = (preferences.target_roles || []).join(", ");
        $("preferenceLocations").value = (preferences.locations || []).join(", ");
        $("preferenceModalities").value = (preferences.modalities || []).join(", ");
        $("preferenceContracts").value = (preferences.contract_types || []).join(", ");
        $("preferenceSchedules").value = (preferences.schedules || []).join(", ");
        $("preferenceIndustries").value = (preferences.industries || []).join(", ");
        $("salaryMin").value = preferences.salary_min ?? "";
        $("salaryMax").value = preferences.salary_max ?? "";
        $("excludedCompanies").value = (preferences.excluded_companies || []).join(", ");
        $("requiredKeywords").value = (preferences.required_keywords || []).join(", ");
        $("excludedKeywords").value = (preferences.excluded_keywords || []).join(", ");
        $("minimumScore").value = preferences.minimum_score;
        $("automaticScore").value = preferences.automatic_score;
        $("maxDailyApplications").value = preferences.max_daily_applications;
        $("allowAutomatic").checked = Boolean(preferences.allow_automatic);
        $("preferencesStatus").textContent = preferences.allow_automatic
          ? "A classificação automática está autorizada. O envio continua desativado."
          : "As oportunidades continuarão aguardando revisão humana.";
      } catch (error) {
        $("preferencesStatus").textContent = error.message;
      }
    }

    async function savePreferences(event) {
      event.preventDefault();
      const payload = {
        target_roles: csvValues($("preferenceRoles").value),
        locations: csvValues($("preferenceLocations").value),
        modalities: csvValues($("preferenceModalities").value),
        contract_types: csvValues($("preferenceContracts").value),
        schedules: csvValues($("preferenceSchedules").value),
        industries: csvValues($("preferenceIndustries").value),
        salary_min: $("salaryMin").value ? Number($("salaryMin").value) : null,
        salary_max: $("salaryMax").value ? Number($("salaryMax").value) : null,
        excluded_companies: csvValues($("excludedCompanies").value),
        required_keywords: csvValues($("requiredKeywords").value),
        excluded_keywords: csvValues($("excludedKeywords").value),
        minimum_score: Number($("minimumScore").value),
        automatic_score: Number($("automaticScore").value),
        max_daily_applications: Number($("maxDailyApplications").value),
        allow_automatic: $("allowAutomatic").checked,
      };
      $("savePreferences").disabled = true;
      try {
        const response = await fetch("/preferences", {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível salvar as preferências."));
        const result = await response.json();
        await loadApplications();
        $("preferencesDialog").close();
        toast(`Preferências salvas. ${result.decisions_updated} decisão(ões) recalculada(s).`);
      } catch (error) {
        $("preferencesStatus").textContent = error.message;
      } finally {
        $("savePreferences").disabled = false;
      }
    }

    async function uploadProfile(event) {
      event.preventDefault();
      const file = $("resumeFile").files[0];
      if (!file) return;
      const data = new FormData();
      data.append("file", file);
      $("uploadProfileButton").disabled = true;
      $("profileStatus").textContent = "Validando e importando currículo...";
      try {
        const response = await fetch("/profile/resume", {method: "POST", body: data});
        if (!response.ok) {
          throw new Error(await responseError(response, "Não foi possível importar o currículo."));
        }
        const result = await response.json();
        $("profileStatus").textContent = `${result.name} • ${result.experiences} experiências • ${result.skills} competências importadas.`;
        $("resumeFile").value = "";
        $("profileButton").textContent = "Meu currículo ✓";
        $("profileDialog").close();
        toast("Currículo importado com segurança.");
      } catch (error) {
        $("profileStatus").textContent = error.message;
      } finally {
        $("uploadProfileButton").disabled = false;
      }
    }

    async function createJob(event) {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const payload = {
        source: "dashboard", external_id: `dashboard-${Date.now()}`,
        company: form.get("company").trim(), title: form.get("title").trim(),
        location: form.get("location").trim(), modality: form.get("modality"),
        salary: form.get("salary").trim(), url: "", description: form.get("description").trim()
      };
      $("submitJob").disabled = true;
      try {
        const response = await fetch("/jobs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível cadastrar a vaga."));
        const created = await response.json();
        $("newJobDialog").close(); $("newJobForm").reset(); selectedId = created.application.id;
        await loadApplications(); openApplication(selectedId); toast("Vaga cadastrada. Agora você pode analisá-la.");
      } catch (error) { toast(error.message); }
      finally { $("submitJob").disabled = false; }
    }

    function resetCaptureReview() {
      capturePreview = null;
      $("captureReview").hidden = true;
      $("captureFileField").hidden = false;
      $("captureTextField").hidden = false;
      $("submitCaptureJob").textContent = "Captar e analisar";
      $("captureStatus").textContent = "A vaga será cadastrada, filtrada e analisada.";
    }

    function showCaptureReview(preview) {
      capturePreview = preview;
      $("reviewCompany").value = preview.company || "";
      $("reviewTitle").value = preview.title || "";
      $("reviewLocation").value = preview.location || "";
      $("reviewModality").value = preview.modality || "";
      $("reviewSalary").value = preview.salary || "";
      $("reviewUrl").value = preview.url || "";
      $("reviewDescription").value = preview.description || "";
      $("captureFileField").hidden = true;
      $("captureTextField").hidden = true;
      $("captureReview").hidden = false;
      $("submitCaptureJob").textContent = "Confirmar e analisar";
      $("captureStatus").textContent = "Revise os campos. Nenhuma vaga foi salva ainda.";
    }

    async function captureJob(event) {
      event.preventDefault();
      const rawText = $("captureText").value.trim();
      const captureFile = $("captureFile").files[0];
      if (capturePreview) {
        const company = $("reviewCompany").value.trim();
        const title = $("reviewTitle").value.trim();
        if (!company || !title) {
          $("captureStatus").textContent = "Confira e preencha empresa e cargo.";
          return;
        }
        $("submitCaptureJob").disabled = true;
        $("captureStatus").textContent = "Salvando os dados confirmados e calculando o score...";
        try {
          const response = await fetch("/intake/confirm", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              external_id: capturePreview.external_id,
              source: capturePreview.source,
              company,
              title,
              location: $("reviewLocation").value.trim(),
              modality: $("reviewModality").value.trim(),
              salary: $("reviewSalary").value.trim(),
              url: $("reviewUrl").value.trim(),
              description: $("reviewDescription").value.trim(),
              auto_analyze: true
            })
          });
          if (!response.ok) throw new Error(await responseError(response, "Não foi possível confirmar a vaga."));
          const result = await response.json();
          $("captureJobDialog").close();
          $("captureJobForm").reset();
          resetCaptureReview();
          await loadApplications();
          if (result.application_id) {
            selectedId = result.application_id;
            openApplication(selectedId);
          }
          toast(result.updated ? "Vaga revisada e atualizada." : "Vaga revisada, cadastrada e analisada.");
        } catch (error) {
          $("captureStatus").textContent = error.message;
        } finally {
          $("submitCaptureJob").disabled = false;
        }
        return;
      }
      if (!rawText && !captureFile) {
        $("captureStatus").textContent = "Envie um print/PDF ou cole o texto da oportunidade.";
        return;
      }
      if (captureFile && captureFile.size > 10 * 1024 * 1024) {
        $("captureStatus").textContent = "O arquivo excede o limite de 10 MB.";
        return;
      }
      $("submitCaptureJob").disabled = true;
      $("captureStatus").textContent = captureFile
        ? "Lendo o arquivo e preparando os campos para revisão..."
        : "Identificando e analisando a oportunidade...";
      try {
        let response;
        if (captureFile) {
          const data = new FormData();
          data.append("file", captureFile);
          const params = new URLSearchParams({source: $("captureSource").value});
          response = await fetch(`/intake/file/preview?${params}`, {method: "POST", body: data});
        } else {
          response = await fetch("/intake/text", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              raw_text: rawText,
              source: $("captureSource").value,
              auto_analyze: true
            })
          });
        }
        if (!response.ok) {
          throw new Error(await responseError(response, "Não foi possível captar a vaga."));
        }
        const result = await response.json();
        if (captureFile) {
          if (result.automatic) {
            $("captureJobDialog").close();
            $("captureJobForm").reset();
            resetCaptureReview();
            await loadApplications();
            if (result.application_id) {
              selectedId = result.application_id;
              openApplication(selectedId);
            }
            toast(`Vaga captada automaticamente (${result.confidence}% de confiança).`);
            return;
          }
          showCaptureReview(result);
          return;
        }
        $("captureJobDialog").close();
        $("captureJobForm").reset();
        $("captureStatus").textContent = "A vaga será cadastrada, filtrada e analisada.";
        await loadApplications();
        if (result.application_id) {
          selectedId = result.application_id;
          openApplication(selectedId);
        }
        toast(result.duplicate ? "Essa vaga já estava no painel." : "Vaga captada e analisada automaticamente.");
      } catch (error) {
        $("captureStatus").textContent = error.message;
      } finally {
        $("submitCaptureJob").disabled = false;
      }
    }

    async function analyzeApplication() {
      const item = applications.find(entry => entry.id === selectedId); if (!item) return;
      $("analyzeButton").disabled = true;
      try {
        const response = await fetch(`/jobs/${item.job_id}/analyze`, {method:"POST"});
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível analisar a vaga."));
        const payload = await response.json();
        analysisCache[item.id] = payload.analysis;
        await loadApplications(); openApplication(item.id); toast(`Análise concluída: ${Math.round(payload.analysis.score)} pontos.`);
      } catch (error) { toast(error.message); }
      finally { $("analyzeButton").disabled = false; }
    }

    function saveBlob(blob, filename) {
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
async function generateCoverLetter() {
  const item = applications.find(
    entry => entry.id === selectedId
  );

  if (!item) {
    return;
  }

  $("coverLetterButton").disabled = true;

  try {
    const response = await fetch(
      `/jobs/${item.job_id}/cover-letter`,
      {
        method: "POST"
      }
    );

    if (!response.ok) {
      throw new Error(
        await responseError(
          response,
          "Não foi possível gerar a carta."
        )
      );
    }

    const payload = await response.json();

    $("coverLetterSubtitle").textContent =
      `${payload.company} — ${payload.job_title}`;

    $("coverLetterText").value = payload.letter;
    const locked = Boolean(payload.preview);
    const copyButton = $("copyCoverLetter");
    const downloadButton = $("downloadCoverLetter");
    const coverLetterText = $("coverLetterText");
    const notice = $("coverLetterNotice");
    copyButton.disabled = locked;
    downloadButton.disabled = locked;
    copyButton.textContent = locked ? "Copiar texto completo (Pro)" : "Copiar texto";
    downloadButton.textContent = locked ? "Baixar em Word (Pro)" : "Baixar em Word";
    coverLetterText.classList.toggle("preview-locked", locked);
    coverLetterText.setAttribute(
      "aria-label",
      locked ? "Prévia protegida da carta de apresentação" : "Texto completo da carta de apresentação",
    );
    notice.hidden = !locked;
    notice.textContent = payload.notice || "A cópia do texto completo fica disponível após o plano Pro ou pagamento avulso.";

    $("coverLetterDialog").showModal();

  } catch (error) {
    toast(error.message);

  } finally {
    $("coverLetterButton").disabled = false;
  }
}

async function downloadCoverLetterDocument() {
  const item = applications.find(
    entry => entry.id === selectedId
  );

  if (!item) {
    return;
  }

  $("downloadCoverLetter").disabled = true;

  try {
    const response = await fetch(
      `/jobs/${item.job_id}/cover-letter/document`,
      {
        method: "POST"
      }
    );

    if (!response.ok) {
      throw new Error(
        await responseError(
          response,
          "Não foi possível gerar o arquivo da carta."
        )
      );
    }

    const blob = await response.blob();

    const disposition =
      response.headers.get("content-disposition") || "";

    const filenameMatch = disposition.match(
      /filename="?([^";]+)"?/i
    );

    const filename = filenameMatch
      ? filenameMatch[1]
      : `Carta_Apresentacao_${item.company}.docx`;

    saveBlob(
      blob,
      filename
    );

    await loadApplications();

    toast("Carta enviada para download.");

  } catch (error) {
    toast(error.message);

  } finally {
    $("downloadCoverLetter").disabled = false;
  }
}

    function showResumePreview(payload) {
      const preview = payload.preview || {};
      $("resumePreviewSubtitle").textContent = `${payload.company || ""} — ${payload.job_title || ""}`;
      $("resumePreviewName").textContent = preview.name || "Candidato";
      $("resumePreviewHeadline").textContent = preview.headline || "";
      const contact = preview.contact || {};
      $("resumePreviewContact").textContent = [contact.email, contact.phone, contact.location].filter(Boolean).join("  ·  ");
      $("resumePreviewSummary").textContent = preview.summary || "";
      $("resumePreviewSkills").innerHTML = (preview.skills || []).map(skill => `<span class="resume-skill">${escapeHtml(skill)}</span>`).join("") || "<span>—</span>";
      $("resumePreviewExperiences").innerHTML = (preview.experiences || []).map(item => `<div class="resume-experience"><div><strong>${escapeHtml(item.role)}</strong><span>${escapeHtml(item.company)}</span></div><small>${escapeHtml(item.period)}</small></div>`).join("") || "—";
      const exportInfo = payload.export || documentExport;
      $("resumePreviewNotice").textContent = preview.notice || exportInfo.message || "O download completo exige pagamento.";
      const checkout = $("resumePreviewCheckout");
      checkout.hidden = !exportInfo.checkout_url && !exportInfo.checkout_ready;
      checkout.textContent = exportInfo.price ? `Liberar download (${exportInfo.price})` : "Liberar download";
      $("resumePreviewDialog").showModal();
    }

    async function startDocumentExportCheckout() {
      const checkout = $("resumePreviewCheckout");
      checkout.disabled = true;
      checkout.textContent = "Abrindo pagamento...";
      try {
        if (documentExport.checkout_url) {
          window.open(documentExport.checkout_url, "_blank", "noopener");
          return;
        }
        const response = await fetch("/billing/document-export/checkout", {method: "POST"});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "Não foi possível iniciar o pagamento.");
        window.open(payload.checkout_url, "_blank", "noopener");
      } catch (error) {
        toast(error.message);
      } finally {
        checkout.disabled = false;
        checkout.textContent = documentExport.price ? `Liberar download (${documentExport.price})` : "Liberar download";
      }
    }

    async function generateDocument() {
      const item = applications.find(entry => entry.id === selectedId); if (!item) return;
      $("generateButton").disabled = true;
      try {
        const response = await fetch(`/jobs/${item.job_id}/generate-document`, {method:"POST"});
        if (!response.ok) throw new Error(await responseError(response, "Não foi possível gerar o currículo."));
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          showResumePreview(await response.json());
          await loadApplications();
          openApplication(item.id);
          return;
        }
        const blob = await response.blob();
        const disposition = response.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="?([^";]+)"?/i);
        saveBlob(blob, match ? match[1] : `Curriculo_${item.job_title}.docx`);
        await loadApplications(); openApplication(item.id); toast("Currículo gerado e enviado para download.");
      } catch (error) { toast(error.message); }
      finally { $("generateButton").disabled = false; }
    }

    function downloadExistingDocument() {
      if (!selectedId) return;
      const link = document.createElement("a"); link.href = `/applications/${selectedId}/document`;
      document.body.appendChild(link); link.click(); link.remove();
    }

    function downloadSavedCoverLetter() {
      if (!selectedId) return;
      const link = document.createElement("a");
      link.href = `/applications/${selectedId}/cover-letter/document`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    }

    let toastTimer;
    function toast(message) { clearTimeout(toastTimer); $("toast").textContent = message; $("toast").classList.add("show"); toastTimer = setTimeout(() => $("toast").classList.remove("show"), 2600); }

    function navigateWorkspace(view) {
      document.querySelectorAll("[data-nav]").forEach(link => link.classList.toggle("active", link.dataset.nav === view));
      if (view === "dashboard") window.scrollTo({top: 0, behavior: "smooth"});
      if (view === "jobs") { window.location.assign("/vagas"); return; }
      if (view === "applications") window.location.assign("/candidaturas");
      if (view === "resume") window.location.assign("/curriculos");
      if (view === "integrations") $("gmailButton").click();
      if (view === "settings") window.location.assign("/configuracoes");
      if (view === "interviews") window.location.assign("/simulador");
      if (view === "support") toast("O suporte Pro será conectado ao seu canal de atendimento.");
    }

    populateStatusOptions();
    $("showLoginTab").addEventListener("click", () => showAuthMode("login"));
    $("showSignupTab").addEventListener("click", () => showAuthMode("signup"));
    $("loginForm").addEventListener("submit", login);
    $("signupForm").addEventListener("submit", signup);
    $("forgotPasswordButton").addEventListener("click", forgotPassword);
    $("resendConfirmationButton").addEventListener("click", resendConfirmation);
    $("resetPasswordForm").addEventListener("submit", saveNewPassword);
    $("closeResetPasswordDialog").addEventListener("click", () => $("resetPasswordDialog").close());
    $("cancelResetPassword").addEventListener("click", () => $("resetPasswordDialog").close());
    $("logoutButton").addEventListener("click", logout);
    document.querySelectorAll("[data-nav]").forEach(link => link.addEventListener("click", () => navigateWorkspace(link.dataset.nav)));
    $("searchInput").addEventListener("input", renderTable);
    $("statusFilter").addEventListener("change", renderTable);
    $("decisionFilter").addEventListener("change", renderTable);
    $("refreshButton").addEventListener("click", async () => {
      await Promise.all([loadApplications(), loadQueue()]);
      toast("Dados atualizados.");
    });
    $("queueRefreshButton").addEventListener("click", () => loadQueue(true));
    $("queueDecisionFilter").addEventListener("change", () => { queuePage = 1; loadQueue(); });
    $("queueStatusFilter").addEventListener("change", () => { queuePage = 1; loadQueue(); });
    $("queueSearchInput").addEventListener("input", () => { queuePage = 1; selectedQueueIds.clear(); renderQueue(queueSummary); });
    $("queuePageSize").addEventListener("change", event => { queuePageSize = Number(event.currentTarget.value) || 10; queuePage = 1; selectedQueueIds.clear(); renderQueue(queueSummary); });
    $("queueEmptyCapture").addEventListener("click", () => {
      document.querySelector(".hero-menu")?.removeAttribute("open");
      resetCaptureReview();
      $("captureJobDialog").showModal();
    });
    $("queueSelectAll").addEventListener("change", event => {
      selectedQueueIds.clear();
      document.querySelectorAll(".queue-item-check:not(:disabled)").forEach(input => {
        input.checked = event.currentTarget.checked;
        if (input.checked) selectedQueueIds.add(Number(input.dataset.id));
      });
      updateQueueBulkBar();
    });
    $("queueBulkApprove").addEventListener("click", () => queueBulkAction("approve"));
    $("queueBulkReject").addEventListener("click", () => queueBulkAction("reject"));
    $("gmailButton").addEventListener("click", () => {
      window.location.assign("/auth/gmail/start");
    });
    $("gmailSyncButton").addEventListener("click", syncGmailNow);
    $("profileButton").addEventListener("click", () => { document.querySelector(".hero-menu")?.removeAttribute("open"); openProfile(); });
    $("preferencesButton").addEventListener("click", () => { document.querySelector(".hero-menu")?.removeAttribute("open"); openPreferences(); });
    $("closePreferencesDialog").addEventListener("click", () => $("preferencesDialog").close());
    $("cancelPreferences").addEventListener("click", () => $("preferencesDialog").close());
    $("preferencesForm").addEventListener("submit", savePreferences);
    $("closeProfileDialog").addEventListener("click", () => $("profileDialog").close());
    $("cancelProfile").addEventListener("click", () => $("profileDialog").close());
    $("profileForm").addEventListener("submit", uploadProfile);
    $("captureJobButton").addEventListener("click", () => {
      document.querySelector(".hero-menu")?.removeAttribute("open");
      resetCaptureReview();
      $("captureJobDialog").showModal();
    });
    $("closeCaptureJobDialog").addEventListener("click", () => {
      $("captureJobForm").reset();
      resetCaptureReview();
      $("captureJobDialog").close();
    });
    $("cancelCaptureJob").addEventListener("click", () => {
      $("captureJobForm").reset();
      resetCaptureReview();
      $("captureJobDialog").close();
    });
    $("captureJobForm").addEventListener("submit", captureJob);
    $("newJobButton").addEventListener("click", () => $("newJobDialog").showModal());
    $("closeJobDialog").addEventListener("click", () => $("newJobDialog").close());
    $("cancelJob").addEventListener("click", () => $("newJobDialog").close());
    $("newJobForm").addEventListener("submit", createJob);
    $("closeDrawer").addEventListener("click", closeDrawer);
    $("backdrop").addEventListener("click", closeDrawer);
    $("saveStatus").addEventListener("click", saveStatus);
    $("openOriginalJob").addEventListener("click", () => {
      const url = $("openOriginalJob").dataset.url;
      if (url) window.open(url, "_blank", "noopener");
    });
    $("startApplicationButton").addEventListener("click", () => {
      const url = $("startApplicationButton").dataset.url;
      if (!url) return;
      window.open(url, "_blank", "noopener");
      $("markApplicationSentButton").hidden = false;
      $("markApplicationSentButton").disabled = false;
      toast("Anúncio aberto. Depois de enviar, atualize o andamento para Candidatura enviada.");
    });
    $("markApplicationSentButton").addEventListener("click", () => {
      if (!selectedId) return;
      $("newStatus").value = "CANDIDATURA_ENVIADA";
      $("statusNote").value = "Candidatura enviada pelo anúncio original.";
      saveStatus();
    });
    $("analyzeButton").addEventListener("click", analyzeApplication);
    $("generateButton").addEventListener("click", generateDocument);
   $("coverLetterButton").addEventListener(
  "click",
  generateCoverLetter
);

$("closeCoverLetter").addEventListener(
  "click",
  () => $("coverLetterDialog").close()
);

$("finishCoverLetter").addEventListener(
  "click",
  () => $("coverLetterDialog").close()
);

$("copyCoverLetter").addEventListener(
  "click",
  async () => {
    if ($("copyCoverLetter").disabled) {
      toast("A cópia do texto completo exige o plano Pro ou pagamento avulso.");
      return;
    }
    const letter = $("coverLetterText").value;

    await navigator.clipboard.writeText(letter);

    toast("Carta copiada.");
  }
);
    $("downloadCoverLetter").addEventListener(
  "click",
  downloadCoverLetterDocument
);

    ["copy", "cut", "selectstart", "contextmenu"].forEach(eventName => {
      $("coverLetterText").addEventListener(eventName, event => {
        if ($("coverLetterText").classList.contains("preview-locked")) {
          event.preventDefault();
        }
      });
    });
    $("coverLetterText").addEventListener("keydown", event => {
      if (
        $("coverLetterText").classList.contains("preview-locked") &&
        (event.ctrlKey || event.metaKey) &&
        ["c", "x"].includes(event.key.toLowerCase())
      ) {
        event.preventDefault();
        toast("A cópia do texto completo exige o plano Pro ou pagamento avulso.");
      }
    });
    $("closeResumePreview").addEventListener("click", () => $("resumePreviewDialog").close());
    $("finishResumePreview").addEventListener("click", () => $("resumePreviewDialog").close());
    $("resumePreviewCheckout").addEventListener("click", startDocumentExportCheckout);
    $("downloadButton").addEventListener("click", downloadExistingDocument);
    $("downloadSavedCoverLetterButton").addEventListener(
      "click",
      downloadSavedCoverLetter
    );
    document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
    bootstrapAuth();
  
