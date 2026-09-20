import unittest

from app.job_health import JobHealthEvaluator


BASE_DESCRIPTION = (
    "Responsabilidades: conduzir processos de recrutamento e seleção, acompanhar "
    "indicadores de RH, apoiar gestores e organizar rotinas de departamento pessoal. "
    "Requisitos: experiência com entrevistas, legislação trabalhista, ferramentas de "
    "seleção e comunicação com equipes. A empresa oferece benefícios, salário "
    "compatível com o mercado, horário comercial e oportunidades de desenvolvimento. "
    "As atividades seguem processos internos documentados e o candidato recebe "
    "informações sobre cada etapa pelo portal oficial da empresa."
)


class JobHealthFraudSignalsTest(unittest.TestCase):
    def evaluate(self, extra_text="", *, url="https://careers.empresa.test/jobs/123", source="manual"):
        return JobHealthEvaluator().evaluate(
            {
                "title": "Analista de Recursos Humanos",
                "company": "Empresa Exemplo",
                "description": f"{BASE_DESCRIPTION} {extra_text}",
                "salary": "R$ 6.000 a R$ 8.000",
                "url": url,
                "source": source,
            }
        )

    def codes(self, result):
        return {signal.code for signal in result.signals}

    def test_accented_pix_fee_request_is_high_risk(self):
        result = self.evaluate(
            "Para participar da seleção, pague uma taxa de inscrição via Pix antes da entrevista."
        )

        self.assertTrue(result.fraud_suspected)
        self.assertEqual(result.band, "SUSPEITA")
        self.assertIn("PEDIDO_PAGAMENTO", self.codes(result))

    def test_explicit_no_fee_warning_is_not_classified_as_payment_request(self):
        result = self.evaluate(
            "A empresa nunca cobra taxa de inscrição nem solicita pagamento para entrevistas."
        )

        self.assertFalse(result.fraud_suspected)
        self.assertNotIn("PEDIDO_PAGAMENTO", self.codes(result))

    def test_explicitly_free_fee_language_is_not_classified_as_payment_request(self):
        result = self.evaluate("A taxa de cadastro é gratuita e o treinamento é sem custo para o candidato.")

        self.assertFalse(result.fraud_suspected)
        self.assertNotIn("PEDIDO_PAGAMENTO", self.codes(result))

    def test_a_separate_payment_request_is_not_hidden_by_a_fee_warning(self):
        result = self.evaluate(
            "Não cobramos taxa de cadastro; mas, para participar da seleção, pague uma taxa de inscrição via Pix."
        )

        self.assertTrue(result.fraud_suspected)
        self.assertIn("PEDIDO_PAGAMENTO", self.codes(result))

    def test_conjunction_does_not_hide_a_separate_payment_request(self):
        result = self.evaluate(
            "Não cobramos taxa de cadastro e pague uma taxa de inscrição via Pix para participar."
        )

        self.assertTrue(result.fraud_suspected)
        self.assertIn("PEDIDO_PAGAMENTO", self.codes(result))

    def test_generic_salary_and_training_language_is_not_a_fee_request(self):
        result = self.evaluate(
            "Os valores de remuneração são compatíveis com o mercado. O material de treinamento é fornecido gratuitamente pela empresa."
        )

        self.assertNotIn("PEDIDO_PAGAMENTO", self.codes(result))
        self.assertNotIn("ERROS_ORTIGRAFICOS", self.codes(result))

    def test_low_quality_score_is_not_itself_a_fraud_finding(self):
        result = JobHealthEvaluator().evaluate({
            "title": "Banco de talentos",
            "company": "Empresa Teste",
            "description": "",
            "salary": "",
            "url": "",
            "source": "manual",
        })

        self.assertEqual(result.band, "SUSPEITA")
        self.assertFalse(result.fraud_suspected)

    def test_sensitive_document_requested_before_interview_by_informal_channel_is_high_risk(self):
        result = self.evaluate(
            "Para participar do processo seletivo, envie seu CPF pelo WhatsApp antes da entrevista ou para vagas@gmail.com."
        )

        self.assertTrue(result.fraud_suspected)
        self.assertIn("PEDIDO_DOCUMENTO", self.codes(result))

    def test_protective_warning_and_post_offer_admission_documents_are_not_high_risk(self):
        warning = self.evaluate(
            "Não envie seu CPF pelo WhatsApp antes da entrevista; a empresa não pede documentos nessa etapa."
        )
        post_offer = self.evaluate(
            "Após a aprovação, envie CPF e dados bancários para concluir a admissão pelo canal oficial."
        )

        self.assertFalse(warning.fraud_suspected)
        self.assertFalse(post_offer.fraud_suspected)
        self.assertNotIn("PEDIDO_DOCUMENTO", self.codes(warning))
        self.assertNotIn("PEDIDO_DOCUMENTO", self.codes(post_offer))

    def test_whatsapp_contact_without_personal_email_is_not_labeled_unsafe(self):
        result = self.evaluate("Entre em contato pelo WhatsApp corporativo para tirar dúvidas sobre a vaga.")

        self.assertNotIn("CONTATO_INSEGURO", self.codes(result))

    def test_arbitrary_com_domain_and_email_channel_do_not_increase_trust(self):
        result = self.evaluate(
            "",
            url="https://empresa-exemplo.com/vagas/analista",
            source="gmail",
        )

        self.assertNotIn("DOMINIO_CORPORATIVO", self.codes(result))
        self.assertNotIn("ALERTA_EMAIL", self.codes(result))


if __name__ == "__main__":
    unittest.main()
