"""User management tools for PingOne MCP server."""

import logging
import re
from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..utils.ping_client import PingOneClient
from ..utils.normalize_ping_responses import PingOneResponseHandler

logger = logging.getLogger("ping_mcp_server")

def register_user_tools(server: FastMCP, ping_client: PingOneClient):
    """Register all user-related tools with the MCP server."""
    
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @server.tool()
    async def list_pingone_users(
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        population_id: Annotated[str, Field(description="Population UUID filter")] = "",
        filter_by: Annotated[str, Field(description="SCIM filter expression. See docstring for complete syntax.")] = "",
        detail_level: Annotated[Literal["basic", "detailed", "contact"], Field(description="Level of detail: basic=core fields, detailed=+dates/lifecycle/MFA, contact=+phone/address")] = "",
        environment: str = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Search PingOne users with SCIM filtering. Returns user IDs for get_pingone_user.
        
        IMPORTANT LIMITATIONS:
        PingOne SCIM does NOT support filtering by createdAt, updatedAt, lastSignOn, or most system timestamps.
        For date-based searches, retrieve users first then filter results programmatically.
        
        SCIM Filter Syntax (filter_by parameter):
        Operators: eq (equals), sw (starts with), ew (ends with), co (contains)
        
        Supported Filter Attributes:
        • username (eq, sw): 'username eq "john"', 'username sw "admin"'
        • email (eq, sw, ew): 'email eq "user@company.com"', 'email sw "admin@"', 'email ew "@company.com"'
        • enabled (eq, sw): 'enabled eq true' or 'enabled eq false'
        • name.given, name.family (eq, sw, ew, co): 'name.given sw "John"', 'name.family eq "Smith"'
        • name.formatted, name.middle, name.honorificPrefix, name.honorificSuffix (eq, sw)
        • population.id (eq, sw): 'population.id eq "uuid-here"'
        • mobilePhone, primaryPhone (eq, sw): 'mobilePhone sw "+1"', 'primaryPhone eq "+1234567890"'
        • nickname, title, type (eq, sw): 'type eq "Employee"', 'title sw "Manager"'
        • externalId, accountId (eq, sw): 'externalId eq "EMP123"'
        • locale, preferredLanguage, timezone (eq, sw): 'locale eq "en-US"'
        • address.streetAddress, address.locality, address.region (eq, sw): 'address.locality eq "Seattle"'
        • address.postalCode, address.countryCode (eq, sw): 'address.countryCode eq "US"'
        • startDate, endDate (eq, sw): 'startDate eq "2024-01-01"' - Employment or custom dates only
        • photo.href (eq, sw): 'photo.href sw "https://"'
        • Custom attributes of type STRING (eq, sw): Use your custom attribute names
        
        Combining Filters:
        Use 'and' to combine conditions: 'enabled eq true and type eq "Employee" and address.countryCode eq "US"'
        
        Common Queries:
        • Active employees: 'enabled eq true and type eq "Employee"'
        • US users: 'address.countryCode eq "US"'
        • Admins by email: 'email sw "admin@"'
        • Mobile users: 'mobilePhone sw "+1"'
        • Specific population: 'population.id eq "your-population-uuid"'
        • Recent hires: 'startDate eq "2024-06-01"' (only if using employment start dates)
        
        Detail Levels:
        • basic: id, username, email, enabled, name.given, name.family, lifecycle.status
        • detailed: basic + createdAt, updatedAt, account.status, population.id, mfaEnabled, verifyStatus
        • contact: id, username, email, phones, name, address
        
        For Date-Based User Searches:
        1. Use list_pingone_users(detail_level="detailed") to get users with timestamps
        2. Filter results programmatically by createdAt, updatedAt fields
        3. Use datetime tools (parse_relative_time, get_current_time) to get comparison timestamps
        
        Returns user list with pagination info. Use get_pingone_user() for full user details.
        """
        try:
            # Add server-side tool logging
            logger.info("SERVER: Executing list_pingone_users")
            if ctx:
                await ctx.info("Executing list_pingone_users")
                await ctx.report_progress(10, 100)
            
            query_params = {}
            filters = []
            if population_id and population_id.strip():
                filters.append(f'population.id eq "{population_id.strip()}"')
            if filter_by and filter_by.strip():
                filters.append(filter_by.strip())
            
            if filters:
                query_params["filter"] = " and ".join(filters)
            
            if ctx:
                await ctx.report_progress(30, 100)
            
            result = await ping_client.get(
                endpoint="users",
                query_params=query_params if query_params else None,
                environment=environment,
                paginated=True,
                page_size=limit
            )
            
            if ctx:
                await ctx.report_progress(70, 100)
            
            if not result["success"]:
                error_msg = f"PingOne API error: {result.get('error', 'Unknown error')}"
                if ctx:
                    await ctx.error(error_msg)
                raise ToolError(error_msg)
            
            users = result["items"]
            
            # Apply field filtering based on detail level
            include_fields = None
            if detail_level == "basic":
                include_fields = ["id", "username", "email", "enabled", "name.given", "name.family", "lifecycle.status"]
            elif detail_level == "detailed":
                include_fields = [
                    "id", "username", "email", "enabled", "createdAt", "updatedAt",
                    "name.given", "name.family", "name.formatted",
                    "lifecycle.status", "account.status", "account.canAuthenticate",
                    "population.id", "mfaEnabled", "verifyStatus"
                ]
            elif detail_level == "contact":
                include_fields = [
                    "id", "username", "email", "mobilePhone", "primaryPhone",
                    "name.given", "name.family", "address"
                ]
            
            if include_fields:
                response_handler = PingOneResponseHandler()
                users = [
                    response_handler.filter_response_fields(user, include_fields)
                    for user in users
                ]
            
            env_info = result.get("environment", {})
            
            if ctx:
                await ctx.info(f"Retrieved {len(users)} users")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "users": users,
                "environment": env_info,
                "summary": {
                    "returned_count": len(users),
                    "has_more": result["pagination"]["has_next"],
                    "detail_level": detail_level,
                    "filter_applied": query_params.get("filter", "none"),
                    "scim_limitation": "PingOne SCIM does not support filtering by createdAt/updatedAt timestamps"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing users: {str(e)}")
            logger.exception("Error in list_pingone_users")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_user(
        user_id: Annotated[str, Field(description="User UUID from list_pingone_users (format: 12345678-1234-1234-1234-123456789abc)")],
        detail_level: Annotated[Literal["basic", "detailed", "contact"], Field(description="basic=core fields, detailed=+lifecycle/MFA, contact=+phone/address")] = "",
        include_groups: Annotated[bool, Field(description="Include group memberships")] = False,
        expand_population: Annotated[bool, Field(description="Include population details")] = False,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed user information by UUID.
        
        Requires a valid user UUID, typically obtained from ***list_pingone_users*** searchtool results.
        Returns comprehensive user data including status fields, population membership, 
        and optionally group assignments.
        
        Use detail_level to control response size:
        - basic: Core identity fields only  
        - detailed: Adds status, dates, MFA, lifecycle info
        - contact: Adds phone numbers and address
        
        Set include_groups=true to get group memberships.
        Set expand_population=true to get full population details instead of just ID.
        """
        try:
            # Add server-side tool logging
            logger.info("Executing get_pingone_user")
            if ctx:
                await ctx.info("Executing get_pingone_user")
                await ctx.report_progress(15, 100)
            
            user_id = user_id.strip()
            environment = environment.strip() if environment else ""
            
            # Validate UUID format
            if not is_valid_uuid(user_id):
                raise ToolError(f"Invalid UUID format: {user_id}. Use list_pingone_users to find correct UUID.")
            
            query_params = {}
            
            # Build query parameters
            include_params = []
            if include_groups:
                include_params.extend(["memberOfGroupNames", "memberOfGroupIDs"])
            if include_params:
                query_params["include"] = ",".join(include_params)
            
            expand_params = []
            if expand_population:
                expand_params.append("populations")
            if expand_params:
                query_params["expand"] = ",".join(expand_params)
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"users/{user_id}",
                query_params=query_params if query_params else None,
                environment=environment,
                paginated=False
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'User not found')
                
                if "400" in str(error_details) or "INVALID_REQUEST" in str(error_details):
                    raise ToolError(f"Invalid user ID. Use list_pingone_users to find correct UUID.")
                elif "404" in str(error_details):
                    raise ToolError(f"User {user_id} not found.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for user {user_id}.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            user = result["item"]
            env_info = result.get("environment", {})
            
            # Apply field filtering
            include_fields = None
            if detail_level == "basic":
                include_fields = ["id", "username", "email", "enabled", "name.given", "name.family", "lifecycle.status"]
            elif detail_level == "detailed":
                include_fields = [
                    "id", "username", "email", "enabled", "createdAt", "updatedAt",
                    "name.given", "name.family", "name.formatted",
                    "lifecycle.status", "account.status", "account.canAuthenticate",
                    "population.id", "mfaEnabled", "verifyStatus"
                ]
            elif detail_level == "contact":
                include_fields = [
                    "id", "username", "email", "mobilePhone", "primaryPhone",
                    "name.given", "name.family", "address"
                ]
            
            if include_fields:
                response_handler = PingOneResponseHandler()
                # Preserve expanded data
                if include_groups:
                    include_fields.extend(["memberOfGroupNames", "memberOfGroupIDs"])
                if expand_population:
                    include_fields.extend(["_embedded.population", "population"])
                
                user = response_handler.filter_response_fields(user, include_fields)
            
            if ctx:
                await ctx.info(f"Retrieved user data for {user_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "user": user,
                "environment": env_info,
                "detail_level": detail_level,
                "included_data": {
                    "groups": include_groups,
                    "population_details": expand_population
                }
            }
        
        except ToolError:
            raise
        except Exception as e:
            if 'rate limit' in str(e).lower():
                raise ToolError('Rate limit exceeded. Wait and retry.')
            
            if ctx:
                await ctx.error(f"Error getting user {user_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_user for {user_id}")
            raise ToolError(f"Unexpected error: {str(e)}")

            
    @server.tool()
    async def get_pingone_user_sessions(
        user_id: Annotated[str, Field(description="User UUID to get sessions for (from list_pingone_users)")],
        include_details: Annotated[bool, Field(description="Include browser, OS, device, and location details")] = True,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get all active sessions for a specific user. ALso known as login events for user
        
        Requires a valid user UUID, typically obtained from ***list_pingone_users** search results.
        Returns session information including login times, IP addresses, browser details,
        operating system, device type, and geographic locations. Limited to last 10 sessions
        per user, returned in descending order by session date.
        
        Useful for security analysis, user activity monitoring, and session management.
        """
        try:
            # Add server-side tool logging
            logger.info("Executing get_pingone_user_sessions")
            if ctx:
                await ctx.info("Executing get_pingone_user_sessions")
                await ctx.report_progress(15, 100)
            
            user_id = user_id.strip()
            environment = environment.strip() if environment else ""
            
            # Validate UUID format
            if not is_valid_uuid(user_id):
                raise ToolError(f"Invalid UUID format: {user_id}. Use list_pingone_users to find correct UUID.")
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"users/{user_id}/sessions",
                query_params=None,
                environment=environment,
                paginated=False
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'Sessions not found')
                
                if "400" in str(error_details) or "INVALID_REQUEST" in str(error_details):
                    raise ToolError(f"Invalid user ID. Use list_pingone_users to find correct UUID.")
                elif "404" in str(error_details):
                    raise ToolError(f"User {user_id} not found or has no sessions.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for user {user_id} sessions.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            # Extract sessions from _embedded.sessions
            sessions_data = result.get("item", {})
            sessions = sessions_data.get("_embedded", {}).get("sessions", [])
            env_info = result.get("environment", {})
            
            # Apply field filtering based on include_details
            if not include_details:
                # Basic session info only
                simplified_sessions = []
                for session in sessions:
                    simplified_session = {
                        "id": session.get("id"),
                        "createdAt": session.get("createdAt"),
                        "activeAt": session.get("activeAt"),
                        "lastSignOn": {
                            "at": session.get("lastSignOn", {}).get("at"),
                            "remoteIp": session.get("lastSignOn", {}).get("remoteIp")
                        }
                    }
                    simplified_sessions.append(simplified_session)
                sessions = simplified_sessions
            
            session_count = len(sessions)
            
            if ctx:
                await ctx.info(f"Retrieved {session_count} sessions for user {user_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "user_id": user_id,
                "sessions": sessions,
                "environment": env_info,
                "summary": {
                    "session_count": session_count,
                    "max_sessions_per_user": 10,
                    "details_included": include_details,
                    "note": "Sessions ordered by date (newest first). Max 10 sessions per user."
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if 'rate limit' in str(e).lower():
                raise ToolError('Rate limit exceeded. Wait and retry.')
            
            if ctx:
                await ctx.error(f"Error getting sessions for user {user_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_user_sessions for {user_id}")
            raise ToolError(f"Unexpected error: {str(e)}")              
    
    logger.info("Registered PingOne user management tools")