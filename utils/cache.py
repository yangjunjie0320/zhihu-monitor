"""DiskCache factory for persistent storage."""

import os

import diskcache


def get_cache(data_dir: str) -> diskcache.Cache:
    """Create or open a diskcache.Cache at {data_dir}/cache.

    Args:
        data_dir: Base data directory.

    Returns:
        A diskcache.Cache instance.
    """
    cache_dir = os.path.join(data_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return diskcache.Cache(cache_dir)
