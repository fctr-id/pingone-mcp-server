"""
Generic PingOne API response handling and normalization.
Focuses on response structure, pagination, and error handling rather than entity-specific normalization.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger("ping_mcp_server")

class PingOneResponseHandler:
    """Handles PingOne API response patterns and structures."""
    
    @staticmethod
    def extract_embedded_data(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract the actual data from PingOne's _embedded response structure.
        
        Args:
            response_data: Raw API response dictionary
            
        Returns:
            List of items from the embedded collection
        """
        if not isinstance(response_data, dict):
            return []
        
        embedded = response_data.get("_embedded", {})
        
        # Find the first list in _embedded (there's usually only one collection)
        for key, value in embedded.items():
            if isinstance(value, list):
                logger.debug(f"Found embedded collection '{key}' with {len(value)} items")
                return value
        
        # Fallback: if response is directly a list
        if isinstance(response_data, list):
            return response_data
            
        # Fallback: if no _embedded but has items key
        if "items" in response_data and isinstance(response_data["items"], list):
            return response_data["items"]
        
        logger.debug("No embedded data found in response")
        return []
    
    @staticmethod
    def extract_pagination_info(response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract pagination metadata from PingOne response.
        
        Args:
            response_data: Raw API response dictionary
            
        Returns:
            Dictionary with pagination info
        """
        links = response_data.get("_links", {})
        next_link = links.get("next", {})
        
        return {
            "count": response_data.get("count", 0),
            "size": response_data.get("size", 0), 
            "has_next": "href" in next_link if isinstance(next_link, dict) else False,
            "next_url": next_link.get("href") if isinstance(next_link, dict) else None,
            "self_url": links.get("self", {}).get("href"),
        }
    
    @staticmethod
    def extract_error_info(response_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract error information from PingOne error response.
        
        Args:
            response_data: Raw error response dictionary
            
        Returns:
            Dictionary with error info or None if no error
        """
        if not isinstance(response_data, dict):
            return None
            
        # PingOne error structure
        if "code" in response_data or "message" in response_data:
            return {
                "code": response_data.get("code"),
                "message": response_data.get("message"),
                "details": response_data.get("details", []),
                "correlation_id": response_data.get("correlationId")
            }
        
        return None
    
    @classmethod
    def normalize_list_response(cls, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a paginated list response from PingOne.
        
        Args:
            response_data: Raw API response
            
        Returns:
            Normalized response with items and metadata
        """
        items = cls.extract_embedded_data(response_data)
        pagination = cls.extract_pagination_info(response_data)
        error = cls.extract_error_info(response_data)
        
        result = {
            "items": items,
            "pagination": pagination,
            "success": error is None
        }
        
        if error:
            result["error"] = error
            
        return result
    
    @classmethod
    def normalize_single_response(cls, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a single item response from PingOne.
        
        Args:
            response_data: Raw API response
            
        Returns:
            Normalized response with item and metadata
        """
        error = cls.extract_error_info(response_data)
        
        result = {
            "item": response_data if error is None else None,
            "success": error is None
        }
        
        if error:
            result["error"] = error
            
        return result
    
    @staticmethod
    def filter_response_fields(item: Dict[str, Any], fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Filter response item to only include specified fields.
        Tools can use this to control what data they return.
        
        Args:
            item: Raw item dictionary
            fields: List of field names to include, None for all fields
            
        Returns:
            Filtered item dictionary
        """
        if not fields or not isinstance(item, dict):
            return item
            
        filtered = {}
        for field in fields:
            if "." in field:
                # Handle nested fields like "name.given"
                parts = field.split(".")
                current = item
                try:
                    for part in parts[:-1]:
                        current = current.get(part, {})
                    if parts[-1] in current:
                        # Create nested structure in filtered result
                        target = filtered
                        for part in parts[:-1]:
                            if part not in target:
                                target[part] = {}
                            target = target[part]
                        target[parts[-1]] = current[parts[-1]]
                except (TypeError, AttributeError):
                    continue
            else:
                # Handle top-level fields
                if field in item:
                    filtered[field] = item[field]
        
        return filtered
    
    @classmethod
    def build_success_response(cls, data: Any, message: str = "Success") -> Dict[str, Any]:
        """Build a standardized success response."""
        return {
            "success": True,
            "data": data,
            "message": message
        }
    
    @classmethod  
    def build_error_response(cls, error: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a standardized error response."""
        response = {
            "success": False,
            "error": error
        }
        
        if details:
            response["details"] = details
            
        return response