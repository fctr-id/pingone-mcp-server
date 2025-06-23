"""
Main PingOne API client that orchestrates authentication, requests, and response handling.
"""

import logging
from typing import Dict, List, Any, Optional, AsyncGenerator
from urllib.parse import urljoin
import httpx
from .config import ConfigManager, PingOneConfig
from .auth_manager import AuthManager
from .rate_limiter import RateLimiter
from .request_manager import RequestManager
from .pagination_handler import PaginationHandler
from .normalize_ping_responses import PingOneResponseHandler


logger = logging.getLogger("ping_mcp_server")

class PingOneClient:
    """Main client for interacting with PingOne APIs with multi-environment support."""
    
    def __init__(self, config: Optional[PingOneConfig] = None):
        """Initialize PingOne client with configuration."""
        
        # Load config from environment if not provided
        self.config = config or ConfigManager.load_config()
        ConfigManager.validate_config(self.config)
        
        # Get regional URLs
        self.api_base_url = ConfigManager.get_api_base_url(self.config.region)
        auth_base_url = ConfigManager.get_auth_base_url(self.config.region)
        
        # Initialize components that don't depend on environment
        self.rate_limiter = RateLimiter(
            max_requests_per_second=self.config.max_requests_per_second
        )
        
        self.pagination_handler = PaginationHandler(
            default_page_size=self.config.default_page_size,
            max_page_size=self.config.max_page_size
        )
        
        self.response_handler = PingOneResponseHandler()
        
        # Environment-specific components (created on-demand) - keyed by env_id
        self._auth_managers: Dict[str, AuthManager] = {}
        self._request_managers: Dict[str, RequestManager] = {}
        
        logger.info(f"PingOne client initialized for region {self.config.region} with {len(self.config.environments)} environments")
    
    def _get_auth_manager(self, env_id: str, client_id: str, client_secret: str) -> AuthManager:
        """Get or create auth manager for specific environment."""
        if env_id not in self._auth_managers:
            auth_base_url = ConfigManager.get_auth_base_url(self.config.region)
            self._auth_managers[env_id] = AuthManager(
                auth_base_url=auth_base_url,
                env_id=env_id,
                client_id=client_id,
                client_secret=client_secret
            )
        return self._auth_managers[env_id]
    
    def _get_request_manager(self, env_id: str, client_id: str, client_secret: str) -> RequestManager:
        """Get or create request manager for specific environment."""
        if env_id not in self._request_managers:
            auth_manager = self._get_auth_manager(env_id, client_id, client_secret)
            self._request_managers[env_id] = RequestManager(
                auth_manager=auth_manager,
                rate_limiter=self.rate_limiter,
                max_retries=self.config.max_retries,
                request_timeout=self.config.request_timeout
            )
        return self._request_managers[env_id]
    
    def _build_api_url(self, endpoint: str, env_id: str) -> str:
        """Build full API URL for an endpoint in specific environment."""
        base_path = f"/v1/environments/{env_id}"
        full_path = f"{base_path}/{endpoint.lstrip('/')}"
        return urljoin(self.api_base_url, full_path)
    
    def _resolve_environment(self, environment: str = "") -> tuple[str, str, str, str]:
        """Resolve environment name to (name, id, client_id, client_secret) using config manager."""
        env_name, env_config = ConfigManager.resolve_environment(self.config, environment)
        return env_name, env_config.id, env_config.client_id, env_config.client_secret
    
    async def get(self, 
                 endpoint: str,
                 query_params: Optional[Dict[str, str]] = None,
                 environment: str = "",
                 paginated: bool = True,
                 page_size: Optional[int] = None) -> Dict[str, Any]:
        """Generic GET request to PingOne API."""
        
        # Resolve environment - now returns 4 values!
        env_name, env_id, client_id, client_secret = self._resolve_environment(environment)
        request_manager = self._get_request_manager(env_id, client_id, client_secret)
        
        # Build URL
        url = self._build_api_url(endpoint, env_id)
        
        # Handle pagination and query params
        params = query_params or {}
        if paginated and page_size:
            params["limit"] = str(page_size)
        
        # Make request
        response = await request_manager.get(url, params=params if params else None)
        
        if not response.is_success:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        response_data = response.json()
        
        # Normalize response
        if paginated:
            result = self.response_handler.normalize_list_response(response_data)
        else:
            result = self.response_handler.normalize_single_response(response_data)
        
        # Add environment context
        result["environment"] = {"name": env_name, "id": env_id}
        
        return result
    
    async def post(self,
                  endpoint: str,
                  body: Optional[Dict[str, Any]] = None,
                  query_params: Optional[Dict[str, str]] = None,
                  environment: str = "") -> Dict[str, Any]:
        """Generic POST request to PingOne API."""
        
        # Resolve environment - now returns 4 values!
        env_name, env_id, client_id, client_secret = self._resolve_environment(environment)
        request_manager = self._get_request_manager(env_id, client_id, client_secret)
        
        # Build URL
        url = self._build_api_url(endpoint, env_id)
        
        # Add query params to URL if provided
        if query_params:
            param_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            url = f"{url}?{param_string}"
        
        # Make request
        response = await request_manager.post(url, json_data=body)
        
        if not response.is_success:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        response_data = response.json()
        result = self.response_handler.normalize_single_response(response_data)
        
        # Add environment context
        result["environment"] = {"name": env_name, "id": env_id}
        
        return result
    
    async def put(self,
                 endpoint: str,
                 body: Optional[Dict[str, Any]] = None,
                 query_params: Optional[Dict[str, str]] = None,
                 environment: str = "") -> Dict[str, Any]:
        """Generic PUT request to PingOne API."""
        
        # Resolve environment - now returns 4 values!
        env_name, env_id, client_id, client_secret = self._resolve_environment(environment)
        request_manager = self._get_request_manager(env_id, client_id, client_secret)
        
        # Build URL
        url = self._build_api_url(endpoint, env_id)
        
        # Add query params to URL if provided
        if query_params:
            param_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            url = f"{url}?{param_string}"
        
        # Make request
        response = await request_manager.put(url, json_data=body)
        
        if not response.is_success:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        response_data = response.json()
        result = self.response_handler.normalize_single_response(response_data)
        
        # Add environment context
        result["environment"] = {"name": env_name, "id": env_id}
        
        return result
    
    async def delete(self,
                    endpoint: str,
                    query_params: Optional[Dict[str, str]] = None,
                    environment: str = "") -> Dict[str, Any]:
        """Generic DELETE request to PingOne API."""
        
        # Resolve environment - now returns 4 values!
        env_name, env_id, client_id, client_secret = self._resolve_environment(environment)
        request_manager = self._get_request_manager(env_id, client_id, client_secret)
        
        # Build URL
        url = self._build_api_url(endpoint, env_id)
        
        # Add query params to URL if provided
        if query_params:
            param_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            url = f"{url}?{param_string}"
        
        # Make request
        response = await request_manager.delete(url)
        
        if not response.is_success:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        response_data = response.json()
        result = self.response_handler.normalize_single_response(response_data)
        
        # Add environment context
        result["environment"] = {"name": env_name, "id": env_id}
        
        return result
    
    async def health_check(self, environment: str = "") -> bool:
        """Check if the client can successfully authenticate and make requests to specified environment."""
        try:
            env_name, env_id, client_id, client_secret = self._resolve_environment(environment)
            result = await self.get("", environment=environment, paginated=False)
            return result["success"]
        except Exception as e:
            logger.error(f"Health check failed for environment '{environment}': {e}")
            return False
    
    def get_available_environments(self) -> List[Dict[str, Any]]:
        """Get list of available environments with details."""
        return ConfigManager.get_available_environments(self.config)
    
    async def get_organization_level(
        self,
        endpoint: str,
        query_params: Optional[Dict[str, Any]] = None,
        paginated: bool = False,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Make organization-level API calls (without environment prefix).
        
        Uses the default environment's credentials for organization-level calls.
        """
        try:
            # Use default environment's credentials for org-level calls
            env_name, env_id, client_id, client_secret = self._resolve_environment("")
            
            # Build URL without environment prefix
            url = urljoin(self.api_base_url, f"v1/{endpoint}")
            
            # Add query parameters
            if query_params:
                # Handle pagination
                if paginated and 'limit' not in query_params:
                    query_params['limit'] = page_size
            
            # Get auth manager for default environment
            auth_manager = self._get_auth_manager(env_id, client_id, client_secret)
            token = await auth_manager.get_valid_token()
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # Make request
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=query_params)
                response.raise_for_status()
                
                data = response.json()
                
                # Handle pagination
                if paginated and "_embedded" in data:
                    # Extract items from embedded structure
                    if "environments" in data["_embedded"]:
                        items = data["_embedded"]["environments"]
                    else:
                        # Generic extraction for other embedded resources
                        embedded_key = list(data["_embedded"].keys())[0]
                        items = data["_embedded"][embedded_key]
                else:
                    items = data
                
                return {
                    "success": True,
                    "items": items if paginated else data,
                    "raw_response": data
                }
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in organization-level call: {e}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "status_code": e.response.status_code
            }
        except Exception as e:
            logger.error(f"Unexpected error in organization-level call: {e}")
            return {
                "success": False,
                "error": str(e)
            }