# RDIP v1.3.0 - Rate Limiter Service
"""
Proactive rate limiting using rolling window algorithm.
Thread-safe implementation using asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitManager:
    """
    Rate limiter using rolling window (60 seconds) for API calls.
    
    Supports separate limits for Groq and Gemini APIs.
    Thread-safe through asyncio.Lock.
    
    Example:
        limiter = RateLimitManager()
        if await limiter.can_use_groq():
            await limiter.record_groq_usage()
            # make API call
    """
    
    def __init__(self) -> None:
        """Initialize rate limiter with configured limits."""
        settings = get_settings()
        
        # Request history queues (timestamps)
        self._groq_history: Deque[float] = deque(maxlen=500)
        self._gemini_history: Deque[float] = deque(maxlen=100)
        
        # Configured limits (with safety margin)
        self._groq_limit_rpm = settings.groq_rpm_limit
        self._gemini_limit_rpm = settings.gemini_rpm_limit
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Window size in seconds
        self._window_seconds = 60.0
        
        logger.info(
            f"Rate limiter initialized: Groq={self._groq_limit_rpm}/min, "
            f"Gemini={self._gemini_limit_rpm}/min"
        )
    
    async def _clean_history(self, history: Deque[float]) -> None:
        """
        Remove expired entries from history (older than window).
        
        Args:
            history: Deque of timestamps to clean.
        """
        now = time.time()
        cutoff = now - self._window_seconds
        
        while history and history[0] < cutoff:
            history.popleft()
    
    async def can_use_groq(self) -> bool:
        """
        Check if Groq API can be called within rate limits.
        
        Returns:
            True if under the rate limit, False otherwise.
        """
        async with self._lock:
            await self._clean_history(self._groq_history)
            can_use = len(self._groq_history) < self._groq_limit_rpm
            
            if not can_use:
                logger.warning(
                    f"Groq rate limit reached: {len(self._groq_history)}/{self._groq_limit_rpm}"
                )
            
            return can_use
    
    async def can_use_gemini(self) -> bool:
        """
        Check if Gemini API can be called within rate limits.
        
        Returns:
            True if under the rate limit, False otherwise.
        """
        async with self._lock:
            await self._clean_history(self._gemini_history)
            can_use = len(self._gemini_history) < self._gemini_limit_rpm
            
            if not can_use:
                logger.warning(
                    f"Gemini rate limit reached: {len(self._gemini_history)}/{self._gemini_limit_rpm}"
                )
            
            return can_use
    
    async def record_groq_usage(self) -> None:
        """Record a Groq API call timestamp."""
        async with self._lock:
            self._groq_history.append(time.time())
            logger.debug(f"Groq usage recorded: {len(self._groq_history)}/{self._groq_limit_rpm}")
    
    async def record_gemini_usage(self) -> None:
        """Record a Gemini API call timestamp."""
        async with self._lock:
            self._gemini_history.append(time.time())
            logger.debug(f"Gemini usage recorded: {len(self._gemini_history)}/{self._gemini_limit_rpm}")
    
    async def get_stats(self) -> dict[str, int]:
        """
        Get current rate limiting statistics.
        
        Returns:
            Dictionary with current usage counts.
        """
        async with self._lock:
            await self._clean_history(self._groq_history)
            await self._clean_history(self._gemini_history)
            
            return {
                "groq_used": len(self._groq_history),
                "groq_limit": self._groq_limit_rpm,
                "groq_available": self._groq_limit_rpm - len(self._groq_history),
                "gemini_used": len(self._gemini_history),
                "gemini_limit": self._gemini_limit_rpm,
                "gemini_available": self._gemini_limit_rpm - len(self._gemini_history),
            }
    
    async def wait_for_groq(self, timeout: float = 60.0) -> bool:
        """
        Wait until Groq API is available or timeout.
        
        Args:
            timeout: Maximum seconds to wait.
        
        Returns:
            True if available, False if timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            if await self.can_use_groq():
                return True
            await asyncio.sleep(1.0)
        return False
    
    async def wait_for_gemini(self, timeout: float = 60.0) -> bool:
        """
        Wait until Gemini API is available or timeout.
        
        Args:
            timeout: Maximum seconds to wait.
        
        Returns:
            True if available, False if timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            if await self.can_use_gemini():
                return True
            await asyncio.sleep(1.0)
        return False