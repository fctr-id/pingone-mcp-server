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
        filter_by: Annotated[str, Field(description="SCIM filter for groups. See docstring for syntax.")] = "",
        population_id: Annotated[str, Field(description="Filter by population UUID")] = "",
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List groups in the PingOne environment with SCIM filtering.
        
        Make sure you understand the user's intent and get the complete group name from user query and pass it completely to the API.
        
        SCIM Filter Syntax (filter_by parameter):
        • Operators: eq (equals), sw (starts with), ew (ends with), co (contains), and (logical AND)
        • Filterable fields: name, description, population.id
        • Examples: 'name eq "IT-Administrators"', 'name co "Sales"', 'population.id eq "uuid"'
        • Combined: 'name sw "Admin" and population.id eq "uuid"'
        
        Returns group IDs needed for other group operations.
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
                    "applied_filter": filter_by or f"population.id eq {population_id}" if population_id else "none"
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
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed information about a specific group.
        
        Make sure you understand the user's intent and get the complete group name from user query and pass it completely to the API.
        
        Requires group UUID (not name) - use list_pingone_groups first to find the correct UUID.
        Returns complete group details including population assignment and metadata.
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
            
            if ctx:
                await ctx.info(f"Retrieved group {group_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "group": group,
                "environment": env_info
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting group {group_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_group for {group_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def list_pingone_users_in_group(
        group_id: Annotated[str, Field(description="Group UUID from list_pingone_groups")],
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        additional_filter: Annotated[str, Field(description="Additional SCIM filter for users (e.g., 'name.family eq \"Smith\"')")] = "",
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all users who are members of a specific group.
        
        Make sure you understand the user's intent and get the complete group name from user query and pass it completely to the API.
        
        Uses PingOne API: GET /users?filter=memberOfGroups[id eq "group-uuid"]
        
        Additional filtering examples:
        • 'name.family eq "Smith"' - Users named Smith in the group
        • 'enabled eq false' - Disabled users in the group
        • 'email ew "@contractor.com"' - Contractors in the group
        
        Workflow: Use list_pingone_groups first to get group UUID, then use UUID here.
        Limited to 50 users by default for LLM context efficiency.
        """
        try:
            logger.info("SERVER: Executing list_pingone_users_in_group")
            if ctx:
                await ctx.info("Executing list_pingone_users_in_group")
                await ctx.report_progress(10, 100)
            
            group_id = group_id.strip()
            environment = environment.strip() if environment else ""
            additional_filter = additional_filter.strip() if additional_filter else ""
            
            if not is_valid_uuid(group_id):
                raise ToolError(f"Invalid UUID format: {group_id}. Use list_pingone_groups to find correct UUID.")
            
            # Build the group membership filter
            group_filter = f'memberOfGroups[id eq "{group_id}"]'
            
            # Combine with additional filter if provided
            if additional_filter:
                full_filter = f'{group_filter} and {additional_filter}'
            else:
                full_filter = group_filter
            
            query_params = {
                "filter": full_filter,
                "limit": limit
            }
            
            if ctx:
                await ctx.info(f"Using filter: {full_filter}")
                await ctx.report_progress(30, 100)
            
            result = await ping_client.get(
                endpoint="users",
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
            
            users = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields for group member display
            simplified_users = []
            for user in users:
                simplified_user = {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "name": user.get("name", {}),
                    "enabled": user.get("enabled"),
                    "lifecycle": user.get("lifecycle", {}),
                    "population": user.get("population", {})
                }
                simplified_users.append(simplified_user)
            
            if ctx:
                await ctx.info(f"Retrieved {len(users)} users in group {group_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "group_id": group_id,
                "users": simplified_users,
                "environment": env_info,
                "summary": {
                    "user_count": len(users),
                    "limit_applied": limit,
                    "filter_used": full_filter
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting users in group {group_id}: {str(e)}")
            logger.exception(f"Error in list_pingone_users_in_group for {group_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def list_pingone_users_in_multiple_groups(
        group_ids: Annotated[List[str], Field(description="List of group UUIDs to find users who are members of ALL groups")],
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Find users who are members of ALL specified groups (intersection).
        
        Make sure you understand the user's intent and get the complete group name from user query and pass it completely to the API.
        
        Uses PingOne API filter: memberOfGroups[id eq "group1"] and memberOfGroups[id eq "group2"]
        Finds users who belong to EVERY group in the list (logical AND operation).
        
        Use cases:
        • Users with multiple role assignments
        • Security audit for privileged access
        • Compliance checks for required group combinations
        
        Workflow: Use list_pingone_groups first to get UUIDs for each group name.
        Maximum 5 groups supported. Limited to 50 users for LLM context efficiency.
        """
        try:
            logger.info("SERVER: Executing list_pingone_users_in_multiple_groups")
            if ctx:
                await ctx.info("Executing list_pingone_users_in_multiple_groups")
                await ctx.report_progress(10, 100)
            
            if not group_ids or len(group_ids) < 2:
                raise ToolError("Must provide at least 2 group IDs to find intersection")
            
            if len(group_ids) > 5:
                raise ToolError("Maximum 5 groups supported to avoid overly complex filters")
            
            environment = environment.strip() if environment else ""
            
            # Validate all group IDs are UUIDs
            for group_id in group_ids:
                if not is_valid_uuid(group_id.strip()):
                    raise ToolError(f"Invalid UUID format: {group_id}. Use list_pingone_groups to get UUIDs.")
            
            # Build the intersection filter
            group_filters = [f'memberOfGroups[id eq "{group_id.strip()}"]' for group_id in group_ids]
            full_filter = ' and '.join(group_filters)
            
            query_params = {
                "filter": full_filter,
                "limit": limit
            }
            
            if ctx:
                await ctx.info(f"Using intersection filter: {full_filter}")
                await ctx.report_progress(30, 100)
            
            result = await ping_client.get(
                endpoint="users",
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
            
            users = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields
            simplified_users = []
            for user in users:
                simplified_user = {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "name": user.get("name", {}),
                    "enabled": user.get("enabled"),
                    "lifecycle": user.get("lifecycle", {}),
                    "population": user.get("population", {})
                }
                simplified_users.append(simplified_user)
            
            if ctx:
                await ctx.info(f"Found {len(users)} users in ALL {len(group_ids)} groups")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "group_ids": group_ids,
                "users": simplified_users,
                "environment": env_info,
                "summary": {
                    "user_count": len(users),
                    "group_count": len(group_ids),
                    "operation": "intersection (users in ALL groups)",
                    "filter_used": full_filter
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error finding users in multiple groups: {str(e)}")
            logger.exception("Error in list_pingone_users_in_multiple_groups")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_user_group_memberships(
        user_id: Annotated[str, Field(description="User UUID from list_pingone_users")],
        include_details: Annotated[Literal["names", "ids", "full"], Field(description="Level of group detail to include")] = "full",
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get all group memberships for a specific user.
        
        Make sure you understand the user's intent and get the complete group name from user query and pass it completely to the API.
        
        Uses correct PingOne API endpoints:
        • include_details="names": GET /users/{id}?include=memberOfGroupNames
        • include_details="ids": GET /users/{id}?include=memberOfGroupIDs  
        • include_details="full": GET /users/{id}/memberOfGroups?expand=group
        
        Detail levels:
        • "names" - Just group names (lightweight)
        • "ids" - Just group IDs (for further operations)
        • "full" - Complete group details with descriptions, member counts, etc.
        
        Returns complete group names - use these exact names for other group operations.
        """
        try:
            logger.info("SERVER: Executing get_pingone_user_group_memberships")
            if ctx:
                await ctx.info("Executing get_pingone_user_group_memberships")
                await ctx.report_progress(10, 100)
            
            user_id = user_id.strip()
            environment = environment.strip() if environment else ""
            
            if not is_valid_uuid(user_id):
                raise ToolError(f"Invalid UUID format: {user_id}. Use list_pingone_users to find correct UUID.")
            
            if ctx:
                await ctx.info(f"Getting group memberships for user {user_id} with detail level: {include_details}")
                await ctx.report_progress(30, 100)
            
            if include_details in ["names", "ids"]:
                # Use the user endpoint with include parameter
                include_param = "memberOfGroupNames" if include_details == "names" else "memberOfGroupIDs"
                
                result = await ping_client.get(
                    endpoint=f"users/{user_id}",
                    query_params={"include": include_param},
                    environment=environment,
                    paginated=False
                )
                
                if not result["success"]:
                    error_details = result.get('error', 'User not found')
                    if "404" in str(error_details):
                        raise ToolError(f"User {user_id} not found.")
                    else:
                        raise ToolError(f"API error: {error_details}")
                
                user_data = result["item"]
                group_data = user_data.get(include_param, [])
                
                response = {
                    "success": True,
                    "user_id": user_id,
                    "group_memberships": group_data,
                    "environment": result.get("environment", {}),
                    "summary": {
                        "membership_count": len(group_data) if group_data else 0,
                        "detail_level": include_details,
                        "data_type": "group names" if include_details == "names" else "group IDs"
                    }
                }
                
            else:  # include_details == "full"
                # Use the memberOfGroups endpoint with expand
                result = await ping_client.get(
                    endpoint=f"users/{user_id}/memberOfGroups",
                    query_params={"expand": "group", "limit": limit},
                    environment=environment,
                    paginated=True,
                    page_size=limit
                )
                
                if not result["success"]:
                    error_details = result.get('error', 'User group memberships not found')
                    if "404" in str(error_details):
                        raise ToolError(f"User {user_id} not found or has no group memberships.")
                    else:
                        raise ToolError(f"API error: {error_details}")
                
                memberships = result["items"]
                
                # Extract group details from membership objects
                group_details = []
                for membership in memberships:
                    group = membership.get("group", {})
                    group_detail = {
                        "membershipId": membership.get("id"),
                        "addedAt": membership.get("createdAt"),
                        "group": {
                            "id": group.get("id"),
                            "name": group.get("name"),
                            "description": group.get("description", ""),
                            "memberCount": group.get("memberCount", 0),
                            "population": group.get("population", {})
                        }
                    }
                    group_details.append(group_detail)
                
                response = {
                    "success": True,
                    "user_id": user_id,
                    "group_memberships": group_details,
                    "environment": result.get("environment", {}),
                    "summary": {
                        "membership_count": len(group_details),
                        "detail_level": include_details,
                        "data_type": "full group details with membership info"
                    }
                }
            
            if ctx:
                await ctx.info(f"Retrieved {response['summary']['membership_count']} group memberships")
                await ctx.report_progress(100, 100)
            
            return response
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting group memberships for user {user_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_user_group_memberships for {user_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    logger.info("Registered PingOne group management tools")