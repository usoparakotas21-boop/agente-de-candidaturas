import unittest
from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class RetentionExperienceCopyTests(unittest.TestCase):
    def test_over_quota_copy_keeps_saved_opportunities_available(self):
        html = (STATIC / "configuracoes.html").read_text(encoding="utf-8")
        self.assertIn("const usageText=used>limit?", html)
        self.assertIn("As vagas salvas continuam disponíveis.", html)
        self.assertIn("Novas capturas serão liberadas em", html)
        self.assertIn("Consulte os planos disponíveis para continuar antes disso.", html)
        self.assertIn("`${used} de ${limit} oportunidades usadas neste mês", html)

    def test_expiring_alert_uses_explicit_deadline_and_reports_smtp_status(self):
        html = (STATIC / "configuracoes.html").read_text(encoding="utf-8")
        self.assertIn('id="notifyExpiring" type="checkbox" disabled', html)
        self.assertIn('id="expiringHint"', html)
        self.assertIn("data de encerramento explícita do anúncio", html)
        self.assertIn("configuração do envio por e-mail", html)

    def test_document_email_tooltip_is_accessible_and_touch_friendly(self):
        html = (STATIC / "curriculos.html").read_text(encoding="utf-8")
        self.assertIn("delivery-info-wrap:hover .delivery-tooltip", html)
        self.assertIn("aria-describedby',tooltipId", html)
        self.assertIn("aria-expanded','false", html)
        self.assertIn("help.classList.toggle('is-open')", html)
        self.assertIn("Seu documento está salvo na biblioteca privada", html)
        self.assertIn("O envio por e-mail ainda depende da configuração do serviço", html)

    def test_terms_disclose_sixty_day_raw_message_retention(self):
        html = (STATIC / "termos.html").read_text(encoding="utf-8")
        self.assertIn("9. Retenção de mensagens e alertas", html)
        self.assertIn("mensagens brutas de e-mail processadas", html)
        self.assertIn("trechos originais dos alertas", html)
        self.assertIn("após 60 dias", html)
        self.assertIn("histórico de decisões e candidaturas podem permanecer", html)

    def test_privacy_policy_names_active_providers_and_retention_windows(self):
        html = (STATIC / "privacidade.html").read_text(encoding="utf-8-sig")
        for provider in (
            "Supabase",
            "Render",
            "Google",
            "Microsoft",
            "Mercado Pago",
            "Upstash",
            "Brevo",
            "GitHub Actions",
            "Cloudflare",
            "UptimeRobot",
            "Have I Been Pwned",
        ):
            with self.subTest(provider=provider):
                self.assertIn(provider, html)
        self.assertIn("cinco primeiros caracteres do hash SHA-1", html)
        self.assertIn("após 60 dias", html)
        self.assertIn("por até 60 dias", html)
        self.assertIn("por até 30 dias", html)
        self.assertIn("serviços sem cobrança", html)
        self.assertIn("revisão humana", html)


if __name__ == "__main__":
    unittest.main()
