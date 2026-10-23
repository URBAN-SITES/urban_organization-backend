from django.core.cache import cache

# A user is online while at least one socket is open. Counters live in the Django cache
# (Redis in prod). shortcut: a crashed worker can leave a stale counter; the 12h TTL
# bounds it, upgrade to heartbeats if presence must be exact.
TTL = 12 * 60 * 60


def _key(user_id) -> str:
    return f"presence:{user_id}"


def mark_online(user_id) -> None:
    cache.add(_key(user_id), 0, TTL)
    cache.incr(_key(user_id))
    cache.touch(_key(user_id), TTL)


def mark_offline(user_id) -> None:
    key = _key(user_id)
    if cache.get(key, 0) > 1:
        cache.decr(key)
    else:
        cache.delete(key)


def is_online(user_id) -> bool:
    return cache.get(_key(user_id), 0) > 0


def online_ids(user_ids) -> list:
    return [user_id for user_id in user_ids if is_online(user_id)]
