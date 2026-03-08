import redis.asyncio as redis

redis_client: redis.Redis = None

async def init_redis(redis_url: str) -> None:
    """Initializes the Redis connection pool."""
    global redis_client
    redis_client = redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True
    )

async def get_redis() -> redis.Redis:
    """Dependency to get the Redis client."""
    return redis_client

async def close_redis():
    """Closes Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()