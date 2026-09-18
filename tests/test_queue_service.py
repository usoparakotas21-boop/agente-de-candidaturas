import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Application, ApplicationEvent, Job, utc_now
from app.queue_service import (
    approve,
    enqueue,
    expire_stale,
    get_summary,
    list_items,
    reject,
)


class QueueServiceLocalModeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp_dir.name) / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _enqueue(self, title):
        return enqueue(
            self.session,
            None,
            {"title": title, "company": "Empresa Teste", "location": "Remoto"},
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]

    def test_local_mode_approves_and_rejects_items(self):
        approved_item = self._enqueue("Analista de Dados")
        rejected_item = self._enqueue("Desenvolvedor Python")

        approved = approve(self.session, None, approved_item.id)
        rejected = reject(self.session, None, rejected_item.id, "Nao aderente")

        self.assertEqual(approved["status"], "PROMOVIDO")
        self.assertIsNotNone(approved["job_id"])
        application = self.session.query(Application).filter_by(
            job_id=approved["job_id"]
        ).one()
        self.assertEqual(application.status, "IDENTIFICADA")
        self.assertEqual(application.queue_decision, "REVISAR")
        self.assertEqual(
            self.session.query(ApplicationEvent)
            .filter_by(application_id=application.id)
            .count(),
            1,
        )
        self.assertEqual(rejected["status"], "RECUSADO")
        items, total = list_items(self.session, None)
        self.assertEqual(total, 2)
        self.assertEqual({item.owner_id for item in items}, {"local_user"})
        self.assertEqual(get_summary(self.session, None)["revisar"]["total"], 2)

    def test_expiration_is_scoped_to_owner(self):
        owner_a = enqueue(
            self.session,
            "owner-a",
            {"title": "Vaga A", "company": "Empresa A"},
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]
        owner_b = enqueue(
            self.session,
            "owner-b",
            {"title": "Vaga B", "company": "Empresa B"},
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]
        old_date = utc_now() - timedelta(days=30)
        owner_a.captured_at = old_date
        owner_b.captured_at = old_date
        self.session.commit()

        expired = expire_stale(self.session, 14, owner_id="owner-a")
        self.session.refresh(owner_a)
        self.session.refresh(owner_b)

        self.assertEqual(expired, 1)
        self.assertEqual(owner_a.status, "EXPIRADO")
        self.assertEqual(owner_b.status, "PENDENTE")

    def test_capturar_items_count_as_pending_review(self):
        enqueue(
            self.session,
            None,
            {"title": "Business Partner", "company": "Empresa Teste"},
            {"decision": "CAPTURAR", "reasons": [], "engine_version": "test"},
            "teste",
        )

        summary = get_summary(self.session, None)
        self.assertEqual(summary["revisar"]["pendente"], 1)
        self.assertEqual(summary["capturar"]["total"], 1)

    def test_health_risk_signals_are_preserved_for_review(self):
        item = enqueue(
            self.session,
            None,
            {
                "title": "Oportunidade suspeita",
                "company": "Empresa Teste",
                "health_score": 10,
                "health_band": "SUSPEITA",
                "health_signals": [{"code": "PEDIDO_PAGAMENTO", "label": "Pede pagamento"}],
                "fraud_suspected": True,
            },
            {"decision": "DESCARTAR", "reasons": ["SAUDE_SUSPEITA"], "engine_version": "test"},
            "teste",
        )[0]

        self.assertEqual(item.health_score, 10)
        self.assertEqual(item.health_band, "SUSPEITA")
        self.assertTrue(item.fraud_suspected)
        self.assertEqual(item.health_signals[0]["code"], "PEDIDO_PAGAMENTO")

    def test_structured_intake_fields_follow_item_into_job(self):
        item = enqueue(
            self.session,
            None,
            {
                "title": "Analista de RH",
                "company": "Empresa Teste",
                "location": "Salvador/BA",
                "modality": "Híbrido",
                "contract_type": "CLT",
                "modality_confidence": 95,
                "salary_confidence": 80,
                "contract_confidence": 90,
                "url": "https://example.test/rh",
            },
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "texto",
        )[0]

        self.assertEqual(item.contract_type, "CLT")
        self.assertEqual(item.modality_confidence, 95)
        self.assertEqual(item.salary_confidence, 80)
        self.assertEqual(item.contract_confidence, 90)

        result = approve(self.session, None, item.id)
        job = self.session.query(Job).filter_by(id=result["job_id"]).one()
        self.assertEqual(job.contract_type, "CLT")
        self.assertEqual(job.modality_confidence, 95)
        self.assertEqual(job.salary_confidence, 80)
        self.assertEqual(job.contract_confidence, 90)
