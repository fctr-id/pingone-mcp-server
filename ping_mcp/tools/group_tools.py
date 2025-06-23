"""Group management tools for PingOne MCP server."""

import logging
import re
from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..utils.ping_client import PingOneClient
from ..utils.normalize_ping_responses import PingOneResponseHandler

logger = logging.getLogger("ping_mcp_server")

def register_group_tools(server: FastMCP, ping_client: PingOneClient):
    """Register all group-related tools with the MCP server."""
    
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @server.tool()
    async def list_pingone_groups(
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        filter_by: Annotated[str, Field(description="""SCIM filter for groups using operators: eq (equals), sw (starts with), ew (ends with), co (contains).
        
        Filterable Attributes:
        • name (eq, sw, ew, co): 'name eq "Administrators"' or 'name sw "Sales"'
        • description (eq, sw, ew, co): 'description co "team"'
        • population.id (eq): 'population.id eq "uuid-here"'
        
        Examples:
        - 'name sw "Admin"' (groups starting with Admin)
        - 'name co "Sales"' (groups containing Sales)
        - 'population.id eq "uuid" and name sw "Dev"' (Dev groups in specific population)
        """)] = "",
        population_id: Annotated[str, Field(description="Filter by population UUID")] = "",
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List groups in the PingOne environment with SCIM filtering.
        
        Returns group information including names, descriptions, member counts, and population assignments.
        Groups are used for role-based access control and application assignments.
        """
        try:
            logger.info("SERVER: Executing list_pingone_groups")
            if ctx:
                await ctx.info("Executing list_pingone_groups")
                await ctx.report_progress(10, 100)
            
            environment = environment.strip() if environment else ""
            filter_by = filter_by.strip() if filter_by else ""
            population_id = population_id.strip() if population_id else ""
            
            # Build query parameters
            query_params = {"limit": limit}
            
            # Add SCIM filter
            if filter_by:
                query_params["filter"] = filter_by
            elif population_id:
                if is_valid_uuid(population_id):
                    query_params["filter"] = f'population.id eq "{population_id}"'
                else:
                    raise ToolError(f"Invalid population UUID format: {population_id}")
            
            if ctx:
                await ctx.report_progress(30, 100)
            
            result = await ping_client.get(
                endpoint="groups",
                query_params=query_params,
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
            
            groups = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields for easy identification
            simplified_groups = []
            for group in groups:
                simplified_group = {
                    "id": group.get("id"),
                    "name": group.get("name"),
                    "description": group.get("description", ""),
                    "memberCount": group.get("memberCount", 0),
                    "population": {
                        "id": group.get("population", {}).get("id")
                    } if group.get("population") else None,
                    "createdAt": group.get("createdAt"),
                    "updatedAt": group.get("updatedAt")
                }
                # Remove None values
                simplified_group = {k: v for k, v in simplified_group.items() if v is not None}
                simplified_groups.append(simplified_group)
            
            if ctx:
                await ctx.info(f"Retrieved {len(groups)} groups")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "groups": simplified_groups,
                "environment": env_info,
                "summary": {
                    "total_count": len(groups),
                    "applied_filter": filter_by or f"population.id eq {population_id}" if population_id else "none",
                    "usage_note": "Use group IDs for get_pingone_group or user group operations"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing groups: {str(e)}")
            logger.exception("Error in list_pingone_groups")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_group(
        group_id: Annotated[str, Field(description="Group UUID from list_pingone_groups")],
        include_members: Annotated[bool, Field(description="Include group member details")] = False,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed information about a specific group.
        
        Requires group UUID from list_pingone_groups. Returns comprehensive group 
        information including member details if requested.
        """
        try:
            logger.info("SERVER: Executing get_pingone_group")
            if ctx:
                await ctx.info("Executing get_pingone_group")
                await ctx.report_progress(15, 100)
            
            group_id = group_id.strip()
            environment = environment.strip() if environment else ""
            
            if not is_valid_uuid(group_id):
                raise ToolError(f"Invalid UUID format: {group_id}. Use list_pingone_groups to find correct UUID.")
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            # Get group details
            result = await ping_client.get(
                endpoint=f"groups/{group_id}",
                query_params=None,
                environment=environment,
                paginated=False
            )
            
            if not result["success"]:
                error_details = result.get('error', 'Group not found')
                
                if "404" in str(error_details):
                    raise ToolError(f"Group {group_id} not found.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for group {group_id}.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            group = result["item"]
            env_info = result.get("environment", {})
            
            response_data = {
                "success": True,
                "group": group,
                "environment": env_info
            }
            
            # Get group members if requested
            if include_members:
                if ctx:
                    await ctx.report_progress(60, 100)
                
                members_result = await ping_client.get(
                    endpoint=f"groups/{group_id}/membershipUsers",
                    query_params={"limit": 200},
                    environment=environment,
                    paginated=True,
                    page_size=200
                )
                
                if members_result["success"]:
                    response_data["members"] = members_result["items"]
                    response_data["member_count"] = len(members_result["items"])
                else:
                    response_data["members"] = []
                    response_data["member_count"] = 0
                    if ctx:
                        await ctx.info("Could not retrieve group members")
            
            if ctx:
                await ctx.info(f"Retrieved group {group_id}")
                await ctx.report_progress(100, 100)
            
            return response_data
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting group {group_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_group for {group_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def list_pingone_group_members(
        group_id: Annotated[str, Field(description="Group UUID from list_pingone_groups")],
        limit: Annotated[int, Field(ge=1, le=200)] = 100,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all members of a specific group.
        
        Returns user information for all members of the specified group including
        basic user details and membership status.
        """
        try:
            logger.info("SERVER: Executing list_pingone_group_members")
            if ctx:
                await ctx.info("Executing list_pingone_group_members")
                await ctx.report_progress(15, 100)
            
            group_id = group_id.strip()
            environment = environment.strip() if environment else ""
            
            if not is_valid_uuid(group_id):
                raise ToolError(f"Invalid UUID format: {group_id}. Use list_pingone_groups to find correct UUID.")
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"groups/{group_id}/membershipUsers",
                query_params={"limit": limit},
                environment=environment,
                paginated=True,
                page_size=limit
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'Group members not found')
                
                if "404" in str(error_details):
                    raise ToolError(f"Group {group_id} not found.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for group {group_id} members.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            members = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key member fields
            simplified_members = []
            for member in members:
                user_data = member.get("user", {})
                simplified_member = {
                    "id": user_data.get("id"),
                    "username": user_data.get("username"),
                    "email": user_data.get("email"),
                    "name": user_data.get("name", {}),
                    "enabled": user_data.get("enabled"),
                    "membershipId": member.get("id"),
                    "addedAt": member.get("createdAt")
                }
                simplified_members.append(simplified_member)
            
            if ctx:
                await ctx.info(f"Retrieved {len(members)} group members")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "group_id": group_id,
                "members": simplified_members,
                "environment": env_info,
                "summary": {
                    "member_count": len(members),
                    "limit_applied": limit,
                    "usage_note": "Use user IDs for detailed user operations"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting group members for {group_id}: {str(e)}")
            logger.exception(f"Error in list_pingone_group_members for {group_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    logger.info("Registered PingOne group management tools")