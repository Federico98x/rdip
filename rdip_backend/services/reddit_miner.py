# RDIP v1.3.0 - Reddit Miner Service
"""
Asynchronous Reddit thread extraction using AsyncPRAW.
Implements context manager pattern for proper resource management.
"""
from __future__ import annotations

import re
from typing import List

import asyncpraw
import asyncpraw.exceptions
from tiktoken import get_encoding

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger
from rdip_backend.models import ThreadContext

logger = get_logger(__name__)

LITE_MODE_MAX_POST_CHARS = 2000
LITE_MODE_MAX_COMMENTS = 30
LITE_MODE_MAX_COMMENT_CHARS = 500
LITE_MODE_MAX_TOTAL_TOKENS = 4000


class RedditMinerV2:
    """
    Asynchronous Reddit thread extractor using AsyncPRAW.
    
    Designed to be used as an async context manager for proper
    resource cleanup.
    
    Example:
        async with RedditMinerV2() as miner:
            context = await miner.extract(url)
    """
    
    def __init__(self) -> None:
        """Initialize the miner without creating the Reddit client yet."""
        self.reddit: asyncpraw.Reddit | None = None
        self._settings = get_settings()
    
    async def __aenter__(self) -> "RedditMinerV2":
        """
        Async context manager entry point.
        
        Creates the AsyncPRAW Reddit client with configured credentials.
        """
        self.reddit = asyncpraw.Reddit(
            client_id=self._settings.reddit_client_id,
            client_secret=self._settings.reddit_client_secret,
            user_agent=self._settings.reddit_user_agent,
        )
        logger.debug("Reddit client initialized")
        return self
    
    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """
        Async context manager exit point.
        
        Ensures the Reddit client is properly closed.
        """
        if self.reddit:
            await self.reddit.close()
            logger.debug("Reddit client closed")
        return False
    
    async def extract(self, url: str, deep_scan: bool = False, lite_mode: bool = False) -> ThreadContext:
        """
        Extract and serialize a Reddit thread.
        
        Args:
            url: The Reddit URL to extract.
            deep_scan: If True, expand more MoreComments objects (slower but more thorough).
            lite_mode: If True, limit content to avoid exceeding LLM token limits.
        
        Returns:
            ThreadContext containing all extracted data.
        
        Raises:
            ValueError: If the URL is invalid or the post is not found.
            RuntimeError: If the Reddit client is not initialized.
        """
        if not self.reddit:
            raise RuntimeError("Reddit client not initialized. Use 'async with' context manager.")
        
        try:
            logger.info(f"Extracting Reddit thread: {url} (deep_scan={deep_scan}, lite_mode={lite_mode})")
            
            submission = await self.reddit.submission(url=url)
            await submission.load()
            
            submission.comment_sort = "top"
            
            if lite_mode:
                more_limit = 0
            else:
                more_limit = (
                    self._settings.deep_scan_more_limit
                    if deep_scan
                    else self._settings.normal_scan_more_limit
                )
            await submission.comments.replace_more(limit=more_limit)
            
            comments = submission.comments.list()
            
            if lite_mode:
                comments = sorted(
                    [c for c in comments if hasattr(c, "body") and hasattr(c, "score")],
                    key=lambda c: c.score,
                    reverse=True
                )[:LITE_MODE_MAX_COMMENTS]
            
            serialized_lines = self._serialize_comments(comments, lite_mode=lite_mode)
            serialized_comments = "\n".join(serialized_lines)
            
            selftext = submission.selftext or ""
            if lite_mode and len(selftext) > LITE_MODE_MAX_POST_CHARS:
                selftext = selftext[:LITE_MODE_MAX_POST_CHARS] + "... [truncated for lite mode]"
            
            all_text = selftext + "\n" + serialized_comments
            detected_urls = self._extract_urls(all_text)
            
            token_count_llama, token_count_gemini = self._count_tokens(all_text)
            
            if lite_mode and token_count_llama > LITE_MODE_MAX_TOTAL_TOKENS:
                serialized_lines = serialized_lines[:len(serialized_lines) // 2]
                serialized_comments = "\n".join(serialized_lines)
                all_text = selftext + "\n" + serialized_comments
                token_count_llama, token_count_gemini = self._count_tokens(all_text)
            
            context = ThreadContext(
                id=submission.id,
                url=url,
                title=submission.title or "",
                selftext=selftext,
                author=str(submission.author) if submission.author else "[deleted]",
                score=submission.score or 0,
                serialized_comments=serialized_comments,
                token_count_llama=token_count_llama,
                token_count_gemini=token_count_gemini,
                metadata={
                    "created_utc": submission.created_utc,
                    "total_comments": submission.num_comments,
                    "upvote_ratio": getattr(submission, "upvote_ratio", 0.0),
                    "subreddit": submission.subreddit.display_name,
                    "urls_detected": detected_urls,
                    "is_self": submission.is_self,
                    "link_flair_text": getattr(submission, "link_flair_text", None),
                    "lite_mode": lite_mode,
                },
            )
            
            logger.info(
                f"Extraction complete: {len(comments)} comments, "
                f"{token_count_llama} tokens (Llama), lite_mode={lite_mode}"
            )
            return context
        
        except asyncpraw.exceptions.InvalidURL as e:
            logger.error(f"Invalid Reddit URL: {url}")
            raise ValueError(f"Invalid Reddit URL format: {url}") from e
        
        except asyncpraw.exceptions.NotFound as e:
            logger.error(f"Reddit post not found: {url}")
            raise ValueError("Post not found (may be deleted or private)") from e
        
        except Exception as e:
            logger.error(f"Reddit extraction error: {e}", exc_info=True)
            raise
    
    def _serialize_comments(self, comments: list, lite_mode: bool = False) -> List[str]:
        """
        Serialize comments to indented text format.
        
        Args:
            comments: List of PRAW Comment objects.
            lite_mode: If True, truncate long comments.
        
        Returns:
            List of formatted comment strings.
        """
        lines: List[str] = []
        
        for comment in comments:
            if not hasattr(comment, "body"):
                continue
            
            if comment.body in ("[deleted]", "[removed]"):
                continue
            
            author = str(comment.author) if comment.author else "[deleted]"
            depth = getattr(comment, "depth", 0)
            score = getattr(comment, "score", 0)
            
            body = comment.body
            if lite_mode and len(body) > LITE_MODE_MAX_COMMENT_CHARS:
                body = body[:LITE_MODE_MAX_COMMENT_CHARS] + "..."
            
            indent = ">" * depth
            line = f"{indent} [score={score}] {author}: {body}"
            lines.append(line)
        
        return lines
    
    @staticmethod
    def _extract_urls(text: str) -> List[str]:
        """
        Extract unique URLs from text.
        
        Args:
            text: Text to search for URLs.
        
        Returns:
            List of unique URLs found.
        """
        url_pattern = r"https?://[^\s<>\"\'\]\)]+"
        urls = re.findall(url_pattern, text)
        # Clean trailing punctuation that might be captured
        cleaned_urls = [
            url.rstrip(".,;:!?)>]}'\"")
            for url in urls
        ]
        return list(set(cleaned_urls))
    
    @staticmethod
    def _count_tokens(text: str) -> tuple[int, int]:
        """
        Count tokens for both Llama and Gemini models.
        
        Args:
            text: Text to tokenize.
        
        Returns:
            Tuple of (llama_tokens, gemini_tokens).
        """
        # cl100k_base is used by GPT-4/Llama (good approximation)
        enc_llama = get_encoding("cl100k_base")
        llama_tokens = len(enc_llama.encode(text))
        
        # Try o200k_base for Gemini approximation, fallback to cl100k
        try:
            enc_gemini = get_encoding("o200k_base")
            gemini_tokens = len(enc_gemini.encode(text))
        except Exception:
            gemini_tokens = llama_tokens
        
        return llama_tokens, gemini_tokens