"""One Redis connection pool per process for the Django cache.

Django builds a cache client (and so a connection pool) per thread. Under daphne every
`sync_to_async` worker thread opened its own pool, and the free Redis plan (about 50
clients) ran out: `users/me` and `ws-ticket` failed with "max number of clients reached".
A shared BlockingConnectionPool caps the connections and makes a thread wait for a free
one instead of failing.
"""

import threading

import redis

_lock = threading.Lock()
_pools: dict[str, redis.BlockingConnectionPool] = {}


class SharedConnectionPool(redis.BlockingConnectionPool):
    @classmethod
    def from_url(cls, url, **kwargs):
        with _lock:
            pool = _pools.get(url)
            if pool is None:
                pool = _pools[url] = super().from_url(url, **kwargs)
            return pool
