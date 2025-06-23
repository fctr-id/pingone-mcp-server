"""
Handles PingOne API pagination using _links.next pattern.
"""

from typing import Dict, List, Any, Optional, AsyncGenerator
import httpx

class PaginationHandler:
    """Handles PingOne's HATEOAS pagination with _links.next."""
    
    def __init__(self, default_page_size: int = 100, max_page_size: int = 1000):
        self.default_page_size = default_page_size
        self.max_page_size = max_page_size
    
    def extract_embedded_data(self, response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract data from _embedded collections."""
        embedded = response_data.get("_embedded", {})
        
        # Find the first list in _embedded (there's usually only one)
        for key, value in embedded.items():
            if isinstance(value, list):
                return value
        
        # Fallback: if no _embedded, check for direct list
        if isinstance(response_data, list):
            return response_data
        
        return []
    
    def get_next_page_url(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Extract next page URL from _links.next."""
        links = response_data.get("_links", {})
        next_link = links.get("next")
        
        if next_link and isinstance(next_link, dict):
            return next_link.get("href")
        
        return None
    
    def get_pagination_info(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract pagination metadata."""
        return {
            "count": response_data.get("count", 0),
            "size": response_data.get("size", 0),
            "has_next": self.get_next_page_url(response_data) is not None
        }
    
    def build_paginated_url(self, base_url: str, page_size: Optional[int] = None, 
                           cursor: Optional[str] = None) -> str:
        """Build URL with pagination parameters."""
        page_size = page_size or self.default_page_size
        page_size = min(page_size, self.max_page_size)
        
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}limit={page_size}"
        
        if cursor:
            url += f"&cursor={cursor}"
        
        return url
    
    async def get_all_pages(self, 
                           http_client: httpx.AsyncClient,
                           initial_url: str,
                           headers: Dict[str, str],
                           max_pages: int = 100) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """
        Generator that yields data from all pages.
        
        Args:
            http_client: HTTP client for making requests
            initial_url: First page URL
            headers: HTTP headers including auth
            max_pages: Maximum pages to fetch (safety limit)
        
        Yields:
            List of items from each page
        """
        current_url = initial_url
        pages_fetched = 0
        
        while current_url and pages_fetched < max_pages:
            response = await http_client.get(current_url, headers=headers)
            response.raise_for_status()
            
            response_data = response.json()
            page_data = self.extract_embedded_data(response_data)
            
            if page_data:
                yield page_data
            
            # Get next page URL
            current_url = self.get_next_page_url(response_data)
            pages_fetched += 1
            
            # Break if no more pages
            if not current_url:
                break