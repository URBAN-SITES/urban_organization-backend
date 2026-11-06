import threading

from django.core.cache.backends.redis import RedisCacheClient
from django.test import SimpleTestCase

from core.cache import SharedConnectionPool

URL = "redis://cache-test.invalid:6379/0"  # never contacted: pools connect lazily


class SharedPoolTests(SimpleTestCase):
    def test_cache_clients_of_every_thread_share_one_bounded_pool(self):
        pools = []

        def client_pool():
            client = RedisCacheClient(
                [URL],
                pool_class="core.cache.SharedConnectionPool",
                max_connections=10,
                timeout=5,
            )
            pools.append(client._get_connection_pool(write=True))

        threads = [threading.Thread(target=client_pool) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len({id(pool) for pool in pools}), 1)
        self.assertIsInstance(pools[0], SharedConnectionPool)
        self.assertEqual(pools[0].max_connections, 10)
