# RDIP v1.3.0 - FastAPI Main Application
"""
Main API application with endpoints for Reddit thread analysis.
Includes lifespan events, background task processing, and health checks.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger, setup_logging
from rdip_backend.models import (
    AnalysisResult, AnalyzeRequest, JobStatus, SentimentObj,
    TrendingRequest, TrendingResponse
)
from rdip_backend.services.ai_orchestrator import AIOrchestrator
from rdip_backend.services.cache_manager import DualCacheManager
from rdip_backend.services.job_store import JobStore
from rdip_backend.services.rate_limiter import RateLimitManager
from rdip_backend.services.reddit_miner import RedditMinerV2
from rdip_backend.services.trending_analyzer import TrendingAnalyzer
from rdip_backend.services.link_enricher import LinkEnricher

logger = get_logger(__name__)

job_store: JobStore
rate_limiter: RateLimitManager
cache_manager: DualCacheManager
ai_orchestrator: AIOrchestrator
link_enricher: LinkEnricher


@asynccontextmanager
async def lifespan(app: FastAPI):
    global job_store, rate_limiter, cache_manager, ai_orchestrator, link_enricher
    
    setup_logging()
    settings = get_settings()
    
    logger.info("RDIP v1.3.0 starting up...")
    logger.info(f"GROQ_API_KEY present: {settings.is_groq_configured}")
    logger.info(f"GOOGLE_API_KEY present: {settings.is_gemini_configured}")
    logger.info(f"REDDIT_CLIENT_ID present: {settings.is_reddit_configured}")
    
    job_store = JobStore()
    rate_limiter = RateLimitManager()
    cache_manager = DualCacheManager()
    ai_orchestrator = AIOrchestrator(rate_limiter)
    link_enricher = LinkEnricher()
    
    logger.info("All services initialized successfully")
    
    yield
    
    logger.info("RDIP shutting down...")
    job_store.cleanup()
    cache_manager.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Reddit Deep Intelligence Platform",
    description="Analyze Reddit threads with AI-powered insights",
    version="1.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDDIT_URL_PATTERNS = [
    r"https?://(?:www\.)?reddit\.com/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+",
    r"https?://redd\.it/[A-Za-z0-9]+",
    r"https?://old\.reddit\.com/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+",
    r"https?://(?:www\.)?reddit\.com/r/[A-Za-z0-9_]+/s/[A-Za-z0-9]+",
]


def validate_reddit_url(url: str) -> bool:
    return any(re.search(pattern, url) for pattern in REDDIT_URL_PATTERNS)


@app.post("/v1/analyze", response_model=JobStatus)
async def submit_analysis(request: AnalyzeRequest) -> JobStatus:
    """
    Submit a Reddit thread URL for analysis.
    
    If the URL is already cached and force_refresh is False, returns
    the cached result immediately. Otherwise, creates a background job
    and returns the job status for polling.
    """
    if not validate_reddit_url(request.url):
        raise HTTPException(
            status_code=400,
            detail="Invalid Reddit URL. Please provide a valid Reddit thread URL.",
        )
    
    if not request.force_refresh:
        cached = await cache_manager.get(request.url)
        if cached:
            logger.info(f"Cache hit for {request.url}")
            return JobStatus(
                job_id="cache",
                status="completed",
                progress=100,
                result=cached,
                created_at=datetime.utcnow(),
            )
    
    job_id = str(uuid.uuid4())
    job_status = JobStatus(
        job_id=job_id,
        status="queued",
        progress=0,
        created_at=datetime.utcnow(),
    )
    job_store.add(job_id, job_status)
    
    asyncio.create_task(
        process_analysis_pipeline(job_id, request.url, request.deep_scan, request.lite_mode)
    )
    
    logger.info(f"Job created: {job_id} for URL: {request.url} (lite_mode={request.lite_mode})")
    return job_status


@app.get("/v1/status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    """
    Get the current status of an analysis job.
    
    Use this endpoint to poll for job completion.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/v1/trending/{subreddit}")
async def get_trending_topics(
    subreddit: str,
    period: str = Query(default="week", pattern="^(day|week|month)$"),
    limit: int = Query(default=10, ge=1, le=25),
) -> TrendingResponse:
    """
    Get trending topics for a subreddit.
    
    Analyzes top posts from the specified time period and extracts
    common themes, keywords, and sentiment.
    """
    try:
        async with TrendingAnalyzer() as analyzer:
            result = await analyzer.analyze_trending(
                subreddit=subreddit,
                period=period,
                limit=limit
            )
        return result
    except Exception as e:
        logger.error(f"Trending analysis failed for r/{subreddit}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze trending topics: {str(e)[:200]}"
        )


