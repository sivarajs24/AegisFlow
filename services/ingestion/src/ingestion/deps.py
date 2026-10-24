"""Process singletons; tests assign the module globals directly."""
import redis
from sqlalchemy import create_engine

from . import config
from .persistence import PgStore

_store = _redis = None


def store():
    global _store
    if _store is None:
        _store = PgStore(create_engine(config.DATABASE_URL, pool_pre_ping=True))
    return _store


def redis_client():
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(config.REDIS_URL)
    return _redis
