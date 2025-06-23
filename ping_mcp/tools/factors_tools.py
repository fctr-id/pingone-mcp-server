"""User MFA factor management tools for PingOne MCP server."""

import logging
import re
from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..utils.ping_client import PingOneClient
from ..utils.normalize_ping_responses import PingOneResponseHandler

logger = logging.getLogger("ping_mcp_server")

def register_user_factor_tools(server: FastMCP, ping_client: PingOneClient):
    """Register all user MFA factor-related tools with the MCP server."""
    
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @server.tool()
    async def list_pingone_user_mfa_devices(
        user_id: Annotated[str, Field(description="User UUID from list_pingone_users")],
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all MFA devices/factors registered for a specific user.
        
        Returns MFA device information including device types, status, and enrollment details.
        
        Common MFA Device Types:
        • SMS - Text message authentication
        • EMAIL - Email-based authentication  
        • TOTP - Time-based one-time passwords (Google Authenticator, Authy)
        • FIDO2 - WebAuthn/FIDO2 security keys
        • MOBILE - PingOne Mobile app
        • VOICE - Voice call authentication
        
        Device Status Values:
        • ACTIVE - Device is active and can be used
        • INACTIVE - Device is disabled
        • PENDING - Device enrollment pending
        • BLOCKED - Device is blocked
        
        Useful for MFA compliance analysis and user support.
        """
        try:
            logger.info("SERVER: Executing list_pingone_user_mfa_devices")
            if ctx:
                await ctx.info("Executing list_pingone_user_mfa_devices")
                await ctx.report_progress(15, 100)
            
            user_id = user_id.strip()
            environment = environment.strip() if environment else ""
            
            if not is_valid_uuid(user_id):
                raise ToolError(f"Invalid UUID format: {user_id}. Use list_pingone_users to find correct UUID.")
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"users/{user_id}/devices",
                query_params=None,
                environment=environment,
                paginated=True,
                page_size=50
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'MFA devices not found')
                
                if "400" in str(error_details) or "INVALID_REQUEST" in str(error_details):
                    raise ToolError(f"Invalid user ID. Use list_pingone_users to find correct UUID.")
                elif "404" in str(error_details):
                    raise ToolError(f"User {user_id} not found or has no MFA devices.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for user {user_id} MFA devices.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            devices = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields for easy analysis
            simplified_devices = []
            for device in devices:
                simplified_device = {
                    "id": device.get("id"),
                    "type": device.get("type"),
                    "status": device.get("status"),
                    "name": device.get("name"),
                    "nickname": device.get("nickname"),
                    "createdAt": device.get("createdAt"),
                    "updatedAt": device.get("updatedAt"),
                    "activatedAt": device.get("activatedAt"),
                    "phoneNumber": device.get("phoneNumber") if device.get("type") == "SMS" else None,
                    "email": device.get("email") if device.get("type") == "EMAIL" else None
                }
                # Remove None values
                simplified_device = {k: v for k, v in simplified_device.items() if v is not None}
                simplified_devices.append(simplified_device)
            
            device_count = len(devices)
            
            if ctx:
                await ctx.info(f"Retrieved {device_count} MFA devices for user {user_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "user_id": user_id,
                "mfa_devices": simplified_devices,
                "environment": env_info,
                "summary": {
                    "device_count": device_count,
                    "device_types": list(set(d.get("type") for d in devices if d.get("type"))),
                    "active_devices": len([d for d in devices if d.get("status") == "ACTIVE"]),
                    "compliance_note": "Check device_count > 0 for MFA compliance"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if 'rate limit' in str(e).lower():
                raise ToolError('Rate limit exceeded. Wait and retry.')
            
            if ctx:
                await ctx.error(f"Error getting MFA devices for user {user_id}: {str(e)}")
            logger.exception(f"Error in list_pingone_user_mfa_devices for {user_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_user_mfa_device(
        user_id: Annotated[str, Field(description="User UUID from list_pingone_users")],
        device_id: Annotated[str, Field(description="MFA device UUID from list_pingone_user_mfa_devices")],
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed information about a specific MFA device.
        
        Requires both user UUID and device UUID from list_pingone_user_mfa_devices.
        Returns comprehensive device information including activation details and configuration.
        """
        try:
            logger.info("SERVER: Executing get_pingone_user_mfa_device")
            if ctx:
                await ctx.info("Executing get_pingone_user_mfa_device")
                await ctx.report_progress(15, 100)
            
            user_id = user_id.strip()
            device_id = device_id.strip()
            environment = environment.strip() if environment else ""
            
            if not is_valid_uuid(user_id):
                raise ToolError(f"Invalid user UUID format: {user_id}")
            if not is_valid_uuid(device_id):
                raise ToolError(f"Invalid device UUID format: {device_id}")
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"users/{user_id}/devices/{device_id}",
                query_params=None,
                environment=environment,
                paginated=False
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'MFA device not found')
                
                if "404" in str(error_details):
                    raise ToolError(f"MFA device {device_id} not found for user {user_id}.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for MFA device {device_id}.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            device = result["item"]
            env_info = result.get("environment", {})
            
            if ctx:
                await ctx.info(f"Retrieved MFA device {device_id} for user {user_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "user_id": user_id,
                "device": device,
                "environment": env_info
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting MFA device {device_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_user_mfa_device")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    logger.info("Registered PingOne user MFA factor management tools")