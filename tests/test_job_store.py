# RDIP v1.3.0 - Job Store Tests
"""
Unit tests for JobStore.
"""
import pytest
from datetime import datetime
from unittest.mock import patch

from rdip_backend.models import JobStatus
from rdip_backend.services.job_store import JobStore


@pytest.fixture
def job_store():
    """Create a job store instance for testing."""
    with patch('rdip_backend.services.job_store.get_settings') as mock_settings:
        mock_settings.return_value.job_ttl_seconds = 3600
        return JobStore()


class TestJobStore:
    """Tests for JobStore."""
    
    def test_add_and_get_job(self, job_store):
        """Test adding and retrieving a job."""
        job = JobStatus(
            job_id="test-123",
            status="queued",
            progress=0,
        )
        job_store.add("test-123", job)
        
        retrieved = job_store.get("test-123")
        assert retrieved is not None
        assert retrieved.job_id == "test-123"
        assert retrieved.status == "queued"
    
    def test_get_nonexistent_job(self, job_store):
        """Test retrieving a non-existent job returns None."""
        assert job_store.get("nonexistent") is None
    
    def test_update_job(self, job_store):
        """Test updating a job's status."""
        job = JobStatus(
            job_id="test-123",
            status="queued",
            progress=0,
        )
        job_store.add("test-123", job)
        
        updated_job = JobStatus(
            job_id="test-123",
            status="processing",
            progress=50,
        )
        result = job_store.update("test-123", updated_job)
        
        assert result is True
        retrieved = job_store.get("test-123")
        assert retrieved.status == "processing"
        assert retrieved.progress == 50
    
    def test_update_nonexistent_job(self, job_store):
        """Test updating a non-existent job returns False."""
        job = JobStatus(job_id="test", status="queued", progress=0)
        result = job_store.update("nonexistent", job)
        assert result is False
    
    def test_remove_job(self, job_store):
        """Test removing a job."""
        job = JobStatus(job_id="test-123", status="queued", progress=0)
        job_store.add("test-123", job)
        
        result = job_store.remove("test-123")
        assert result is True
        assert job_store.get("test-123") is None
    
    def test_stats(self, job_store):
        """Test job statistics."""
        jobs = [
            JobStatus(job_id="1", status="queued", progress=0),
            JobStatus(job_id="2", status="processing", progress=50),
            JobStatus(job_id="3", status="completed", progress=100),
            JobStatus(job_id="4", status="failed", progress=30),
        ]
        
        for job in jobs:
            job_store.add(job.job_id, job)
        
        stats = job_store.stats()
        
        assert stats["queued"] == 1
        assert stats["processing"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        assert stats["total"] == 4
    
    def test_clear(self, job_store):
        """Test clearing all jobs."""
        for i in range(5):
            job = JobStatus(job_id=f"test-{i}", status="queued", progress=0)
            job_store.add(f"test-{i}", job)
        
        count = job_store.clear()
        assert count == 5
        assert job_store.stats()["total"] == 0