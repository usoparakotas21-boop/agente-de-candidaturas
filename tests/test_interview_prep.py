import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Application, Job


class InterviewPrepTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        job = Job(
            owner_id="owner-a", source="manual", external_id="prep-1",
            company="Empresa A", title="Coordenador de RH", location="Salvador",
            modality="hibrido", url="https://example.test/prep", description="Vaga",
        )
        other_job = Job(
            owner_id="owner-b", source="manual", external_id="prep-2",
            company="Empresa B", title="Analista", location="Recife",
            modality="remoto", url="https://example.test/other", description="Vaga",
        )
        db.add_all([job, other_job])
        db.flush()
        db.add_all([
            Application(
                job_id=job.id, status="ENTREVISTA", analysis_score=76,
                analysis_data=json.dumps({"gaps": ["Power Query"], "strengths": ["Recursos Humanos"]}),
            ),
            Application(job_id=other_job.id, status="ENTREVISTA"),
        ])
        db.commit()
        self.application_id = job.application.id
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_prep_uses_owner_scoped_gaps(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            result = main_module.interview_prep(self.application_id, {"id": "owner-a"})

        self.assertEqual(result["job_title"], "Coordenador de RH")
        self.assertEqual(result["gaps"], ["Power Query"])
        self.assertIn("Power Query", result["questions"][0])

    def test_prep_does_not_expose_other_owner(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            with self.assertRaises(main_module.HTTPException) as raised:
                main_module.interview_prep(self.application_id, {"id": "owner-b"})

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
