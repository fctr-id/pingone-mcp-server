"""
HTTP request manager with retry logic, error handling, and rate limiting integration.
"""

import asyncio
import httpx
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from .rate_limiter import RateLimiter
from .auth_manager import AuthManager

logger = logging.getLogger("ping_mcp_server")

class RequestManager:
    """Manages HTTP requests with retry logic and rate limiting."""
    
    def __init__(self, 
                 auth_manager: AuthManager,
                 rate_limiter: RateLimiter,
                 max_retries: int = 3,
                 request_timeout: int = 30):
        self.auth_manager = auth_manager
        self.rate_limiter = rate_limiter
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        
        # HTTP status codes that are retryable
        self.retryable_status_codes = {408, 429, 500, 502, 503, 504}
        
        # HTTP status codes that require auth refresh
        self.auth_error_codes = {401, 403}
    
    async def _calculate_retry_delay(self, attempt: int, retry_after: Optional[str] = None) -> float:
        """Calculate delay before retry attempt."""
        
        # If we have a Retry-After header, handle it first
        if retry_after:
            handled = await self.rate_limiter.handle_retry_after(retry_after)
            if handled:
                return 0  # Already waited in handle_retry_after
        
        # Exponential backoff with jitter (1s, 2s, 4s, 8s...)
        base_delay = 1.0
        max_delay = 30.0
        delay = min(base_delay * (2 ** attempt), max_delay)
        
        # Add jitter (±25% randomness)
        import random
        jitter = delay * 0.25 * (2 * random.random() - 1)
        final_delay = max(0.1, delay + jitter)
        
        logger.debug(f"Retry attempt {attempt + 1}: waiting {final_delay:.2f}s")
        return final_delay
    
    async def _should_retry(self, response: httpx.Response, attempt: int) -> bool:
        """Determine if request should be retried."""
        
        if attempt >= self.max_retries:
            return False
        
        status_code = response.status_code
        
        # Always retry retryable status codes
        if status_code in self.retryable_status_codes:
            return True
        
        # Retry auth errors once (after token refresh)
        if status_code in self.auth_error_codes and attempt == 0:
            return True
        
        return False
    
    async def _make_request(self, 
                           method: str,
                           url: str, 
                           headers: Optional[Dict[str, str]] = None,
                           params: Optional[Dict[str, Any]] = None,
                           json_data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make a single HTTP request."""
        
        # Apply rate limiting
        await self.rate_limiter.wait_if_needed()
        
        # Get auth headers
        auth_headers = await self.auth_manager.get_auth_header()
        
        # Merge headers
        request_headers = {
            "User-Agent": "PingOne-MCP-Server/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if headers:
            request_headers.update(headers)
        
        request_headers.update(auth_headers)
        
        # Make request
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            logger.debug(f"{method} {url}")
            
            response = await client.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                json=json_data
            )
            
            logger.debug(f"Response: {response.status_code}")
            return response
    
    async def request(self,
                     method: str,
                     url: str,
                     headers: Optional[Dict[str, str]] = None,
                     params: Optional[Dict[str, Any]] = None, 
                     json_data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Optional additional headers
            params: Optional query parameters
            json_data: Optional JSON body data
            
        Returns:
            HTTP response
            
        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        
        last_response = None
        
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._make_request(method, url, headers, params, json_data)
                
                # Success - return response
                if response.is_success:
                    return response
                
                # Check if we should retry
                if not await self._should_retry(response, attempt):
                    logger.warning(f"Request failed with {response.status_code}, no more retries")
                    return response
                
                # Handle auth errors by refreshing token
                if response.status_code in self.auth_error_codes:
                    logger.info("Auth error, refreshing token")
                    self.auth_manager.invalidate_token()
                
                # Calculate retry delay
                retry_after = response.headers.get("Retry-After")
                delay = await self._calculate_retry_delay(attempt, retry_after)
                
                if delay > 0:
                    await asyncio.sleep(delay)
                
                last_response = response
                
            except httpx.TimeoutException:
                logger.warning(f"Request timeout on attempt {attempt + 1}")
                if attempt >= self.max_retries:
                    raise
                
                delay = await self._calculate_retry_delay(attempt)
                await asyncio.sleep(delay)
                
            except httpx.NetworkError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt >= self.max_retries:
                    raise
                
                delay = await self._calculate_retry_delay(attempt)
                await asyncio.sleep(delay)
        
        # If we get here, all retries failed
        if last_response:
            return last_response
        else:
            raise httpx.RequestError("All retry attempts failed")
    
    async def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make GET request."""
        return await self.request("GET", url, params=params)
    
    async def post(self, url: str, json_data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make POST request."""
        return await self.request("POST", url, json_data=json_data)
    
    async def put(self, url: str, json_data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make PUT request.""" 
        return await self.request("PUT", url, json_data=json_data)
    
    async def delete(self, url: str) -> httpx.Response:
        """Make DELETE request."""
        return await self.request("DELETE", url)