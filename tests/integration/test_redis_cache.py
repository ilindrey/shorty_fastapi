"""Integration tests for RedisLinkCache against a real Redis instance."""

from redis.asyncio import Redis

from shorty.adapters.redis_cache import RedisLinkCache


async def test_set_then_get_round_trip(redis_client: Redis) -> None:
    cache = RedisLinkCache(redis_client)

    await cache.set('abc123', 'https://example.com', 60)

    assert await cache.get('abc123') == 'https://example.com'


async def test_get_missing_key_returns_none(redis_client: Redis) -> None:
    cache = RedisLinkCache(redis_client)

    assert await cache.get('missing') is None


async def test_set_applies_ttl(redis_client: Redis) -> None:
    cache = RedisLinkCache(redis_client)

    await cache.set('abc123', 'https://example.com', 60)

    ttl = await redis_client.ttl('abc123')
    assert 0 < ttl <= 60


async def test_delete_evicts_key(redis_client: Redis) -> None:
    cache = RedisLinkCache(redis_client)
    await cache.set('abc123', 'https://example.com', 60)

    await cache.delete('abc123')

    assert await cache.get('abc123') is None
