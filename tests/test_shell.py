import unittest
import re
from pathlib import Path

from app import main as main_module


class ShellLayoutTest(unittest.TestCase):
    def test_active_shells_reference_brand_favicon(self):
        dashboard = main_module._page(Path(main_module.DASHBOARD_PATH)).body.decode("utf-8")
        security = main_module._page(Path(main_module.SECURITY_PAGE_PATH)).body.decode("utf-8")
        landing = main_module.root().body.decode("utf-8")
        expected = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">'
        for html in (dashboard, security, landing):
            self.assertIn(expected, html)
        self.assertIn('fill="#092f56"', (Path(main_module.STATIC_DIR) / "favicon.svg").read_text(encoding="utf-8"))

    def test_dashboard_keeps_its_own_header_without_global_duplicate(self):
        response = main_module._page(Path(main_module.DASHBOARD_PATH))
        html = response.body.decode("utf-8")
        self.assertEqual(html.count('<nav class="global-nav">'), 0)
        self.assertIn('<header class="topbar">', html)
        self.assertIn('id="userEmail"', html)

    def test_subpages_keep_the_single_global_navigation_shell(self):
        response = main_module._page(Path(main_module.SECURITY_PAGE_PATH))
        html = response.body.decode("utf-8")
        self.assertEqual(html.count('<nav class="global-nav">'), 1)
        self.assertNotIn('<header class="top">', html)

    def test_active_templates_do_not_require_inline_style_attributes(self):
        templates = [
            path for path in Path(main_module.STATIC_DIR).glob("*.html")
            if "_backup" not in path.name
        ]
        for path in templates:
            html = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\sstyle\s*=", html, re.IGNORECASE),
                msg=f"template ainda contém atributo style inline: {path.name}",
            )

    def test_global_fetch_feedback_preserves_http_error_responses(self):
        script = (Path(main_module.STATIC_DIR) / "ui-feedback.js").read_text(encoding="utf-8")
        self.assertNotIn("if(!r.ok)throw r", script)
        self.assertIn("if(!r.ok){hide();return r}", script)
        self.assertIn("bar.setAttribute('aria-hidden','true')", script)
        self.assertIn("return r", script)

    def test_resume_upload_dropzone_selector_is_valid(self):
        html = (Path(main_module.STATIC_DIR) / "curriculos.html").read_text(encoding="utf-8")
        self.assertIn(".upload{", html)
        self.assertNotIn("..upload{", html)
        self.assertIn('id="status" role="status" aria-live="polite"', html)

    def test_jobs_page_uses_accessible_loading_skeleton_and_retry(self):
        html = (Path(main_module.STATIC_DIR) / "vagas.html").read_text(encoding="utf-8")
        self.assertIn('class="skeleton skeleton-card"', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn('id="retryJobs"', html)
        self.assertIn("Não foi possível carregar os detalhes. Tente novamente.", html)

    def test_async_profile_and_preferences_surfaces_recovery_messages(self):
        resume = (Path(main_module.STATIC_DIR) / "curriculos.html").read_text(encoding="utf-8")
        preferences = (Path(main_module.STATIC_DIR) / "configuracoes.html").read_text(encoding="utf-8")
        self.assertIn("Carregando seu perfil...", resume)
        self.assertIn("Não foi possível carregar seu perfil.", resume)
        self.assertIn("Não foi possível carregar suas preferências. Tente novamente.", preferences)
        self.assertIn("Não foi possível salvar suas preferências. Tente novamente.", preferences)

    def test_resume_profile_load_exposes_accessible_retry(self):
        resume = (Path(main_module.STATIC_DIR) / "curriculos.html").read_text(encoding="utf-8")
        self.assertIn('id="status" role="status" aria-live="polite"', resume)
        self.assertIn('id="retryProfile" type="button" class="button retry-profile" hidden', resume)
        self.assertIn(".retry-profile[hidden]{display:none}", resume)
        self.assertIn("if(!r.ok)throw new Error('profile request failed')", resume)
        self.assertIn("retryProfile.addEventListener('click',load)", resume)
        self.assertIn("catch(()=>setStatus('Não foi possível carregar seu perfil.',false,true))", resume)
        self.assertIn("if(!p.configured){setStatus('');return;}", resume)

    def test_config_page_keeps_its_layout_styles(self):
        html = (Path(main_module.STATIC_DIR) / "configuracoes.html").read_text(encoding="utf-8")
        self.assertIn(":root{--ink:", html)
        self.assertIn(".layout{", html)
        self.assertIn(".nav{", html)
        self.assertIn(".card{", html)

    def test_applications_page_surfaces_retry_on_load_failure(self):
        html = (Path(main_module.STATIC_DIR) / "candidaturas.html").read_text(encoding="utf-8")
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn('id="retryApplications"', html)
        self.assertIn("Não foi possível carregar as candidaturas agora.", html)
        self.assertIn("Tentar novamente", html)

    def test_interviews_page_surfaces_retry_on_load_failure(self):
        html = (Path(main_module.STATIC_DIR) / "entrevistas.html").read_text(encoding="utf-8")
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn('id="retryInterviews"', html)
        self.assertIn("Não foi possível carregar as entrevistas agora.", html)

    def test_profile_and_settings_surface_network_recovery(self):
        profile = (Path(main_module.STATIC_DIR) / "profile.html").read_text(encoding="utf-8")
        settings = (Path(main_module.STATIC_DIR) / "settings.html").read_text(encoding="utf-8")
        self.assertIn("Não foi possível carregar seu perfil. Tente novamente.", profile)
        self.assertIn("Não foi possível salvar seu perfil. Tente novamente.", profile)
        self.assertIn("Não foi possível carregar suas preferências. Tente novamente.", settings)
        self.assertIn("Não foi possível salvar suas preferências. Tente novamente.", settings)

    def test_resume_page_groups_extracted_data_for_review(self):
        html = (Path(main_module.STATIC_DIR) / "curriculos.html").read_text(encoding="utf-8")
        self.assertIn('id="extractSummary"', html)
        self.assertIn('id="experienceItems"', html)
        self.assertIn('id="skillItems"', html)
        self.assertIn('id="educationItems"', html)
        self.assertIn('id="languageItems"', html)
        self.assertIn("fillList", html)

    def test_document_studio_clear_action_protects_filled_draft(self):
        html = (Path(main_module.STATIC_DIR) / "document-studio.html").read_text(encoding="utf-8")
        self.assertIn('class="clear-action" id="clear"', html)
        self.assertIn("Limpar formulário", html)
        self.assertIn("const hasDraft=", html)
        self.assertIn("window.confirm('Limpar os dados preenchidos e a prévia gerada?')", html)
        self.assertIn("current=null", html)
        self.assertIn("$('title').focus()", html)

    def test_document_studio_shows_generation_progress(self):
        html = (Path(main_module.STATIC_DIR) / "document-studio.html").read_text(encoding="utf-8")
        self.assertIn(".primary.busy", html)
        self.assertIn("aria-busy", html)
        self.assertIn("Gerando prévia...", html)
        self.assertIn("button.classList.remove('busy')", html)
        self.assertIn("/billing/document-export/status?application_id=", html)
        self.assertIn("state.generation_status==='READY'", html)
        self.assertIn("$('downloadResume').hidden=true", html)
        self.assertIn("$('downloadResume').hidden=false", html)
        self.assertIn('id="retryGeneration"', html)

    def test_document_studio_supports_manual_or_captured_application_and_safe_checkout_open(self):
        html = (Path(main_module.STATIC_DIR) / "document-studio.html").read_text(encoding="utf-8")
        self.assertIn('id="applicationSelect"', html)
        self.assertIn("/applications/${linkedApplicationId}", html)
        self.assertIn("application_id:linkedApplicationId", html)
        self.assertIn("const paymentWindow=window.open('about:blank','_blank')", html)
        self.assertIn("O Pix aparece entre os métodos disponíveis da sua conta", html)

    def test_dashboard_checkout_reserves_popup_before_fetch(self):
        html = (Path(main_module.STATIC_DIR) / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('const paymentWindow = window.open("about:blank", "_blank");', html)
        self.assertIn("paymentWindow.location.href = payload.checkout_url", html)

    def test_dashboard_records_channel_and_external_result(self):
        html = (Path(main_module.STATIC_DIR) / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="statusChannel"', html)
        self.assertIn('id="externalResult"', html)
        self.assertIn("external_result: $(\"externalResult\").value", html)
        self.assertIn("latestTracking", html)

    def test_dashboard_requires_risk_review_before_opening_doubtful_vacancy(self):
        html = (Path(main_module.STATIC_DIR) / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="applicationRiskCheck"', html)
        self.assertIn('id="riskAcknowledged"', html)
        self.assertIn("/risk-review", html)
        self.assertIn('["DUVIDOSA", "SUSPEITA"].includes(item.health_band)', html)
        self.assertIn("const isFraud = Boolean(item.fraud_suspected)", html)
        self.assertIn("isReview && !item.risk_reviewed_at", html)

    def test_dashboard_has_dismissible_guided_onboarding(self):
        html = (Path(main_module.STATIC_DIR) / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="guidedOnboardingDialog"', html)
        self.assertIn('data-guided-step="0"', html)
        self.assertIn('data-guided-step="1"', html)
        self.assertIn('data-guided-step="2"', html)
        self.assertIn('ac_guided_onboarding_v1', html)
        self.assertIn('id="skipGuidedOnboarding"', html)
        self.assertIn('id="guidedCaptureButton"', html)

    def test_help_page_is_public_and_covers_core_questions(self):
        response = main_module._page(Path(main_module.STATIC_DIR) / "ajuda.html")
        html = response.body.decode("utf-8")
        self.assertIn("Central de ajuda", html)
        self.assertIn("Quais formatos de currículo posso importar?", html)
        self.assertIn("Como meus dados são tratados?", html)
        self.assertIn("/privacidade", html)
        self.assertIn("/configuracoes#preferencias", html)
        self.assertIn("/ajuda", main_module.AuthMiddleware.PUBLIC_PATHS)

    def test_settings_persist_lifecycle_email_preferences(self):
        html = (Path(main_module.STATIC_DIR) / "configuracoes.html").read_text(encoding="utf-8")
        self.assertIn('id="notificationFrequency"', html)
        self.assertIn('id="notifyInterviews"', html)
        self.assertIn('id="notifyFollowups"', html)
        self.assertIn('id="notifyExpiring" type="checkbox" disabled', html)
        self.assertIn('value="immediate">Imediatamente (em até 5 minutos)</option>', html)
        self.assertIn('notification_frequency:', html)
        self.assertIn('notify_expiring:false', html)
        self.assertIn('Vagas expirando ainda não geram e-mail.', html)

    def test_security_page_exposes_confirmed_account_deletion(self):
        html = (Path(main_module.STATIC_DIR) / "security.html").read_text(encoding="utf-8")
        self.assertIn('id="deleteAccountForm"', html)
        self.assertIn('id="deleteConfirmation"', html)
        self.assertIn("EXCLUIR MINHA CONTA", html)
        self.assertIn("/api/privacy/delete-account", html)

    def test_mfa_ui_does_not_promise_unimplemented_recovery_methods(self):
        script = (Path(main_module.STATIC_DIR) / "security-enhance.js").read_text(encoding="utf-8")
        self.assertIn("A proteção é opcional", script)
        self.assertIn("Não oferecemos recuperação por SMS nem códigos de emergência", script)
        self.assertIn("a mesma conta nos dois", script)
        self.assertIn("data-mfa-second-device", script)
        self.assertIn("QR code", script)
        self.assertIn("Passo 2 · Digite o código de 6 dígitos", script)
        self.assertIn("dialog.showModal()", script)
        self.assertNotIn("window.prompt", script)
        self.assertNotIn("segredo TOTP", script.casefold())
        self.assertNotIn("você receberá códigos de recuperação", script.casefold())

    def test_security_ui_manages_current_and_other_sessions_honestly(self):
        script = (Path(main_module.STATIC_DIR) / "security-enhance.js").read_text(encoding="utf-8")
        self.assertIn("Sessões e dispositivos", script)
        self.assertIn("id=\"logoutOthers\"", script)
        self.assertIn("id=\"logoutCurrent\"", script)
        self.assertIn("/auth/logout/others", script)
        self.assertIn("O app ainda não mostra os aparelhos individualmente", script)
        self.assertNotIn("Revise os dispositivos que estão usando sua conta.", script)

    def test_alerts_enhancement_does_not_duplicate_persisted_controls(self):
        script = (Path(main_module.STATIC_DIR) / "alerts-enhance.js").read_text(encoding="utf-8")
        self.assertIn("#notifyInterviews", script)
        self.assertIn("#notificationFrequency", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("mailto:", script)


if __name__ == "__main__":
    unittest.main()
