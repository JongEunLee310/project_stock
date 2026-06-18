from redis import Redis

from app.core.config import settings


def get_redis_connection() -> Redis:
    return Redis.from_url(settings.REDIS_URL)
