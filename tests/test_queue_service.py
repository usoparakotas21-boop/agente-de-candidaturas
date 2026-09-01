import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import utc_now
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
