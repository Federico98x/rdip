# RDIP v1.3.0 - Trending Topics Analyzer
"""
Service for analyzing trending topics in a subreddit.
Extracts top posts, analyzes common themes, and generates trending topics.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

import asyncpraw

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger
from rdip_backend.models import TrendingResponse, TrendingTopic

logger = get_logger(__name__)

PERIOD_MAP = {
    "day": "day",
    "week": "week", 
    "month": "month",
}


class TrendingAnalyzer:
    """Analyzes trending topics in a subreddit."""
    
    def __init__(self):
        self._settings = get_settings()
        self.reddit: asyncpraw.Reddit | None = None
    
    async def __aenter__(self) -> "TrendingAnalyzer":
        self.reddit = asyncpraw.Reddit(
            client_id=self._settings.reddit_client_id,
            client_secret=self._settings.reddit_client_secret,
            user_agent=self._settings.reddit_user_agent,
        )
        return self
    
    async def __aexit__(self, *args) -> bool:
        if self.reddit:
            await self.reddit.close()
        return False
    
    async def analyze_trending(
        self,
        subreddit: str,
        period: str = "week",
        limit: int = 10
    ) -> TrendingResponse:
        """
        Analyze trending topics in a subreddit.
        
        Args:
            subreddit: Subreddit name (without r/).
            period: Time period (day, week, month).
            limit: Number of top posts to analyze.
        
        Returns:
            TrendingResponse with analyzed topics.
        """
        if not self.reddit:
            raise RuntimeError("Reddit client not initialized")
        
        logger.info(f"Analyzing trending for r/{subreddit} ({period}, limit={limit})")
        
        sub = await self.reddit.subreddit(subreddit)
        time_filter = PERIOD_MAP.get(period, "week")
        
        posts: List[Dict[str, Any]] = []
        async for submission in sub.top(time_filter=time_filter, limit=limit):
            posts.append({
                "id": submission.id,
                "title": submission.title,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "url": f"https://reddit.com{submission.permalink}",
                "created_utc": submission.created_utc,
                "selftext": (submission.selftext or "")[:500],
                "author": str(submission.author) if submission.author else "[deleted]",
                "upvote_ratio": getattr(submission, "upvote_ratio", 0.0),
                "link_flair_text": getattr(submission, "link_flair_text", None),
            })
        
        topics = self._extract_topics(posts)
        overall_sentiment = self._calculate_overall_sentiment(posts)
        
        return TrendingResponse(
            subreddit=subreddit,
            period=period,
            analyzed_posts=len(posts),
            topics=topics,
            overall_sentiment=overall_sentiment,
            generated_at=datetime.utcnow(),
        )
    
    def _extract_topics(self, posts: List[Dict[str, Any]]) -> List[TrendingTopic]:
        """Extract trending topics from posts."""
        import re
        
        all_words = []
        for post in posts:
            title = post.get("title", "")
            text = post.get("selftext", "")
            combined = f"{title} {text}".lower()
            
            combined = re.sub(r'[^\w\s]', ' ', combined)
            words = combined.split()
            
            stopwords = {
                'the', 'a', 'an', 'is', 'it', 'to', 'of', 'and', 'for', 'in', 'on',
                'with', 'as', 'at', 'by', 'from', 'or', 'be', 'was', 'are', 'been',
                'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                'should', 'may', 'might', 'must', 'just', 'that', 'this', 'these',
                'those', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
                'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
                'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
                'than', 'too', 'very', 'can', 'about', 'if', 'but', 'my', 'your',
                'i', 'me', 'you', 'he', 'she', 'they', 'we', 'them', 'us', 'his',
                'her', 'its', 'our', 'their', 'get', 'got', 'like', 'im', 'dont',
                'cant', 'wont', 'didnt', 'ive', 'youre', 'thats', 'one', 'two'
            }
            
            meaningful_words = [
                w for w in words 
                if len(w) > 3 and w not in stopwords and not w.isdigit()
            ]
            all_words.extend(meaningful_words)
        
        word_counts = Counter(all_words)
        top_words = word_counts.most_common(15)
        
        topics: List[TrendingTopic] = []
        
        topic_groups = self._group_related_words(top_words, posts)
        
        for topic_name, keywords in topic_groups[:5]:
            related_posts = self._find_related_posts(keywords, posts)
            sentiment = self._analyze_topic_sentiment(related_posts)
            
            topics.append(TrendingTopic(
                topic=topic_name.title(),
                mentions=sum(word_counts.get(kw, 0) for kw in keywords),
                sentiment=sentiment,
                top_posts=[
                    {"title": p["title"], "score": p["score"], "url": p["url"]}
                    for p in related_posts[:3]
                ],
                keywords=keywords[:5],
            ))
        
        return topics
    
    def _group_related_words(
        self, 
        top_words: List[tuple], 
        posts: List[Dict]
    ) -> List[tuple]:
        """Group related words into topics."""
        groups = []
        used_words = set()
        
        for word, count in top_words:
            if word in used_words:
                continue
            
            related = [word]
            used_words.add(word)
            
            for other_word, other_count in top_words:
                if other_word in used_words:
                    continue
                
                co_occurrence = 0
                for post in posts:
                    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
                    if word in text and other_word in text:
                        co_occurrence += 1
                
                if co_occurrence >= len(posts) * 0.3:
                    related.append(other_word)
                    used_words.add(other_word)
            
            groups.append((word, related))
        
        return sorted(groups, key=lambda x: len(x[1]), reverse=True)
    
    def _find_related_posts(
        self, 
        keywords: List[str], 
        posts: List[Dict]
    ) -> List[Dict]:
        """Find posts related to keywords."""
        scored_posts = []
        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored_posts.append((score, post))
        
        scored_posts.sort(key=lambda x: (x[0], x[1].get("score", 0)), reverse=True)
        return [p for _, p in scored_posts]
    
    def _analyze_topic_sentiment(self, posts: List[Dict]) -> str:
        """Analyze sentiment based on upvote ratios and engagement."""
        if not posts:
            return "neutral"
        
        avg_ratio = sum(p.get("upvote_ratio", 0.5) for p in posts) / len(posts)
        
        if avg_ratio >= 0.85:
            return "positive"
        elif avg_ratio >= 0.70:
            return "mixed"
        elif avg_ratio >= 0.50:
            return "neutral"
        else:
            return "negative"
    
    def _calculate_overall_sentiment(self, posts: List[Dict]) -> str:
        """Calculate overall subreddit sentiment."""
        if not posts:
            return "neutral"
        
        avg_ratio = sum(p.get("upvote_ratio", 0.5) for p in posts) / len(posts)
        total_engagement = sum(p.get("score", 0) + p.get("num_comments", 0) for p in posts)
        
        if avg_ratio >= 0.80 and total_engagement > len(posts) * 100:
            return "Highly engaged and positive"
        elif avg_ratio >= 0.70:
            return "Generally positive with active discussion"
        elif avg_ratio >= 0.50:
            return "Mixed reactions, diverse opinions"
        else:
            return "Controversial or divisive content"
