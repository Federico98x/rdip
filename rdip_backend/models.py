# RDIP v1.3.0 - Pydantic Models
"""
Data models for the Reddit Deep Intelligence Platform.
Defines input/output schemas, internal context objects, and job status structures.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class SubredditType(str, Enum):
    """Subreddit category for specialized prompts."""
    TECH = "tech"
    GAMING = "gaming"
    FINANCE = "finance"
    SCIENCE = "science"
    POLITICS = "politics"
    GENERAL = "general"


class AnalyzeRequest(BaseModel):
    """
    Input request for analyzing a Reddit thread.
    
    Attributes:
        url: The Reddit URL to analyze (must be valid reddit.com or redd.it URL).
        force_refresh: If True, bypass cache and re-analyze.
        deep_scan: If True, expand more comments (slower but more thorough).
        lite_mode: If True, limit content to avoid exceeding LLM token limits.
    """
    url: str
    force_refresh: bool = False
    deep_scan: bool = False
    lite_mode: bool = False
    
    @field_validator("url")
    @classmethod
    def validate_reddit_url(cls, v: str) -> str:
        """Validate that the URL is a valid Reddit URL."""
        v = v.strip().rstrip("/")
        if not v or ("reddit.com" not in v and "redd.it" not in v):
            raise ValueError("Must be a valid Reddit URL")
        return v


class TrendingRequest(BaseModel):
    """Request for trending topics analysis."""
    subreddit: str
    period: Literal["day", "week", "month"] = "week"
    limit: int = Field(default=10, ge=1, le=25)
    
    @field_validator("subreddit")
    @classmethod
    def validate_subreddit(cls, v: str) -> str:
        """Clean subreddit name."""
        v = v.strip().lower()
        if v.startswith("r/"):
            v = v[2:]
        if not v or len(v) > 50:
            raise ValueError("Invalid subreddit name")
        return v


class TrendingTopic(BaseModel):
    """A single trending topic from a subreddit."""
    topic: str
    mentions: int
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    top_posts: List[Dict[str, Any]]
    keywords: List[str]


class TrendingResponse(BaseModel):
    """Response for trending topics analysis."""
    subreddit: str
    period: str
    analyzed_posts: int
    topics: List[TrendingTopic]
    overall_sentiment: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class EnrichedLink(BaseModel):
    """Enriched link with metadata."""
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    type: str = "unknown"
    domain: str
    favicon: Optional[str] = None
    context: str
    relevance_score: float = Field(ge=0.0, le=1.0, default=0.5)


class ThreadContext(BaseModel):
    """
    Internal context object containing extracted Reddit thread data.
    
    Used to pass data from the Reddit miner to the AI orchestrator.
    """
    id: str
    url: str
    title: str
    selftext: str
    author: str
    score: int
    serialized_comments: str
    token_count_llama: int
    token_count_gemini: int
    metadata: Dict[str, Any]


class SentimentObj(BaseModel):
    """
    Sentiment analysis result for a piece of content.
    
    Attributes:
        label: Categorical sentiment label.
        score: Numeric confidence score (0.0-1.0).
        details: Brief explanation of the sentiment.
    """
    label: Literal["Positivo", "Negativo", "Neutro", "Mixto", "Controversial"]
    score: float = Field(ge=0.0, le=1.0)
    details: str


class AnalysisResult(BaseModel):
    """
    Complete analysis result returned by the platform.
    
    Contains metadata, raw text, summaries, sentiment analysis,
    and extracted information from the Reddit thread.
    """
    meta: Dict[str, Any]
    raw_post_text: str
    raw_comments_text: str
    summary_post: str
    summary_comments: str
    sentiment_post: SentimentObj
    sentiment_comments: SentimentObj
    consensus: str
    key_controversies: List[str]
    useful_links: List[Dict[str, Any]]


class JobStatus(BaseModel):
    """
    Status object for tracking asynchronous analysis jobs.
    
    Attributes:
        job_id: Unique identifier for the job.
        status: Current state of the job.
        progress: Completion percentage (0-100).
        result: Analysis result (populated when status is 'completed').
        error: Error message (populated when status is 'failed').
        created_at: Timestamp when the job was created.
    """
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = Field(ge=0, le=100, default=0)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)