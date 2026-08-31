import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.queue_service import approve, enqueue, get_summary, list_items, reject


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

