import unittest
from unittest.mock import Mock, patch

from app import distributed_rate_limit


class DistributedRateLimitTest(unittest.TestCase):
    def test_check_uses_atomic_eval_and_blocks_after_limit(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"result": 3}
        with patch.dict(
            "os.environ",
            {
                "UPSTASH_REDIS_REST_URL": "https://redis.example",
                "UPSTASH_REDIS_REST_TOKEN": "token-not-printed",
            },
            clear=False,
        ), patch.object(distributed_rate_limit.requests, "post", return_value=response) as post:
            blocked, retry_after = distributed_rate_limit.check(
                ["login:ip:198.51.100.10"],
                2,
                60,
            )

        self.assertTrue(blocked)
        self.assertEqual(retry_after, 60)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://redis.example")
        command = post.call_args.kwargs["json"]
        self.assertEqual(command[0], "EVAL")
        self.assertIn("redis.call('INCR', KEYS[1])", command[1])
        self.assertEqual(command[2:], [1, "login:ip:198.51.100.10", "60"])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer token-not-printed")

    def test_unconfigured_store_is_detected(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(distributed_rate_limit.is_configured())


if __name__ == "__main__":
    unittest.main()
