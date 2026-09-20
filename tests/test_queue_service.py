import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Application, ApplicationEvent, Job, utc_now
from app.queue_service import (
    QueueRiskBlockedError,
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
            {
                "title": "Business Partner",
                "company": "Empresa Teste",
                "url": "https://empresa.test/vagas/123",
                "salary_min": 6000,
                "salary_max": 8000,
                "description": (
                    "Responsabilidades: conduzir os processos de recrutamento, seleção e integração, "
                    "acompanhar indicadores e apoiar líderes. Requisitos: experiência em RH, "
                    "comunicação, organização e domínio das ferramentas do setor. "
                    "A empresa oferece benefícios, salário compatível e ambiente colaborativo. "
                    "Todas as etapas são comunicadas pelo portal oficial de carreiras."
                ),
            },
            {"decision": "CAPTURAR", "reasons": [], "engine_version": "test"},
            "teste",
        )

        summary = get_summary(self.session, None)
        self.assertEqual(summary["revisar"]["pendente"], 1)
        self.assertEqual(summary["capturar"]["total"], 1)

    def test_health_risk_signals_are_recalculated_from_listing_content(self):
        item = enqueue(
            self.session,
            None,
            {
                "title": "Analista de RH",
                "company": "Empresa Teste",
                "description": "Para participar da seleção, pague uma taxa de inscrição via Pix antes da entrevista.",
            },
            {"decision": "CAPTURAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]

        self.assertLessEqual(item.health_score, 15)
        self.assertEqual(item.health_band, "SUSPEITA")
        self.assertTrue(item.fraud_suspected)
        self.assertIn("PEDIDO_PAGAMENTO", {signal["code"] for signal in item.health_signals})
        self.assertEqual(item.decision, "DESCARTAR")

    def test_approval_rechecks_legacy_content_and_blocks_fraud_but_allows_rejection(self):
        suspected = enqueue(
            self.session,
            None,
            {
                "title": "Analista de RH",
                "company": "Empresa Teste",
                "description": "Para participar da seleção, pague uma taxa de inscrição via Pix antes da entrevista.",
            },
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]
        # Simula registro legado com os campos de risco antigos ou ausentes.
        suspected.health_band = None
        suspected.health_score = None
        suspected.health_signals = []
        suspected.fraud_suspected = False
        self.session.commit()

        with self.assertRaisesRegex(QueueRiskBlockedError, "bloqueada por sinais de fraude"):
            approve(self.session, None, suspected.id)
        self.assertEqual(suspected.status, "PENDENTE")
        self.assertTrue(suspected.fraud_suspected)

        rejected = reject(self.session, None, suspected.id, "Fonte suspeita")
        self.assertEqual(rejected["status"], "RECUSADO")
        self.assertEqual(suspected.status, "RECUSADO")

    def test_duvidosa_opportunity_can_be_approved_manually(self):
        item = enqueue(
            self.session,
            None,
            {"title": "Vaga duvidosa", "health_band": "DUVIDOSA", "fraud_suspected": False},
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]

        result = approve(self.session, None, item.id)

        self.assertEqual(result["status"], "PROMOVIDO")
        self.assertIsNotNone(result["job_id"])
        application = self.session.query(Application).filter_by(job_id=result["job_id"]).one()
        self.assertEqual(application.health_band, "SUSPEITA")
        self.assertFalse(application.fraud_suspected)

    def test_automatic_promotion_never_skips_fraud_check(self):
        item = enqueue(
            self.session,
            None,
            {
                "title": "Analista de RH",
                "company": "Empresa Teste",
                "description": "Para participar da seleção, pague uma taxa de inscrição via Pix antes da entrevista.",
            },
            {"decision": "AUTOMATICA", "reasons": [], "engine_version": "test"},
            "teste",
        )[0]

        self.assertEqual(item.status, "PENDENTE")
        self.assertEqual(item.decision, "DESCARTAR")
        self.assertTrue(item.fraud_suspected)
        self.assertIsNone(item.job_id)

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
                "salary": "R$ 6.000 a R$ 8.000",
                "modality_confidence": 95,
                "salary_confidence": 80,
                "contract_confidence": 90,
                "url": "https://example.test/rh",
                "salary_min": 6000,
                "salary_max": 8000,
                "confidence_overall": 88,
                "description": (
                    "Responsabilidades: conduzir recrutamento e seleção, apoiar gestores e acompanhar indicadores. "
                    "Requisitos: experiência com RH, comunicação e organização. "
                    "A empresa oferece benefícios, salário compatível e processo seletivo pelo portal oficial."
                ),
            },
            {"decision": "REVISAR", "reasons": [], "engine_version": "test"},
            "texto",
        )[0]

        self.assertEqual(item.contract_type, "CLT")
        self.assertEqual(item.salary, "R$ 6.000 a R$ 8.000")
        self.assertEqual(item.modality_confidence, 95)
        self.assertEqual(item.salary_confidence, 80)
        self.assertEqual(item.contract_confidence, 90)

        result = approve(self.session, None, item.id)
        job = self.session.query(Job).filter_by(id=result["job_id"]).one()
        self.assertEqual(job.contract_type, "CLT")
        self.assertEqual(job.modality, "Híbrido")
        self.assertEqual(job.salary, "R$ 6.000 a R$ 8.000")
        self.assertEqual(job.salary_min, 6000)
        self.assertEqual(job.salary_max, 8000)
        self.assertEqual(job.modality_confidence, 95)
        self.assertEqual(job.salary_confidence, 80)
        self.assertEqual(job.contract_confidence, 90)
        application = self.session.query(Application).filter_by(job_id=job.id).one()
        self.assertEqual(application.health_score, item.health_score)
        self.assertEqual(application.health_band, item.health_band)
        self.assertEqual(application.health_signals, item.health_signals)
        self.assertEqual(application.capture_confidence, 88)
