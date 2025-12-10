# RDIP v1.3.0 - Rate Limiter Tests
"""
Unit tests for RateLimitManager.
"""
import pytest
import asyncio
import time
from unittest.mock import patch

from rdip_backend.services.rate_limiter import RateLimitManager


@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    with patch('rdip_backend.services.rate_limiter.get_settings') as mock_settings:
        mock_settings.return_value.groq_rpm_limit = 5
        mock_settings.return_value.gemini_rpm_limit = 2
        return RateLimitManager()


class TestRateLimitManager:
    """Tests for RateLimitManager."""
    
    @pytest.mark.asyncio
    async def test_initial_state_allows_usage(self, rate_limiter):
        """Test that fresh rate limiter allows API usage."""
        assert await rate_limiter.can_use_groq() is True
        assert await rate_limiter.can_use_gemini() is True
    
    @pytest.mark.asyncio
    async def test_records_usage(self, rate_limiter):
        """Test that usage is properly recorded."""
        await rate_limiter.record_groq_usage()
        stats = await rate_limiter.get_stats()
        assert stats["groq_used"] == 1
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter):
        """Test that rate limit is enforced."""
        for _ in range(5):
            await rate_limiter.record_groq_usage()
        
        assert await rate_limiter.can_use_groq() is False
    
    @pytest.mark.asyncio
    async def test_separate_limits(self, rate_limiter):
        """Test that Groq and Gemini have separate limits."""
        for _ in range(5):
            await rate_limiter.record_groq_usage()
        
        assert await rate_limiter.can_use_groq() is False
        assert await rate_limiter.can_use_gemini() is True
    
    @pytest.mark.asyncio
    async def test_stats_accuracy(self, rate_limiter):
        """Test that stats are accurate."""
        await rate_limiter.record_groq_usage()
        await rate_limiter.record_groq_usage()
        await rate_limiter.record_gemini_usage()
        
        stats = await rate_limiter.get_stats()
        
        assert stats["groq_used"] == 2
        assert stats["groq_limit"] == 5
        assert stats["groq_available"] == 3
        assert stats["gemini_used"] == 1
        assert stats["gemini_limit"] == 2
        assert stats["gemini_available"] == 1