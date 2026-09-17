import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main as main_module


class ProcessingLimitTest(unittest.IsolatedAsyncioTestCase):
    async def test_document_work_has_hard_timeout(self):
        async def slow_thread(*args):
            await asyncio.sleep(0.05)

        with (
            patch.object(main_module, "DOCUMENT_PROCESSING_TIMEOUT", 0.001),
            patch.object(main_module, "run_in_threadpool", side_effect=slow_thread),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main_module._run_document_work(lambda: None)
        self.assertEqual(raised.exception.status_code, 504)


if __name__ == "__main__":
    unittest.main()
