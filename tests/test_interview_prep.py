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

    def _set_analysis_data(self, value):
        db = self.session_factory()
        try:
            application = db.get(Application, self.application_id)
            application.analysis_data = value
            db.commit()
        finally:
            db.close()

    def test_malformed_analysis_shapes_fall_back_to_general_questions(self):
        for raw_analysis in ("[\"unexpected\"]", "{invalid json"):
            with self.subTest(analysis=raw_analysis):
                self._set_analysis_data(raw_analysis)
                with patch.object(main_module, "SessionLocal", self.session_factory):
                    result = main_module.interview_prep(self.application_id, {"id": "owner-a"})

                self.assertEqual(result["gaps"], [])
                self.assertEqual(result["strengths"], [])
                self.assertEqual(len(result["questions"]), 3)

    def test_analysis_fields_are_normalized_and_bounded(self):
        self._set_analysis_data(json.dumps({
            "gaps": "not a list",
            "strengths": ["  " + "S" * 400, 23, "Força concreta"],
        }))

        with patch.object(main_module, "SessionLocal", self.session_factory):
            result = main_module.interview_prep(self.application_id, {"id": "owner-a"})

        self.assertEqual(result["gaps"], [])
        self.assertEqual(result["strengths"], ["S" * 300, "Força concreta"])
        self.assertEqual(len(result["questions"]), 3)


if __name__ == "__main__":
    unittest.main()
