import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Application, Candidate, DocumentExportPurchase, Job
from scripts.migrate_rls import CHILD_POLICIES, DIRECT_OWNER_TABLES


class RlsCoverageTest(unittest.TestCase):
    def test_every_model_table_is_covered_by_rls_migration(self):
        configured = set(DIRECT_OWNER_TABLES) | set(CHILD_POLICIES)
        self.assertEqual(set(Base.metadata.tables), configured)


class CrossUserIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'idor.db'}",
            connect_args={"check_same_thread": False},
        )
        self.testing_session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.original_session = main_module.SessionLocal
        main_module.SessionLocal = self.testing_session
        self.user_a = {
            "id": "owner-a",
            "email": "a@example.com",
            "app_metadata": {"plan": "pro"},
        }
        self.user_b = {
            "id": "owner-b",
            "email": "b@example.com",
            "app_metadata": {"plan": "pro"},
        }

        db = self.testing_session()
        self.job_ids = {}
        self.application_ids = {}
        for owner, company in (("owner-a", "Empresa A"), ("owner-b", "Empresa B")):
            candidate = Candidate(
                owner_id=owner,
                name=f"Candidato {owner}",
                location="Salvador/BA",
                email=f"{owner}@example.com",
                phone="71999999999",
                linkedin="",
                target_roles="Recursos Humanos",
                summary="Experiência profissional em recursos humanos.",
            )
            db.add(candidate)
            db.flush()
            job = Job(
                owner_id=owner,
                source="teste",
                external_id=f"vaga-{owner}",
                company=company,
                title="Analista de Recursos Humanos",
                location="Salvador/BA",
                modality="Híbrido",
                salary="",
                url="",
                description="Atuação em recursos humanos, seleção e treinamento.",
            )
            db.add(job)
            db.flush()
            document_path = Path(self.temp_dir.name) / f"{owner}-curriculo.docx"
            letter_path = Path(self.temp_dir.name) / f"{owner}-carta.docx"
            document_path.write_bytes(b"PK\x03\x04teste")
            letter_path.write_bytes(b"PK\x03\x04teste")
            application = Application(
                job_id=job.id,
                candidate_id=candidate.id,
                status="CURRICULO_GERADO",
                document_path=str(document_path),
                cover_letter_path=str(letter_path),
            )
            db.add(application)
            db.flush()
            db.add(
                DocumentExportPurchase(
                    owner_id=owner,
                    order_nsu=f"order-{owner}",
                    amount=990,
                    paid_amount=990,
                    status="PAID",
                )
            )
            self.job_ids[owner] = job.id
            self.application_ids[owner] = application.id
        db.commit()
        db.close()

    def tearDown(self):
        main_module.SessionLocal = self.original_session
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_user_sees_only_owned_jobs_and_applications(self):
        jobs_a = main_module.list_jobs_endpoint(self.user_a)
        apps_a = main_module.list_apps(user=self.user_a)
        jobs_b = main_module.list_jobs_endpoint(self.user_b)
        apps_b = main_module.list_apps(user=self.user_b)

        self.assertEqual([item["id"] for item in jobs_a["jobs"]], [self.job_ids["owner-a"]])
        self.assertEqual([item["id"] for item in apps_a["applications"]], [self.application_ids["owner-a"]])
        self.assertEqual([item["id"] for item in jobs_b["jobs"]], [self.job_ids["owner-b"]])
        self.assertEqual([item["id"] for item in apps_b["applications"]], [self.application_ids["owner-b"]])

    def test_user_cannot_access_other_users_ids_or_files(self):
        foreign_job_id = self.job_ids["owner-a"]
        foreign_application_id = self.application_ids["owner-a"]

        with self.assertRaises(HTTPException) as job_error:
            main_module.get_job_endpoint(foreign_job_id, self.user_b)
        self.assertEqual(job_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as application_error:
            main_module.get_app(foreign_application_id, self.user_b)
        self.assertEqual(application_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as status_error:
            main_module.update_app_status(
                foreign_application_id,
                main_module.ApplicationStatusRequest(
                    status="CANDIDATURA_ENVIADA",
                    note="tentativa de acesso cruzado",
                ),
                self.user_b,
            )
        self.assertEqual(status_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as document_error:
            main_module.download_doc(foreign_application_id, self.user_b)
        self.assertEqual(document_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as letter_error:
            main_module.download_cover_letter(foreign_application_id, self.user_b)
        self.assertEqual(letter_error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
