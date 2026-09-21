import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base
from app.models import Candidate, Experience, Skill


class ExtractedProfileTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False)
        self.session_patch = patch.object(main_module, "SessionLocal", self.session_factory)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _candidate(self, owner_id, *, profile_data="{}", name="Pessoa"):
        candidate = Candidate(
            owner_id=owner_id,
            name=name,
            location="Salvador, BA",
            email=f"{owner_id}@example.com",
            phone="71999990000",
            linkedin="https://linkedin.com/in/pessoa",
            target_roles="Analista de RH",
            summary="Resumo profissional",
            profile_data=profile_data,
            resume_filename="base.docx",
        )
        return candidate

    def test_manual_sections_save_and_reload_with_unrelated_metadata(self):
        metadata = {
            "headline": "Coordenação de RH",
            "website": "https://portfolio.example",
            "industry": "Recursos Humanos",
            "photo_data": "data:image/png;base64,abc",
            "contact_metadata": {"source": "verified"},
            "education": [],
            "languages": [],
        }
        with self.session_factory() as db:
            candidate = self._candidate("owner-a", profile_data=json.dumps(metadata))
            candidate.experiences.append(Experience(
                company="Empresa antiga", role="Analista", start_date="2020", end_date="2022", description="Rotinas de RH",
            ))
            candidate.skills.append(Skill(name="Excel", category="Importada", proficiency="Avançada"))
            db.add(candidate)
            db.commit()

        request = main_module.ExtractedProfileUpdateRequest(
            experiences=[{
                "role": "Coordenadora de RH", "company": "Empresa Nova", "start_date": "2022",
                "end_date": "Atual", "description": "Liderança de R&S e desenvolvimento do time.",
            }],
            skills=["Power BI", "Excel", "power bi"],
            education=[{"course": "Gestão de Pessoas", "institution": "UFBA", "period": "2018–2020"}],
            languages=["Português avançado", "Inglês intermediário"],
            manual_sections=["experiences", "skills", "education", "languages"],
        )
        response = main_module.update_extracted_profile(request, {"id": "owner-a"})
        profile = main_module.get_profile({"id": "owner-a"})

        self.assertEqual(response["experiences"], 1)
        self.assertEqual(profile["experience_items"][0]["role"], "Coordenadora de RH")
        self.assertEqual(profile["experience_items"][0]["description"], "Liderança de R&S e desenvolvimento do time.")
        self.assertEqual(profile["skill_items"], ["Power BI", "Excel"])
        self.assertEqual(profile["education_items"][0]["course"], "Gestão de Pessoas")
        self.assertEqual(profile["language_items"], ["Português avançado", "Inglês intermediário"])
        self.assertEqual(
            set(profile["manual_sections"]),
            {"experiences", "skills", "education", "languages"},
        )
        self.assertEqual(profile["photo_data"], metadata["photo_data"])
        self.assertEqual(profile["website"], metadata["website"])
        self.assertEqual(profile["industry"], metadata["industry"])
        with self.session_factory() as db:
            saved = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            saved_data = json.loads(saved.profile_data)
            self.assertEqual(saved_data["contact_metadata"], metadata["contact_metadata"])
            self.assertEqual(saved.skills[1].category, "Importada")
            self.assertEqual(saved.skills[1].proficiency, "Avançada")

    def test_user_without_profile_cannot_write_another_owners_candidate(self):
        with self.session_factory() as db:
            other = self._candidate("owner-b", name="Outra pessoa")
            other.experiences.append(Experience(
                company="Empresa B", role="Gerente", start_date="2020", end_date="", description="Dados privados",
            ))
            db.add(other)
            db.commit()

        request = main_module.ExtractedProfileUpdateRequest(
            experiences=[{"role": "Invasão"}], skills=[], education=[], languages=[],
            manual_sections=["experiences"],
        )
        with self.assertRaises(HTTPException) as raised:
            main_module.update_extracted_profile(request, {"id": "owner-a"})
        self.assertEqual(raised.exception.status_code, 409)
        with self.session_factory() as db:
            unchanged = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-b"))
            self.assertEqual(unchanged.experiences[0].role, "Gerente")
            self.assertEqual(unchanged.experiences[0].description, "Dados privados")

    def test_bounded_request_rejects_oversized_section(self):
        with self.assertRaises(ValidationError):
            main_module.ExtractedProfileUpdateRequest(
                experiences=[{"role": "R"} for _ in range(51)],
                skills=[], education=[], languages=[],
            )
        with self.assertRaises(ValidationError):
            main_module.ExtractedProfileUpdateRequest(
                experiences=[{"role": "x" * 201}],
                skills=[], education=[], languages=[],
            )

    def test_failed_commit_rolls_back_every_extracted_section(self):
        with self.session_factory() as db:
            candidate = self._candidate("owner-a")
            candidate.experiences.append(Experience(
                company="Empresa atual", role="Analista", start_date="2020", end_date="2022", description="Descrição atual",
            ))
            candidate.skills.append(Skill(name="Excel", category="Importada", proficiency="Intermediária"))
            db.add(candidate)
            db.commit()

        class FailingCommitSession(Session):
            def commit(self):
                raise RuntimeError("simulated commit failure")

        failing_factory = sessionmaker(bind=self.engine, autoflush=False, class_=FailingCommitSession)
        request = main_module.ExtractedProfileUpdateRequest(
            experiences=[{"role": "Gestora", "company": "Nova", "description": "Nova descrição"}],
            skills=["Power BI"],
            education=[{"course": "MBA"}],
            languages=["Inglês"],
            manual_sections=["experiences", "skills", "education", "languages"],
        )
        with patch.object(main_module, "SessionLocal", failing_factory):
            with self.assertRaisesRegex(RuntimeError, "simulated commit failure"):
                main_module.update_extracted_profile(request, {"id": "owner-a"})

        with self.session_factory() as db:
            saved = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            self.assertEqual(saved.experiences[0].role, "Analista")
            self.assertEqual(saved.skills[0].name, "Excel")
            self.assertNotIn("_manual_sections", json.loads(saved.profile_data))

    def test_reimport_keeps_manually_edited_categories_empty_parser_values_and_metadata(self):
        metadata = {
            "headline": "Headline ajustada manualmente",
            "website": "https://portfolio.example",
            "industry": "Tecnologia",
            "photo_data": "data:image/png;base64,xyz",
            "contact_metadata": {"verified": True},
            "education": [{"course": "MBA", "institution": "FGV", "period": "2021"}],
            "languages": ["Português fluente"],
            "_manual_sections": ["experiences", "skills"],
        }
        with self.session_factory() as db:
            candidate = self._candidate("owner-a", profile_data=json.dumps(metadata))
            candidate.experiences.append(Experience(
                company="Empresa escolhida", role="HRBP", start_date="2023", end_date="Atual", description="Edição manual.",
            ))
            candidate.skills.append(Skill(name="People Analytics", category="Manual", proficiency="Avançada"))
            db.add(candidate)
            db.commit()

        parsed = {
            "name": "",
            "location": "",
            "email": "",
            "phone": "",
            "linkedin": "",
            "target_roles": "",
            "summary": "",
            "headline": "Headline extraída diferente",
            "experiences": [{"company": "Parser", "role": "Analista", "start_date": "2018", "end_date": "2020", "description": "Parser"}],
            "skills": ["Skill do parser"],
            "education": [],
            "languages": [],
            "source_filename": "nova-versao.docx",
        }
        upload = UploadFile(filename="nova-versao.docx", file=io.BytesIO(b"test"))
        with patch.object(main_module, "_run_document_work", new=AsyncMock(return_value=parsed)):
            result = asyncio.run(main_module.upload_resume(upload, {"id": "owner-a"}))

        self.assertEqual(result["filename"], "nova-versao.docx")
        profile = main_module.get_profile({"id": "owner-a"})
        self.assertEqual(profile["name"], "Pessoa")
        self.assertEqual(profile["summary"], "Resumo profissional")
        self.assertEqual(profile["experience_items"][0]["role"], "HRBP")
        self.assertEqual(profile["experience_items"][0]["description"], "Edição manual.")
        self.assertEqual(profile["skill_items"], ["People Analytics"])
        self.assertEqual(profile["education_items"], metadata["education"])
        self.assertEqual(profile["language_items"], metadata["languages"])
        self.assertEqual(profile["headline"], metadata["headline"])
        self.assertEqual(profile["website"], metadata["website"])
        self.assertEqual(profile["industry"], metadata["industry"])
        self.assertEqual(profile["photo_data"], metadata["photo_data"])
        with self.session_factory() as db:
            saved = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            self.assertEqual(saved.email, "owner-a@example.com")
            self.assertEqual(json.loads(saved.profile_data)["contact_metadata"], metadata["contact_metadata"])

    def test_reimport_with_all_four_sections_missing_keeps_existing_values_and_metadata(self):
        metadata = {
            "headline": "Headline existente",
            "website": "https://site.example",
            "industry": "RH",
            "photo_data": "data:image/png;base64,abc",
            "education": [{"course": "Psicologia", "institution": "UFBA", "period": "2015"}],
            "languages": ["Português fluente"],
            "other_metadata": {"source": "manual"},
        }
        with self.session_factory() as db:
            candidate = self._candidate("owner-a", profile_data=json.dumps(metadata))
            candidate.experiences.append(Experience(
                company="Empresa atual", role="Business Partner", start_date="2021", end_date="Atual", description="Acompanhamento de lideranças.",
            ))
            candidate.skills.append(Skill(name="People Analytics", category="Importada", proficiency="Avançada"))
            db.add(candidate)
            db.commit()

        parsed = {
            "name": "",
            "location": "",
            "email": "",
            "phone": "",
            "linkedin": "",
            "target_roles": "",
            "summary": "",
            "headline": "",
            "source_filename": "resume-com-secoes-vazias.pdf",
            # Deliberately omit experiences, skills, education, and languages.
        }
        upload = UploadFile(filename="resume-com-secoes-vazias.pdf", file=io.BytesIO(b"test"))
        with patch.object(main_module, "_run_document_work", new=AsyncMock(return_value=parsed)):
            result = asyncio.run(main_module.upload_resume(upload, {"id": "owner-a"}))

        self.assertEqual(result["experiences"], 0)
        self.assertEqual(result["skills"], 0)
        self.assertEqual(result["education"], 0)
        self.assertEqual(result["languages"], 0)
        profile = main_module.get_profile({"id": "owner-a"})
        self.assertEqual(profile["experience_items"][0]["role"], "Business Partner")
        self.assertEqual(profile["experience_items"][0]["description"], "Acompanhamento de lideranças.")
        self.assertEqual(profile["skill_items"], ["People Analytics"])
        self.assertEqual(profile["education_items"], metadata["education"])
        self.assertEqual(profile["language_items"], metadata["languages"])
        self.assertEqual(profile["headline"], metadata["headline"])
        self.assertEqual(profile["website"], metadata["website"])
        self.assertEqual(profile["industry"], metadata["industry"])
        self.assertEqual(profile["photo_data"], metadata["photo_data"])
        with self.session_factory() as db:
            saved = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            self.assertEqual(json.loads(saved.profile_data)["other_metadata"], metadata["other_metadata"])

    def test_editing_one_section_does_not_lock_empty_unedited_sections(self):
        metadata = {
            "education": [{"course": "Formação antiga", "institution": "Escola A", "period": "2015"}],
            "languages": ["Português básico"],
            "_manual_sections": ["skills", {}],
        }
        with self.session_factory() as db:
            candidate = self._candidate("owner-a", profile_data=json.dumps(metadata))
            candidate.experiences.append(Experience(
                company="Empresa atual", role="Analista", start_date="2020", end_date="Atual", description="Descrição atual",
            ))
            candidate.skills.append(Skill(name="Excel", category="Importada", proficiency="Intermediária"))
            db.add(candidate)
            db.commit()

        request = main_module.ExtractedProfileUpdateRequest(
            experiences=[], skills=["Power BI"], education=[], languages=[],
            manual_sections=["skills"],
        )
        main_module.update_extracted_profile(request, {"id": "owner-a"})
        parsed = {
            "name": "", "location": "", "email": "", "phone": "", "linkedin": "",
            "target_roles": "", "summary": "", "headline": "", "source_filename": "novo-cv.pdf",
            "education": [{"course": "MBA", "institution": "Universidade B", "period": "2024"}],
            "languages": ["Inglês intermediário"],
        }
        upload = UploadFile(filename="novo-cv.pdf", file=io.BytesIO(b"test"))
        with patch.object(main_module, "_run_document_work", new=AsyncMock(return_value=parsed)):
            asyncio.run(main_module.upload_resume(upload, {"id": "owner-a"}))

        profile = main_module.get_profile({"id": "owner-a"})
        self.assertEqual(profile["skill_items"], ["Power BI"])
        self.assertEqual(profile["education_items"][0]["course"], "MBA")
        self.assertEqual(profile["language_items"], ["Inglês intermediário"])
        self.assertEqual(profile["experience_items"][0]["role"], "Analista")
        self.assertEqual(profile["manual_sections"], ["skills"])


if __name__ == "__main__":
    unittest.main()
