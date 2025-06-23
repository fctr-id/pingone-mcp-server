"""
Rate limiting with token bucket algorithm and Retry-After header handling.
"""

import asyncio
import time
from typing import Optional
from datetime import datetime, timezone
import re

class TokenBucket:
    """Token bucket rate limiter with Retry-After support."""
    
    def __init__(self, max_requests_per_second: int = 50):
        self.max_requests = max_requests_per_second
        self.tokens = float(max_requests_per_second)
        self.last_update = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token from the bucket, waiting if necessary."""
        async with self.lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.max_requests, self.tokens + elapsed * self.max_requests)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            # Wait for next token
            wait_time = (1 - self.tokens) / self.max_requests
            await asyncio.sleep(wait_time)
            self.tokens = 0

class RetryAfterHandler:
    """Handles Retry-After header parsing and validation."""
    
    MAX_RETRY_AFTER_SECONDS = 300  # 5 minutes max for security
    
    @classmethod
    def parse_retry_after(cls, retry_after_value: str) -> Optional[float]:
        """
        Parse Retry-After header value.
        Returns wait time in seconds, or None if invalid.
        """
        if not retry_after_value:
            return None
        
        retry_after_value = retry_after_value.strip()
        
        # Try parsing as seconds (integer)
        if retry_after_value.isdigit():
            seconds = int(retry_after_value)
            if seconds <= cls.MAX_RETRY_AFTER_SECONDS:
                return float(seconds)
            return None
        
        # Try parsing as HTTP date
        try:
            # Common HTTP date formats
            date_formats = [
                "%a, %d %b %Y %H:%M:%S GMT",
                "%A, %d-%b-%y %H:%M:%S GMT", 
                "%a %b %d %H:%M:%S %Y"
            ]
            
            for fmt in date_formats:
                try:
                    target_time = datetime.strptime(retry_after_value, fmt)
                    target_time = target_time.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    
                    wait_seconds = (target_time - now).total_seconds()
                    if 0 <= wait_seconds <= cls.MAX_RETRY_AFTER_SECONDS:
                        return wait_seconds
                    break
                except ValueError:
                    continue
                    
        except Exception:
            pass
        
        return None

class RateLimiter:
    """Main rate limiter with token bucket and retry-after handling."""
    
    def __init__(self, max_requests_per_second: int = 50):
        self.token_bucket = TokenBucket(max_requests_per_second)
        self.retry_after_handler = RetryAfterHandler()
    
    async def wait_if_needed(self) -> None:
        """Wait for rate limiting if needed."""
        await self.token_bucket.acquire()
    
    async def handle_retry_after(self, retry_after_value: str) -> bool:
        """
        Handle Retry-After header from API response.
        Returns True if wait was performed, False if header was invalid.
        """
        wait_seconds = self.retry_after_handler.parse_retry_after(retry_after_value)
        
        if wait_seconds is not None:
            await asyncio.sleep(wait_seconds)
            return True
        
        return False