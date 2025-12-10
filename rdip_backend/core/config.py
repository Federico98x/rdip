# RDIP v1.3.0 - Configuration Management
"""
Centralized configuration management using Pydantic Settings.
Loads configuration from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables or .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Reddit API Credentials
    reddit_client_id: str = Field(default="", description="Reddit API client ID")
    reddit_client_secret: str = Field(default="", description="Reddit API client secret")
    reddit_user_agent: str = Field(
        default="web:rdip-v1.3.0:(by-rdip-user)",
        description="Reddit API user agent string"
    )
    
    # LLM API Keys
    groq_api_key: str = Field(default="", description="Groq API key for Llama models")
    google_api_key: str = Field(default="", description="Google API key for Gemini")
    
    # LLM Model Configuration
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model identifier"
    )
    gemini_model: str = Field(
        default="gemini-2.0-flash",
        description="Gemini model identifier"
    )
    llm_temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2200, ge=100, le=8000)
    
    # Rate Limiting
    groq_rpm_limit: int = Field(default=150, ge=1, description="Groq requests per minute limit")
    gemini_rpm_limit: int = Field(default=8, ge=1, description="Gemini requests per minute limit")
    groq_max_tokens: int = Field(default=120000, description="Max tokens for Groq context")
    
    # Server Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API server port")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    # Cache Configuration
    hot_cache_db: str = Field(default="data/cache_hot.rdb", description="Redislite database path")
    cold_cache_db: str = Field(default="data/cache_cold.duckdb", description="DuckDB database path")
    hot_cache_ttl: int = Field(default=86400, description="Hot cache TTL in seconds (24h default)")
    
    # Job Configuration
    job_ttl_seconds: int = Field(default=3600, description="Job TTL in seconds")
    
    # Deep Scan Settings
    deep_scan_more_limit: int = Field(default=120, description="MoreComments limit for deep scan")
    normal_scan_more_limit: int = Field(default=40, description="MoreComments limit for normal scan")
    
    @property
    def is_reddit_configured(self) -> bool:
        """Check if Reddit API credentials are configured."""
        return bool(self.reddit_client_id and self.reddit_client_secret)
    
    @property
    def is_groq_configured(self) -> bool:
        """Check if Groq API is configured."""
        return bool(self.groq_api_key)
    
    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini API is configured."""
        return bool(self.google_api_key)
    
    @property
    def has_llm_available(self) -> bool:
        """Check if at least one LLM is configured."""
        return self.is_groq_configured or self.is_gemini_configured


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses LRU cache to avoid re-reading environment variables on every call.
    """
    return Settings()