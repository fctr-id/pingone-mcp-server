"""
OAuth2 authentication manager for PingOne API access.
"""

import base64
import time
from typing import Optional, Dict, Any
import httpx
from dataclasses import dataclass

@dataclass
class TokenInfo:
    """OAuth2 token information."""
    access_token: str
    token_type: str
    expires_at: float
    scope: Optional[str] = None

class AuthManager:
    """Manages OAuth2 authentication with PingOne."""
    
    def __init__(self, auth_base_url: str, env_id: str, client_id: str, client_secret: str):
        self.auth_base_url = auth_base_url
        self.env_id = env_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_info: Optional[TokenInfo] = None
        self.token_buffer_seconds = 60  # Refresh token 60 seconds before expiry
    
    def _create_basic_auth_header(self) -> str:
        """Create Basic auth header for client credentials."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    async def _request_token(self) -> TokenInfo:
        """Request a new access token using client credentials flow."""
        token_url = f"{self.auth_base_url}/{self.env_id}/as/token"
        
        headers = {
            "Authorization": self._create_basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, headers=headers, data=data)
            
            if response.status_code != 200:
                error_detail = ""
                try:
                    error_info = response.json()
                    error_detail = f": {error_info.get('error_description', error_info.get('error', ''))}"
                except:
                    error_detail = f": HTTP {response.status_code}"
                
                raise Exception(f"Token request failed{error_detail}")
            
            token_data = response.json()
            
            # Calculate expiry time
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
            expires_at = time.time() + expires_in
            
            return TokenInfo(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_at=expires_at,
                scope=token_data.get("scope")
            )
    
    def _is_token_expired(self) -> bool:
        """Check if current token is expired or about to expire."""
        if not self.token_info:
            return True
        
        return time.time() >= (self.token_info.expires_at - self.token_buffer_seconds)
    
    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._is_token_expired():
            self.token_info = await self._request_token()
        
        return self.token_info.access_token
    
    async def get_auth_header(self) -> Dict[str, str]:
        """Get Authorization header for API requests."""
        token = await self.get_access_token()
        return {"Authorization": f"Bearer {token}"}
    
    def invalidate_token(self) -> None:
        """Invalidate current token to force refresh on next request."""
        self.token_info = None