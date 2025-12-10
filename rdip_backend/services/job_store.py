# RDIP v1.3.0 - Job Store Service
"""
In-memory job status storage with automatic TTL-based cleanup.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger
from rdip_backend.models import JobStatus

logger = get_logger(__name__)


class JobStore:
    """
    In-memory storage for job status tracking.
    
    Features:
    - Simple dict-based storage for job status objects
    - Automatic cleanup of expired jobs based on TTL
    - Thread-safe operations (single-threaded async context)
    
    Example:
        store = JobStore()
        store.add(job_id, JobStatus(...))
        status = store.get(job_id)
        store.update(job_id, updated_status)
    """
    
    def __init__(self, ttl: int | None = None) -> None:
        """
        Initialize job store.
        
        Args:
            ttl: Time-to-live for jobs in seconds. Defaults to config value.
        """
        settings = get_settings()
        self._ttl = ttl or settings.job_ttl_seconds
        
        # Storage for job status objects
        self._jobs: Dict[str, JobStatus] = {}
        
        # Timestamps for TTL tracking
        self._created_at: Dict[str, float] = {}
        
        logger.info(f"Job store initialized with TTL={self._ttl}s")
    
    def add(self, job_id: str, status: JobStatus) -> None:
        """
        Add a new job to the store.
        
        Triggers cleanup of expired jobs before adding.
        
        Args:
            job_id: Unique job identifier.
            status: Initial job status.
        """
        self.cleanup()
        
        self._jobs[job_id] = status
        self._created_at[job_id] = time.time()
        
        logger.info(f"Job added: {job_id} (status={status.status})")
    
    def get(self, job_id: str) -> Optional[JobStatus]:
        """
        Retrieve job status by ID.
        
        Args:
            job_id: Job identifier to look up.
        
        Returns:
            JobStatus if found, None otherwise.
        """
        return self._jobs.get(job_id)
    
    def update(self, job_id: str, status: JobStatus) -> bool:
        """
        Update an existing job's status.
        
        Args:
            job_id: Job identifier to update.
            status: New job status.
        
        Returns:
            True if job was found and updated, False otherwise.
        """
        if job_id not in self._jobs:
            logger.warning(f"Attempted to update non-existent job: {job_id}")
            return False
        
        self._jobs[job_id] = status
        logger.debug(f"Job updated: {job_id} (status={status.status}, progress={status.progress})")
        return True
    
    def remove(self, job_id: str) -> bool:
        """
        Remove a job from the store.
        
        Args:
            job_id: Job identifier to remove.
        
        Returns:
            True if job was found and removed, False otherwise.
        """
        if job_id not in self._jobs:
            return False
        
        del self._jobs[job_id]
        self._created_at.pop(job_id, None)
        
        logger.debug(f"Job removed: {job_id}")
        return True
    
    def cleanup(self) -> int:
        """
        Remove expired jobs from the store.
        
        Returns:
            Number of jobs removed.
        """
        now = time.time()
        cutoff = now - self._ttl
        
        expired = [
            job_id
            for job_id, created in self._created_at.items()
            if created < cutoff
        ]
        
        for job_id in expired:
            self._jobs.pop(job_id, None)
            self._created_at.pop(job_id, None)
            logger.info(f"Cleaned up expired job: {job_id}")
        
        if expired:
            logger.info(f"Cleanup completed: {len(expired)} jobs removed")
        
        return len(expired)
    
    def stats(self) -> Dict[str, int]:
        """
        Get job statistics by status.
        
        Triggers cleanup before computing stats.
        
        Returns:
            Dictionary mapping status to count.
        """
        self.cleanup()
        
        stats: Dict[str, int] = {
            "queued": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "total": 0,
        }
        
        for job in self._jobs.values():
            stats[job.status] = stats.get(job.status, 0) + 1
            stats["total"] += 1
        
        return stats
    
    def list_jobs(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[JobStatus]:
        """
        List jobs, optionally filtered by status.
        
        Args:
            status: Filter by status (queued, processing, completed, failed).
            limit: Maximum number of jobs to return.
        
        Returns:
            List of JobStatus objects.
        """
        self.cleanup()
        
        jobs = list(self._jobs.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        # Sort by created_at (newest first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        return jobs[:limit]
    
    def clear(self) -> int:
        """
        Clear all jobs from the store.
        
        Returns:
            Number of jobs cleared.
        """
        count = len(self._jobs)
        self._jobs.clear()
        self._created_at.clear()
        
        logger.info(f"Job store cleared: {count} jobs removed")
        return count