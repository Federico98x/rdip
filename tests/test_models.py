# RDIP v1.3.0 - Model Tests
"""
Unit tests for Pydantic models.
"""
import pytest
from datetime import datetime

from rdip_backend.models import (
    AnalyzeRequest,
    ThreadContext,
    SentimentObj,
    AnalysisResult,
    JobStatus,
)


class TestAnalyzeRequest:
    """Tests for AnalyzeRequest model."""
    
    def test_valid_reddit_url(self):
        """Test validation of valid Reddit URLs."""
        valid_urls = [
            "https://www.reddit.com/r/python/comments/abc123/test",
            "https://reddit.com/r/programming/comments/xyz789/hello",
            "https://redd.it/abc123",
            "https://old.reddit.com/r/test/comments/123abc/post",
        ]
        
        for url in valid_urls:
            request = AnalyzeRequest(url=url)
            assert request.url == url.strip().rstrip("/")
    
    def test_invalid_reddit_url(self):
        """Test validation rejects invalid URLs."""
        invalid_urls = [
            "https://google.com",
            "https://twitter.com/user/status/123",
            "not a url",
            "",
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValueError):
                AnalyzeRequest(url=url)
    
    def test_default_values(self):
        """Test default values for optional fields."""
        request = AnalyzeRequest(url="https://reddit.com/r/test/comments/123/x")
        assert request.force_refresh is False
        assert request.deep_scan is False


class TestSentimentObj:
    """Tests for SentimentObj model."""
    
    def test_valid_sentiment(self):
        """Test creation of valid sentiment object."""
        sentiment = SentimentObj(
            label="Positivo",
            score=0.85,
            details="Very positive discussion"
        )
        assert sentiment.label == "Positivo"
        assert sentiment.score == 0.85
    
    def test_score_bounds(self):
        """Test score must be between 0 and 1."""
        with pytest.raises(ValueError):
            SentimentObj(label="Positivo", score=1.5, details="test")
        
        with pytest.raises(ValueError):
            SentimentObj(label="Negativo", score=-0.1, details="test")


class TestJobStatus:
    """Tests for JobStatus model."""
    
    def test_job_status_creation(self):
        """Test creation of job status."""
        job = JobStatus(
            job_id="test-123",
            status="queued",
            progress=0,
        )
        assert job.job_id == "test-123"
        assert job.status == "queued"
        assert job.progress == 0
        assert job.result is None
        assert job.error is None
    
    def test_completed_job_with_result(self):
        """Test completed job with result."""
        job = JobStatus(
            job_id="test-456",
            status="completed",
            progress=100,
            result={"summary": "test"},
        )
        assert job.status == "completed"
        assert job.result == {"summary": "test"}
    
    def test_failed_job_with_error(self):
        """Test failed job with error message."""
        job = JobStatus(
            job_id="test-789",
            status="failed",
            progress=50,
            error="Something went wrong",
        )
        assert job.status == "failed"
        assert job.error == "Something went wrong"