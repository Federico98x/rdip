# RDIP v1.3.0 - Link Enrichment Service
"""
Service for enriching links with metadata (title, description, type).
Uses async HTTP requests to fetch metadata from URLs.
"""
from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from rdip_backend.core.logging import get_logger

logger = get_logger(__name__)

LINK_TYPE_PATTERNS = {
    "github": (r"github\.com", "GitHub Repository"),
    "youtube": (r"youtube\.com|youtu\.be", "Video"),
    "twitter": (r"twitter\.com|x\.com", "Social Media"),
    "reddit": (r"reddit\.com", "Reddit Thread"),
    "arxiv": (r"arxiv\.org", "Research Paper"),
    "medium": (r"medium\.com", "Article"),
    "stackoverflow": (r"stackoverflow\.com", "Q&A"),
    "wikipedia": (r"wikipedia\.org", "Encyclopedia"),
    "docs": (r"docs\.|documentation|readme", "Documentation"),
    "news": (r"bbc\.|cnn\.|nytimes|reuters|theguardian", "News"),
    "image": (r"\.(png|jpg|jpeg|gif|webp|svg)($|\?)", "Image"),
    "pdf": (r"\.pdf($|\?)", "PDF Document"),
}


class LinkEnricher:
    """Enriches URLs with metadata like title, description, and type."""
    
    def __init__(self, timeout: float = 5.0, max_concurrent: int = 5):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def enrich_links(
        self, 
        links: List[Dict[str, str]]
    ) -> List[Dict[str, any]]:
        """
        Enrich a list of links with metadata.
        
        Args:
            links: List of link dicts with 'url', 'type', 'context' keys.
        
        Returns:
            List of enriched link dictionaries.
        """
        tasks = [self._enrich_single(link) for link in links]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        enriched = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to enrich link: {links[i].get('url')}: {result}")
                enriched.append(self._create_basic_enrichment(links[i]))
            else:
                enriched.append(result)
        
        return sorted(enriched, key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    async def _enrich_single(self, link: Dict[str, str]) -> Dict[str, any]:
        """Enrich a single link with metadata."""
        async with self._semaphore:
            url = link.get("url", "")
            context = link.get("context", "")
            
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            
            link_type = self._detect_link_type(url)
            
            enriched = {
                "url": url,
                "domain": domain,
                "type": link_type,
                "context": context,
                "title": None,
                "description": None,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=32",
                "relevance_score": self._calculate_relevance(url, context, link_type),
            }
            
            if link_type not in ["Image", "PDF Document"]:
                try:
                    meta = await self._fetch_metadata(url)
                    enriched["title"] = meta.get("title")
                    enriched["description"] = meta.get("description")
                except Exception as e:
                    logger.debug(f"Metadata fetch failed for {url}: {e}")
            
            return enriched
    
    def _detect_link_type(self, url: str) -> str:
        """Detect the type of link based on URL patterns."""
        url_lower = url.lower()
        
        for type_name, (pattern, label) in LINK_TYPE_PATTERNS.items():
            if re.search(pattern, url_lower):
                return label
        
        return "Reference"
    
    def _calculate_relevance(self, url: str, context: str, link_type: str) -> float:
        """Calculate relevance score based on link characteristics."""
        score = 0.5
        
        high_value_types = ["GitHub Repository", "Documentation", "Research Paper", "Q&A"]
        if link_type in high_value_types:
            score += 0.2
        
        if link_type in ["Image", "Social Media"]:
            score -= 0.1
        
        important_keywords = ["source", "official", "documentation", "tutorial", "guide"]
        if any(kw in context.lower() for kw in important_keywords):
            score += 0.15
        
        return min(max(score, 0.0), 1.0)
    
    async def _fetch_metadata(self, url: str) -> Dict[str, Optional[str]]:
        """Fetch title and description from URL."""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RDIP/1.3)"}
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return {}
            
            html = response.text[:10000]
            
            title = self._extract_tag(html, "title")
            og_title = self._extract_meta(html, "og:title")
            
            description = self._extract_meta(html, "description")
            og_desc = self._extract_meta(html, "og:description")
            
            return {
                "title": og_title or title,
                "description": og_desc or description,
            }
    
    @staticmethod
    def _extract_tag(html: str, tag: str) -> Optional[str]:
        """Extract content from an HTML tag."""
        match = re.search(f"<{tag}[^>]*>([^<]+)</{tag}>", html, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:200]
        return None
    
    @staticmethod
    def _extract_meta(html: str, name: str) -> Optional[str]:
        """Extract content from a meta tag."""
        patterns = [
            f'<meta[^>]*(?:name|property)=["\']?{name}["\']?[^>]*content=["\']?([^"\']+)["\']?',
            f'<meta[^>]*content=["\']?([^"\']+)["\']?[^>]*(?:name|property)=["\']?{name}["\']?',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:300]
        return None
    
    def _create_basic_enrichment(self, link: Dict[str, str]) -> Dict[str, any]:
        """Create basic enrichment when fetch fails."""
        url = link.get("url", "")
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        
        return {
            "url": url,
            "domain": domain,
            "type": self._detect_link_type(url),
            "context": link.get("context", ""),
            "title": None,
            "description": None,
            "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=32",
            "relevance_score": 0.3,
        }
