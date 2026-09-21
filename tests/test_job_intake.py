import unittest

from app.job_intake import parse_job_text


SAMPLE = """
Empresa: Exemplo Tecnologia
Cargo: Coordenador de Recursos Humanos
Localização: Salvador/BA
Modalidade: Híbrido
Salário: R$ 8.000,00 a R$ 10.000,00
Buscamos profissional com experiência em recrutamento, folha de pagamento,
gestão de equipes, indicadores, Power BI e relações trabalhistas.
Candidate-se: https://exemplo.gupy.io/jobs/12345
"""


class JobIntakeParserTest(unittest.TestCase):
    def test_extracts_public_url_without_scheme(self):
        result = parse_job_text(
            "Coordenador de Recursos Humanos\n"
            "Canil Palazzo\n"
            "Lauro de Freitas, Brasil\n"
            "Descricao completa da oportunidade com requisitos e responsabilidades.\n"
            "bebee.com/br/jobs/coordenador-de-recursos-humanos-canil-palazzo-lauro-de-freitas-ba"
        )
        self.assertTrue(result["url"].startswith("https://bebee.com/"))
        self.assertEqual(result["location"], "Lauro de Freitas, Brasil")

    def test_company_is_read_after_title_and_navigation_is_ignored(self):
        result = parse_job_text(
            "Entra\n"
            "Coordenador de Recursos Humanos Generalista\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_wrapped_title_is_joined_before_company_detection(self):
        result = parse_job_text(
            "Entra\n"
            "Coordenador de Recursos Humanos\n"
            "Generalista\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(
            result["title"],
            "Coordenador de Recursos Humanos Generalista",
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_section_heading_is_not_used_as_company(self):
        result = parse_job_text(
            "Coordenador de Recursos Humanos\n"
            "Generalista\n"
            "Descricao da vaga\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_extracts_labeled_job(self):
        result = parse_job_text(SAMPLE, "gupy")
        self.assertEqual(result["company"], "Exemplo Tecnologia")
        self.assertEqual(result["title"], "Coordenador de Recursos Humanos")
        self.assertEqual(result["location"], "Salvador/BA")
        self.assertEqual(result["modality"], "Hibrido")
        self.assertEqual(result["modality_confidence"], 95)
        self.assertEqual(result["salary_confidence"], 95)
        self.assertEqual(result["salary_min"], 8000)
        self.assertEqual(result["salary_max"], 10000)
        self.assertEqual(result["contract_type"], "")
        self.assertEqual(result["url"], "https://exemplo.gupy.io/jobs/12345")
        self.assertTrue(result["external_id"].startswith("intake-"))

    def test_fingerprint_is_stable(self):
        first = parse_job_text(SAMPLE, "email")
        second = parse_job_text(SAMPLE, "linkedin")
        self.assertEqual(first["external_id"], second["external_id"])

    def test_url_used_as_title_is_converted_to_readable_job_name(self):
        result = parse_job_text(
            "Cargo: https://www.jobbol.com.br/cargos/analista-administrativo\n"
            "Empresa: Jobbol\n"
            "Descricao com responsabilidades, requisitos e experiencia para a vaga.\n"
            "https://www.jobbol.com.br/cargos/analista-administrativo"
        )
        self.assertEqual(result["title"], "Analista Administrativo")

    def test_alert_greeting_is_removed_before_saving_the_job_title(self):
        result = parse_job_text(
            "Olá Paulo, temos novas vagas de Analista de Recursos Humanos\n"
            "Empresa Alpha\n"
            "Descrição com responsabilidades, requisitos e experiência para a vaga.\n"
            "https://example.com/jobs/123"
        )
        self.assertEqual(result["title"], "Analista de Recursos Humanos")

    def test_company_prefix_cnpj_is_hidden(self):
        result = parse_job_text(
            "Cargo: Analista de Inovacao\n"
            "Empresa: 5.297.491 RODRIGO FELIPE - ME\n"
            "Descricao com responsabilidades, requisitos e experiencia para a vaga.\n"
            "https://example.com/jobs/123"
        )
        self.assertEqual(result["company"], "RODRIGO FELIPE - ME")

    def test_extracts_brazilian_contract_type_and_confidence(self):
        result = parse_job_text(
            "Cargo: Analista de Recursos Humanos\n"
            "Empresa: Exemplo\n"
            "Regime: CLT\n"
            "Modalidade: Remoto\n"
            "Descricao completa com responsabilidades, requisitos e experiencia para a vaga."
        )
        self.assertEqual(result["contract_type"], "CLT")
        self.assertEqual(result["contract_confidence"], 95)
        self.assertEqual(result["modality"], "Remoto")

    def test_keeps_conflicting_modality_and_contract_unknown(self):
        result = parse_job_text(
            "Cargo: Analista de Recursos Humanos\n"
            "Empresa: Exemplo\n"
            "Regime: CLT ou PJ\n"
            "Modalidade: Remoto ou híbrido\n"
            "Descrição com responsabilidades, requisitos e experiência profissional."
        )
        self.assertEqual(result["contract_type"], "")
        self.assertEqual(result["contract_confidence"], 0)
        self.assertEqual(result["modality"], "")
        self.assertEqual(result["modality_confidence"], 0)

    def test_keeps_multiple_unlabeled_salary_values_unknown(self):
        result = parse_job_text(
            "Cargo: Analista de Recursos Humanos\n"
            "Empresa: Exemplo\n"
            "Benefícios de R$ 800,00 e bônus de R$ 1.200,00.\n"
            "Descrição com responsabilidades, requisitos e experiência profissional."
        )
        self.assertEqual(result["salary"], "")
        self.assertIsNone(result["salary_min"])
        self.assertIsNone(result["salary_max"])
        self.assertEqual(result["salary_confidence"], 0)

    def test_does_not_infer_city_from_role_before_city_state(self):
        result = parse_job_text(
            "Analista de RH - Salvador/BA\n"
            "Empresa Exemplo\n"
            "Descrição com responsabilidades, requisitos e experiência profissional."
        )
        self.assertEqual(result["location"], "")

    def test_explicit_location_label_remains_authoritative(self):
        result = parse_job_text(
            "Cargo: Analista de RH - Salvador/BA\n"
            "Empresa: Exemplo\n"
            "Localização: Salvador/BA\n"
            "Descrição com responsabilidades, requisitos e experiência profissional."
        )
        self.assertEqual(result["location"], "Salvador/BA")

    def test_keeps_multiple_unlabeled_city_state_values_unknown(self):
        result = parse_job_text(
            "Analista de Recursos Humanos\n"
            "Empresa Exemplo\n"
            "Salvador/BA ou São Paulo/SP\n"
            "Descrição com responsabilidades, requisitos e experiência profissional."
        )
        self.assertEqual(result["location"], "")

    def test_salary_bounds_are_empty_when_salary_is_not_disclosed(self):
        result = parse_job_text(
            "Cargo: Analista de Recursos Humanos\n"
            "Empresa: Exemplo\n"
            "Descricao completa com responsabilidades, requisitos e experiencia para a vaga."
        )
        self.assertIsNone(result["salary_min"])
        self.assertIsNone(result["salary_max"])

    def test_rejects_short_text(self):
        with self.assertRaises(ValueError):
            parse_job_text("Vaga de RH")


if __name__ == "__main__":
    unittest.main()
