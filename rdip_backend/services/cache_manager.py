# RDIP v1.3.0 - Dual Cache Manager Service
"""
Two-level caching system:
- Hot cache: In-memory dictionary with TTL
- Cold cache: DuckDB (persistent storage for historical data)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

import duckdb

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger

logger = get_logger(__name__)


class InMemoryCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, ttl: int = 86400):
        self._data: Dict[str, tuple[float, str]] = {}
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[str]:
        """Get value if exists and not expired."""
        if key in self._data:
            timestamp, value = self._data[key]
            if time.time() - timestamp < self._ttl:
                return value
            else:
                del self._data[key]
        return None
    
    def setex(self, key: str, ttl: int, value: str) -> None:
        """Set value with expiration."""
        self._data[key] = (time.time(), value)
    
    def delete(self, key: str) -> None:
        """Delete key."""
        self._data.pop(key, None)
    
    def dbsize(self) -> int:
        """Return number of keys."""
        self._cleanup()
        return len(self._data)
    
    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (ts, _) in self._data.items() if now - ts >= self._ttl]
        for k in expired:
            del self._data[k]


class DualCacheManager:
    """
    Two-level cache manager for analysis results.
    
    Hot cache: Fast, in-memory with TTL (24h default).
    Cold cache (DuckDB): Persistent storage for long-term retrieval.
    """
    
    def __init__(
        self,
        hot_db: str | None = None,
        cold_db: str | None = None,
    ) -> None:
        settings = get_settings()
        
        cold_db = cold_db or settings.cold_cache_db
        self._ttl = settings.hot_cache_ttl
        
        for db_path in [cold_db]:
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        
        self._hot = InMemoryCache(ttl=self._ttl)
        logger.info("Hot cache initialized (in-memory)")
        
        self._cold = duckdb.connect(cold_db)
        self._init_cold_schema()
        logger.info(f"Cold cache initialized: {cold_db}")
    
    def _init_cold_schema(self) -> None:
        """Initialize DuckDB schema for cold cache."""
        self._cold.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                url_hash VARCHAR PRIMARY KEY,
                url VARCHAR NOT NULL,
                analysis JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        """)
        
        try:
            self._cold.execute(
                "CREATE INDEX IF NOT EXISTS idx_analyses_url ON analyses(url)"
            )
        except Exception:
            pass
    
    @staticmethod
    def _hash_url(url: str) -> str:
        normalized = url.strip().lower().rstrip("/")
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    async def get(self, url: str) -> Optional[Dict[str, Any]]:
        key = self._hash_url(url)
        
        try:
            data = self._hot.get(key)
            if data:
                logger.debug(f"Hot cache hit for {key}")
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Hot cache read error: {e}")
        
        try:
            row = self._cold.execute(
                "SELECT analysis FROM analyses WHERE url_hash = ?",
                [key],
            ).fetchone()
            
            if row:
                analysis = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                
                try:
                    self._hot.setex(key, self._ttl, json.dumps(analysis))
                except Exception as e:
                    logger.warning(f"Failed to rehydrate hot cache: {e}")
                
                try:
                    self._cold.execute(
                        """
                        UPDATE analyses 
                        SET access_count = access_count + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE url_hash = ?
                        """,
                        [key],
                    )
                except Exception as e:
                    logger.warning(f"Failed to update access count: {e}")
                
                logger.debug(f"Cold cache hit for {key}")
                return analysis
        except Exception as e:
            logger.warning(f"Cold cache read error: {e}")
        
        logger.debug(f"Cache miss for {key}")
        return None
    
    async def save(self, url: str, analysis: Dict[str, Any]) -> None:
        key = self._hash_url(url)
        serialized = json.dumps(analysis, ensure_ascii=False)
        
        try:
            self._hot.setex(key, self._ttl, serialized)
            logger.debug(f"Saved to hot cache: {key}")
        except Exception as e:
            logger.error(f"Hot cache save error: {e}")
        
        try:
            self._cold.execute(
                """
                INSERT INTO analyses (url_hash, url, analysis, access_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT (url_hash) DO UPDATE SET
                    analysis = EXCLUDED.analysis,
                    updated_at = CURRENT_TIMESTAMP,
                    access_count = analyses.access_count + 1
                """,
                [key, url, serialized],
            )
            logger.debug(f"Saved to cold cache: {key}")
        except Exception as e:
            logger.error(f"Cold cache save error: {e}")
    
    async def invalidate(self, url: str) -> None:
        key = self._hash_url(url)
        
        try:
            self._hot.delete(key)
            logger.debug(f"Invalidated hot cache: {key}")
        except Exception as e:
            logger.warning(f"Hot cache invalidation error: {e}")
        
        try:
            self._cold.execute(
                "DELETE FROM analyses WHERE url_hash = ?",
                [key],
            )
            logger.debug(f"Invalidated cold cache: {key}")
        except Exception as e:
            logger.warning(f"Cold cache invalidation error: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        
        try:
            stats["hot_cache_keys"] = self._hot.dbsize()
        except Exception:
            stats["hot_cache_keys"] = "error"
        
        try:
            row = self._cold.execute(
                "SELECT COUNT(*), SUM(access_count) FROM analyses"
            ).fetchone()
            if row:
                stats["cold_cache_entries"] = row[0] or 0
                stats["total_accesses"] = row[1] or 0
        except Exception:
            stats["cold_cache_entries"] = "error"
            stats["total_accesses"] = "error"
        
        return stats
    
    def close(self) -> None:
        try:
            self._cold.close()
            logger.info("Cold cache connection closed")
        except Exception as e:
            logger.warning(f"Error closing cold cache: {e}")
