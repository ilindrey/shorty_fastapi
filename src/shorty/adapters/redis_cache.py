"""Redis adapter for the redirect cache.

Only the `subpart -> url` mapping is cached here - never a view, a queryset,
or the Link aggregate itself, keeping the cache focused on redirect lookups.
"""

from redis.asyncio import Redis

from shorty.service_layer.ports import AbstractLinkCache


class RedisLinkCache(AbstractLinkCache):
    """Redis-backed implementation of AbstractLinkCache.

    Entries carry a TTL mirroring the Postgres retention period, as a safety
    net in case the `LinkExpired` event handler is ever skipped.
    """

    def __init__(self, client: Redis) -> None:
        """Store the Redis client used by this adapter."""
        self._client = client

    async def get(self, subpart: str) -> str | None:
        """Return the cached url for `subpart`, or None on a cache miss."""
        value = await self._client.get(subpart)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, subpart: str, url: str, ttl_seconds: int) -> None:
        """Cache `url` under `subpart` with the requested TTL."""
        await self._client.set(subpart, url, ex=ttl_seconds)

    async def delete(self, subpart: str) -> None:
        """Evict `subpart` from the cache."""
        await self._client.delete(subpart)