@app.post("/v1/enrich-links")
async def enrich_links_endpoint(links: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Enrich a list of links with metadata.
    
    Takes links with url, type, and context fields and returns
    enriched data including title, description, favicon, and relevance score.
    """
    if not links:
        return []
    
    if len(links) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 links allowed per request")
    
    try:
        enriched = await link_enricher.enrich_links(links)
        return enriched
    except Exception as e:
        logger.error(f"Link enrichment failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enrich links: {str(e)[:200]}"
        )


@app.get("/v1/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring.
    
    Returns service status and configuration checks.
    """
    settings = get_settings()
    
    health: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.3.0",
        "services": {},
    }
    
    try:
        async with RedditMinerV2() as miner:
            pass
        health["services"]["reddit"] = "ok"
    except Exception as e:
        health["services"]["reddit"] = f"error: {str(e)[:100]}"
        health["status"] = "degraded"
    
    health["services"]["groq"] = (
        "configured" if settings.is_groq_configured else "missing_key"
    )
    health["services"]["gemini"] = (
        "configured" if settings.is_gemini_configured else "missing_key"
    )
    
    try:
        cache_stats = await cache_manager.get_stats()
        health["services"]["cache"] = "ok"
        health["cache_stats"] = cache_stats
    except Exception as e:
        health["services"]["cache"] = f"error: {str(e)[:100]}"
        health["status"] = "degraded"
    
    health["jobs_active"] = job_store.stats()
    
    try:
        rate_stats = await rate_limiter.get_stats()
        health["rate_limits"] = rate_stats
    except Exception:
        pass
    
    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/v1/stats")
async def get_stats() -> Dict[str, Any]:
    """
    Get system statistics.
    """
    return {
        "jobs": job_store.stats(),
        "cache": await cache_manager.get_stats(),
        "rate_limits": await rate_limiter.get_stats(),
    }


async def process_analysis_pipeline(
    job_id: str,
    url: str,
    deep_scan: bool,
    lite_mode: bool = False,
) -> None:
    """
    Background task that processes the full analysis pipeline.
    Now includes link enrichment step and lite_mode support.
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in store")
        return
    
    try:
        job.status = "processing"
        job.progress = 10
        job_store.update(job_id, job)
        
        logger.info(f"[{job_id}] Starting extraction for {url} (lite_mode={lite_mode})")
        async with RedditMinerV2() as miner:
            context = await miner.extract(url, deep_scan=deep_scan, lite_mode=lite_mode)
        
        job.progress = 35
        job_store.update(job_id, job)
        logger.info(f"[{job_id}] Extraction complete, starting LLM analysis")
        
        llm_raw = await ai_orchestrator.analyze(context)
        
        job.progress = 70
        job_store.update(job_id, job)
        logger.info(f"[{job_id}] LLM analysis complete, enriching links")
        
        raw_links = llm_raw.get("useful_links", [])
        enriched_links = []
        if raw_links:
            try:
                enriched_links = await link_enricher.enrich_links(raw_links)
            except Exception as e:
                logger.warning(f"[{job_id}] Link enrichment failed: {e}")
                enriched_links = raw_links
        
        job.progress = 85
        job_store.update(job_id, job)
        
        sentiment_post_data = llm_raw.get("sentiment_post", {})
        sentiment_comments_data = llm_raw.get("sentiment_comments", {})
        
        result = AnalysisResult(
            meta={
                "title": context.title,
                "author": context.author,
                "upvotes": context.score,
                "total_comments": context.metadata.get("total_comments", 0),
                "subreddit": context.metadata.get("subreddit"),
                "created_utc": context.metadata.get("created_utc"),
                "upvote_ratio": context.metadata.get("upvote_ratio"),
                "url": context.url,
                "is_self": context.metadata.get("is_self", True),
                "link_flair_text": context.metadata.get("link_flair_text"),
            },
            raw_post_text=context.selftext,
            raw_comments_text=context.serialized_comments,
            summary_post=llm_raw.get("summary_post", ""),
            summary_comments=llm_raw.get("summary_comments", ""),
            sentiment_post=SentimentObj(
                label=sentiment_post_data.get("label", "Neutro"),
                score=float(sentiment_post_data.get("score", 0.5)),
                details=sentiment_post_data.get("details", ""),
            ),
            sentiment_comments=SentimentObj(
                label=sentiment_comments_data.get("label", "Neutro"),
                score=float(sentiment_comments_data.get("score", 0.5)),
                details=sentiment_comments_data.get("details", ""),
            ),
            consensus=llm_raw.get("consensus", ""),
            key_controversies=llm_raw.get("key_controversies", []),
            useful_links=enriched_links,
        )
        
        job.progress = 95
        job_store.update(job_id, job)
        
        logger.info(f"[{job_id}] Saving to cache")
        await cache_manager.save(url, result.model_dump())
        
        job.result = result.model_dump()
        job.status = "completed"
        job.progress = 100
        job_store.update(job_id, job)
        
        logger.info(f"[{job_id}] Analysis completed successfully")
    
    except ValueError as e:
        logger.error(f"[{job_id}] Validation error: {e}")
        job.status = "failed"
        job.error = str(e)[:200]
        job_store.update(job_id, job)
    
    except RuntimeError as e:
        logger.error(f"[{job_id}] Runtime error: {e}")
        job.status = "failed"
        job.error = str(e)[:200]
        job_store.update(job_id, job)
    
    except Exception as e:
        logger.error(f"[{job_id}] Unexpected error: {e}", exc_info=True)
        job.status = "failed"
        job.error = f"Unexpected error: {str(e)[:180]}"
        job_store.update(job_id, job)


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "rdip_backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        workers=1,
    )