import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import cover_letter
from app import main as main_module
from app import resume_document
from app.database import Base
from app.models import Application, Candidate, Experience, Job, Skill


class IntegratedFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.engine = create_engine(
            f"sqlite:///{temp_path / 'test.db'}",
            connect_args={"check_same_thread": False},
        )
        self.testing_session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.original_session = main_module.SessionLocal
        self.original_output_dir = resume_document.OUTPUT_DIR
        self.original_cover_letter_output_dir = cover_letter.OUTPUT_DIR
        main_module.SessionLocal = self.testing_session
        resume_document.OUTPUT_DIR = temp_path
        cover_letter.OUTPUT_DIR = temp_path

        db = self.testing_session()
        candidate = Candidate(
            name="Paulo Henrique Santos Oliveira",
            location="Salvador/BA",
            email="henriqueoliveirarh93@gmail.com",
            phone="(71) 99349-4443",
            linkedin="https://www.linkedin.com/in/paulo-oliveira-933a9254/",
            target_roles="Coordenador de RH, Supervisor de RH",
            summary="Profissional de RH com mais de 10 anos de experiência.",
        )
        db.add(candidate)
        db.flush()
        db.add(
            Experience(
                candidate_id=candidate.id,
                company="TPC Logística",
                role="Supervisor de Recursos Humanos",
                start_date="07/2022",
                end_date="08/2024",
                description=(
                    "Gestão de RH, recrutamento, treinamento, "
                    "indicadores e Power BI."
                ),
            )
        )
        for name in ["Recursos Humanos", "Gestão de Equipes", "Power BI"]:
            db.add(
                Skill(
                    candidate_id=candidate.id,
                    name=name,
                    category="RH",
                    proficiency="Avançado",
                )
            )
        db.add(
            Job(
                source="teste",
                external_id="vaga-1",
                company="Empresa Teste",
                title="Coordenador de Recursos Humanos",
                location="Salvador/BA",
                modality="Híbrido",
                salary="R$ 8.000 a R$ 10.000",
                url="",
                description=(
                    "Gestão de RH, recrutamento e seleção, treinamento, "
                    "gestão de equipes, indicadores e Power BI."
                ),
            )
        )
        db.commit()
        db.close()

    def tearDown(self):
        main_module.SessionLocal = self.original_session
        resume_document.OUTPUT_DIR = self.original_output_dir
        cover_letter.OUTPUT_DIR = self.original_cover_letter_output_dir
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_generate_document_for_job_returns_download(self):
        response = main_module.generate_document_for_job(1)

        self.assertTrue(Path(response.path).is_file())
        self.assertEqual(Path(response.path).read_bytes()[:2], b"PK")
        self.assertIn(
            "application/vnd.openxmlformats-officedocument",
            response.media_type,
        )
        self.assertTrue(response.headers["x-analysis-score"])
        self.assertTrue(response.headers["x-personalization-score"])
        self.assertEqual(response.headers["x-application-status"], "CURRICULO_GERADO")

        db = self.testing_session()
        application = db.query(Application).filter_by(job_id=1).one()
        self.assertEqual(application.status, "CURRICULO_GERADO")
        self.assertIsNotNone(application.analysis_score)
        self.assertIsNotNone(application.personalization_score)
        self.assertTrue(application.document_path)
        self.assertEqual(
            [event.status for event in application.events],
            ["IDENTIFICADA", "CURRICULO_GERADO"],
        )
        db.close()

    def test_preferences_drive_automatic_queue_decision(self):
        request = main_module.CandidatePreferencesRequest(
            target_roles=["Coordenador de Recursos Humanos"],
            locations=["Salvador/BA"],
            minimum_score=0,
            automatic_score=0,
            allow_automatic=True,
        )
        updated = main_module.update_preferences(request)

        self.assertEqual(updated["status"], "PREFERENCIAS_ATUALIZADAS")
        main_module.analyze_saved_job(1)
        application = main_module.get_application(1)
        self.assertEqual(application["queue_decision"], "AUTOMATICA")
        self.assertTrue(application["decision_reasons"])

    def test_excluded_company_is_sent_to_discard_queue(self):
        request = main_module.CandidatePreferencesRequest(
            excluded_companies=["Empresa Teste"],
            minimum_score=0,
        )
        main_module.update_preferences(request)

        main_module.analyze_saved_job(1)
        application = main_module.get_application(1)
        self.assertEqual(application["queue_decision"], "DESCARTAR")

    def test_generate_document_for_unknown_job_returns_404(self):
        with self.assertRaises(HTTPException) as context:
            main_module.generate_document_for_job(999)

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Vaga não encontrada.")

    def test_analyze_job_returns_analysis(self):
        request = main_module.JobRequest(
            title="Coordenador de Recursos Humanos",
            description="Gestão de RH, equipes, indicadores e Power BI.",
        )
        payload = main_module.analyze(request)

        self.assertGreaterEqual(payload["analysis"]["score"], 0)
        self.assertEqual(
            payload["next_action"],
            payload["analysis"]["next_action"],
        )

    def test_saved_analysis_survives_dashboard_reload(self):
        result = main_module.analyze_saved_job(1)
        listing = main_module.list_applications()
        saved = listing["applications"][0]

        self.assertEqual(saved["analysis_score"], result["analysis"]["score"])
        self.assertEqual(
            saved["recommendation"],
            result["analysis"]["recommendation"],
        )
        self.assertEqual(saved["analysis"]["strengths"], result["analysis"]["strengths"])
        self.assertEqual(saved["analysis"]["gaps"], result["analysis"]["gaps"])

    def test_application_status_history(self):
        main_module.generate_document_for_job(1)
        request = main_module.ApplicationStatusRequest(
            status="CANDIDATURA_ENVIADA",
            note="Candidatura enviada pelo portal da empresa.",
        )
        payload = main_module.update_application_status(1, request)

        self.assertEqual(payload["status"], "CANDIDATURA_ENVIADA")
        self.assertEqual(payload["events"][-1]["status"], "CANDIDATURA_ENVIADA")
        self.assertEqual(
            payload["events"][-1]["note"],
            "Candidatura enviada pelo portal da empresa.",
        )

    def test_dashboard_is_available(self):
        response = main_module.dashboard()

        self.assertEqual(response.status_code, 200)
        body = bytes(response.body).decode("utf-8")
        self.assertIn("Agente de Candidaturas", body)
        self.assertIn("/applications", body)
        self.assertIn("/queue/summary", body)
        self.assertIn("Fila de decisão", body)
        self.assertIn("queueBulkApprove", body)
        self.assertIn("Nova vaga", body)
        self.assertIn("Gerar e baixar currículo", body)

    def test_create_job_also_creates_application(self):
        request = main_module.JobCreateRequest(
            source="dashboard",
            external_id="vaga-2",
            company="Nova Empresa",
            title="Supervisor de RH",
            location="Salvador/BA",
            modality="Híbrido",
            salary="",
            url="",
            description="Gestão de equipe de Recursos Humanos.",
        )
        payload = main_module.create_job(request)

        self.assertEqual(payload["status"], "VAGA_CADASTRADA")
        self.assertEqual(payload["application"]["status"], "IDENTIFICADA")

    def test_download_existing_document(self):
        generated = main_module.generate_document_for_job(1)
        application_id = int(generated.headers["x-application-id"])

        downloaded = main_module.download_application_document(application_id)

        self.assertTrue(Path(downloaded.path).is_file())
        self.assertEqual(Path(downloaded.path).read_bytes()[:2], b"PK")

    def test_cover_letter_returns_personalized_text(self):
        payload = main_module.create_cover_letter_for_job(1)

        self.assertEqual(payload["job_id"], 1)
        self.assertEqual(payload["company"], "Empresa Teste")
        self.assertIn(
            "Coordenador de Recursos Humanos",
            payload["letter"],
        )
        self.assertIn(
            "Paulo Henrique Santos Oliveira",
            payload["letter"],
        )

    def test_cover_letter_document_returns_docx(self):
        response = main_module.create_cover_letter_document(1)

        document_path = Path(response.path)

        self.assertTrue(document_path.is_file())
        self.assertEqual(
            document_path.read_bytes()[:2],
            b"PK",
        )

        db = self.testing_session()
        application = db.query(Application).filter_by(job_id=1).one()
        self.assertTrue(application.cover_letter_text)
        self.assertEqual(
            Path(application.cover_letter_path),
            document_path,
        )
        application_id = application.id
        db.close()

        saved_response = main_module.download_application_cover_letter(
            application_id
        )
        self.assertEqual(Path(saved_response.path), document_path)


if __name__ == "__main__":
    unittest.main()
