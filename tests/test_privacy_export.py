import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Application, Candidate, Job


class PrivacyExportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        candidate = Candidate(
            owner_id="owner-a", name="Pessoa A", location="Salvador", email="a@example.test",
            phone="", linkedin="", target_roles="RH", summary="Resumo", profile_data="{}",
            preferences_data="{}",
        )
        own_job = Job(owner_id="owner-a", source="manual", external_id="export-1", company="Empresa A", title="Analista", location="Salvador", modality="hibrido", url="https://example.test/a", description="Descrição")
        other_job = Job(owner_id="owner-b", source="manual", external_id="export-2", company="Empresa B", title="Coordenador", location="Recife", modality="remoto", url="https://example.test/b", description="Descrição")
        db.add_all([candidate, own_job, other_job])
        db.flush()
        db.add(Application(job_id=own_job.id, candidate_id=candidate.id, status="IDENTIFICADA"))
        db.add(Application(job_id=other_job.id, status="ENTREVISTA"))
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_export_is_owner_scoped_and_omits_secrets(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            response = main_module.privacy_export({"id": "owner-a"})

        payload = json.loads(response.body)
        self.assertEqual(payload["profile"]["name"], "Pessoa A")
        self.assertEqual([item["company"] for item in payload["jobs"]], ["Empresa A"])
        self.assertEqual(len(payload["applications"]), 1)
        self.assertNotIn("access_token", payload)
        self.assertIn("attachment;", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
