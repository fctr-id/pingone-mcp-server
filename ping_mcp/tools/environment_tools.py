"""Environment management tools for PingOne MCP server."""

import logging
import re
from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..utils.ping_client import PingOneClient
from ..utils.config import ConfigManager
from ..utils.normalize_ping_responses import PingOneResponseHandler

logger = logging.getLogger("ping_mcp_server")

def register_environment_tools(server: FastMCP, ping_client: PingOneClient):
    """Register all environment-related tools with the MCP server."""
    
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @server.tool()
    async def list_configured_environments(
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all configured environments available for use with this MCP server.
        ***YOU MUST CALL THIS TOOL FIRST TO SEE ENVIRONMENTS AVAILABLE FOR USE!***
        
        This shows the environments configured in your .env file or MCP client JSON,
        NOT the environments in your PingOne organization (use list_pingone_environments for that).
        
        Returns environment names, aliases, and which one is the default.
        Use this to see what environment names you can use in other tools.
        """
        try:
            logger.info("SERVER: Executing list_configured_environments")
            if ctx:
                await ctx.info("Listing configured environments from server configuration")
                await ctx.report_progress(25, 100)
            
            # Get configuration
            config = ConfigManager.load_config()
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            # Build environment list
            environments = []
            for env_name, env_config in config.environments.items():
                environments.append({
                    "name": env_name,
                    "environment_id": env_config.id,
                    "aliases": env_config.aliases,
                    "is_default": env_name == config.default_env,
                    "has_dedicated_credentials": True  # All environments now have dedicated credentials
                })
            
            if ctx:
                await ctx.info(f"Found {len(environments)} configured environments")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "configured_environments": environments,
                "summary": {
                    "total_environments": len(environments),
                    "default_environment": config.default_env,
                    "region": config.region,
                    "organization_id": config.org_id,
                    "usage_notes": [
                        "Use environment 'name' or any 'alias' in other tools",
                        "Leave environment parameter empty to use default",
                        "Names and aliases are case-insensitive",
                        "Use list_pingone_environments to see all org environments"
                    ]
                }
            }
            
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing configured environments: {str(e)}")
            logger.exception("Error in list_configured_environments")
            raise ToolError(f"Configuration error: {str(e)}")
    
    @server.tool()
    async def list_pingone_environments(
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
        filter_by: Annotated[str, Field(description="""SCIM filter for environments using operators: eq (equals), sw (starts with).
        
        Filterable Attributes (per PingOne API docs):
        • name (sw): 'name sw "Test"' - Environments starting with "Test"
        • id (eq): 'id eq "uuid"' - Specific environment by ID
        • organization.id (eq): 'organization.id eq "uuid"' - Environments in specific org
        • license.id (eq): 'license.id eq "uuid"' - Environments with specific license
        • status (eq): 'status eq "ACTIVE"' - Environment status
        
        Examples:
        - 'name sw "Test"' (environments starting with Test)
        - 'status eq "ACTIVE"' (active environments only)
        - 'license.id eq "57f0efac-37d9-4a17-8a35-196bb3362983"'
        
        Note: limit is ignored when used with filters other than organization.id or license.id
        """)] = "",
        expand_bill_of_materials: Annotated[bool, Field(description="Include bill of materials (licensed products)")] = False,
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List ALL environments in the PingOne organization (organization-level call).
        
        This shows all environments in your PingOne organization that you have access to,
        NOT just the ones configured for this MCP server (use list_configured_environments for that).
        
        This is useful for discovering new environments or getting UUIDs for configuration.
        Returns detailed environment information including types, regions, licenses, and bill of materials.
        """
        try:
            logger.info("SERVER: Executing list_pingone_environments")
            if ctx:
                await ctx.info("Executing list_pingone_environments - Organization level call")
                await ctx.report_progress(10, 100)
            
            filter_by = filter_by.strip() if filter_by else ""
            
            # Build query parameters
            query_params = {"limit": limit}
            
            if filter_by:
                query_params["filter"] = filter_by
            
            if expand_bill_of_materials:
                query_params["expand"] = "billOfMaterials"
            
            if ctx:
                await ctx.report_progress(30, 100)
            
            # Use organization-level call
            result = await ping_client.get_organization_level(
                endpoint="environments",
                query_params=query_params,
                paginated=True,
                page_size=limit
            )
            
            if ctx:
                await ctx.report_progress(70, 100)
            
            if not result["success"]:
                error_msg = f"PingOne API error: {result.get('error', 'Unknown error')}"
                if "403" in str(error_msg):
                    error_msg += " - Check that your application has organization-level permissions to list environments"
                if ctx:
                    await ctx.error(error_msg)
                raise ToolError(error_msg)
            
            environments = result["items"]
            
            # Get configured environments for comparison
            try:
                config = ConfigManager.load_config()
                configured_env_ids = {env.id for env in config.environments.values()}
            except Exception:
                configured_env_ids = set()
            
            # Extract key fields based on actual API response structure
            simplified_environments = []
            for env in environments:
                organization = env.get("organization", {})
                license_info = env.get("license", {})
                bill_of_materials = env.get("_embedded", {}).get("billOfMaterials", {})
                
                simplified_env = {
                    "id": env.get("id"),
                    "name": env.get("name"),
                    "description": env.get("description", ""),
                    "type": env.get("type"),
                    "region": env.get("region"),
                    "organization": {
                        "id": organization.get("id")
                    } if organization else None,
                    "license": {
                        "id": license_info.get("id")
                    } if license_info else None,
                    "createdAt": env.get("createdAt"),
                    "updatedAt": env.get("updatedAt"),
                    "configured_in_mcp": env.get("id") in configured_env_ids
                }
                
                # Add bill of materials if expanded
                if expand_bill_of_materials and bill_of_materials:
                    products = bill_of_materials.get("products", [])
                    simplified_env["billOfMaterials"] = {
                        "products": [
                            {
                                "type": p.get("type"),
                                "description": p.get("description")
                            } for p in products
                        ],
                        "createdAt": bill_of_materials.get("createdAt"),
                        "updatedAt": bill_of_materials.get("updatedAt")
                    }
                
                # Remove None values
                simplified_env = {k: v for k, v in simplified_env.items() if v is not None}
                simplified_environments.append(simplified_env)
            
            # Generate summary
            types_found = list(set(e.get("type") for e in environments if e.get("type")))
            regions_found = list(set(e.get("region") for e in environments if e.get("region")))
            configured_count = sum(1 for e in simplified_environments if e.get("configured_in_mcp"))
            
            if ctx:
                await ctx.info(f"Retrieved {len(environments)} environments ({configured_count} configured in MCP)")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "environments": simplified_environments,
                "summary": {
                    "total_count": len(environments),
                    "configured_in_mcp_count": configured_count,
                    "applied_filter": filter_by or "none",
                    "types_found": types_found,
                    "regions_found": regions_found,
                    "bill_of_materials_included": expand_bill_of_materials,
                    "usage_notes": [
                        "Use environment 'name' field for MCP server tools",
                        "Environments with 'configured_in_mcp': true are available for use",
                        "Use list_configured_environments to see MCP server configuration"
                    ]
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing environments: {str(e)}")
            logger.exception("Error in list_pingone_environments")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_environment(
        environment: Annotated[str, Field(description="Environment name (like 'Production') from list_configured_environments or leave empty for default")] = "",
        include_license: Annotated[bool, Field(description="Include detailed license information")] = True,
        include_bill_of_materials: Annotated[bool, Field(description="Include bill of materials (feature breakdown)")] = False,
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed information about a specific configured environment.
        
        Requires environment name (not UUID) from list_configured_environments.
        Returns comprehensive environment configuration including license details and features.
        """
        try:
            logger.info("SERVER: Executing get_pingone_environment")
            if ctx:
                await ctx.info("Executing get_pingone_environment")
                await ctx.report_progress(15, 100)
            
            environment = environment.strip() if environment else ""
            
            # Build include parameters
            include_params = []
            if include_license:
                include_params.append("license")
            if include_bill_of_materials:
                include_params.append("billOfMaterials")
            
            query_params = {}
            if include_params:
                query_params["include"] = ",".join(include_params)
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            # Get current environment info
            env_result = await ping_client.get(
                endpoint="environment",
                query_params=query_params if query_params else None,
                environment=environment,
                paginated=False
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not env_result["success"]:
                error_details = env_result.get('error', 'Environment not found')
                
                if "404" in str(error_details):
                    raise ToolError(f"Environment '{environment}' not found.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for environment '{environment}'.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            environment_data = env_result["item"]
            env_info = env_result.get("environment", {})
            
            if ctx:
                await ctx.info(f"Retrieved environment {environment}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "environment": environment_data,
                "environment_info": env_info,
                "included_data": {
                    "license": include_license,
                    "bill_of_materials": include_bill_of_materials
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting environment {environment}: {str(e)}")
            logger.exception(f"Error in get_pingone_environment for {environment}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def list_pingone_environment_resources(
        resource_type: Annotated[Literal["applications", "resources"], Field(description="Type of resources to list")] = "resources",
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        filter_by: Annotated[str, Field(description="""SCIM filter for resources using operators: eq (equals), sw (starts with), ew (ends with), co (contains).
        
        Filterable Attributes for Resources:
        • name (eq, sw, ew, co): 'name eq "PingOne API"' or 'name sw "Custom"'
        • type (eq): "OPENID_CONNECT" | "PING_ONE_API" | "CUSTOM" → 'type eq "CUSTOM"'
        • audience (eq, sw, ew, co): 'audience sw "https://api"'
        • description (eq, sw, ew, co): 'description co "custom"'
        
        Resource Types:
        • OPENID_CONNECT - Built-in OpenID Connect resource
        • PING_ONE_API - Built-in PingOne API resource  
        • CUSTOM - Custom API resources
        
        Examples:
        - 'type eq "CUSTOM"' (custom resources only)
        - 'name sw "Custom"' (resources starting with Custom)
        - 'audience sw "https://api"' (API resources with https audience)
        """)] = "",
        environment: Annotated[str, Field(description="Environment name (like 'Production') or leave empty for default")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List resources within a specific configured environment.
        
        Resource Types:
        • applications - OAuth/OIDC applications and SAML connections
        • resources - API resources including PingOne API, OpenID Connect, and custom resources
        
        Resources define protected endpoints and scopes for applications.
        Custom resources model external APIs that use PingOne for protection.
        """
        try:
            logger.info("SERVER: Executing list_pingone_environment_resources")
            if ctx:
                await ctx.info("Executing list_pingone_environment_resources")
                await ctx.report_progress(15, 100)
            
            environment = environment.strip() if environment else ""
            filter_by = filter_by.strip() if filter_by else ""
            
            query_params = {"limit": limit}
            if filter_by:
                query_params["filter"] = filter_by
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=resource_type,
                query_params=query_params,
                environment=environment,
                paginated=True,
                page_size=limit
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'Resources not found')
                
                if "404" in str(error_details):
                    raise ToolError(f"Environment '{environment}' not found or no {resource_type} exist.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for {resource_type} in environment '{environment}'. Check API scopes: p1:read:applications or p1:read:resources")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            resources = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields based on resource type
            simplified_resources = []
            for resource in resources:
                if resource_type == "applications":
                    simplified_resource = {
                        "id": resource.get("id"),
                        "name": resource.get("name"),
                        "description": resource.get("description", ""),
                        "type": resource.get("type"),
                        "protocol": resource.get("protocol"),
                        "enabled": resource.get("enabled"),
                        "createdAt": resource.get("createdAt")
                    }
                elif resource_type == "resources":
                    # Updated based on actual API response structure
                    app_permissions = resource.get("applicationPermissionsSettings", {})
                    simplified_resource = {
                        "id": resource.get("id"),
                        "name": resource.get("name"),
                        "description": resource.get("description", ""),
                        "type": resource.get("type"),
                        "audience": resource.get("audience"),
                        "accessTokenValiditySeconds": resource.get("accessTokenValiditySeconds"),
                        "introspectEndpointAuthMethod": resource.get("introspectEndpointAuthMethod"),
                        "applicationPermissionsEnabled": app_permissions.get("claimEnabled", False),
                        "createdAt": resource.get("createdAt"),
                        "updatedAt": resource.get("updatedAt")
                    }
                
                # Remove None values
                simplified_resource = {k: v for k, v in simplified_resource.items() if v is not None}
                simplified_resources.append(simplified_resource)
            
            # Provide type breakdown for resources
            type_summary = {}
            if resource_type == "resources":
                type_summary = {
                    "custom_resources": len([r for r in resources if r.get("type") == "CUSTOM"]),
                    "pingone_api_resources": len([r for r in resources if r.get("type") == "PING_ONE_API"]),
                    "openid_connect_resources": len([r for r in resources if r.get("type") == "OPENID_CONNECT"])
                }
            
            if ctx:
                await ctx.info(f"Retrieved {len(resources)} {resource_type}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "environment_name": environment or "default",
                "resource_type": resource_type,
                "resources": simplified_resources,
                "environment": env_info,
                "summary": {
                    "resource_count": len(resources),
                    "limit_applied": limit,
                    "filter_applied": filter_by or "none",
                    "type_breakdown": type_summary,
                    "usage_note": f"Use resource IDs for detailed {resource_type} operations"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing {resource_type} in environment {environment}: {str(e)}")
            logger.exception(f"Error in list_pingone_environment_resources")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_environment_activity(
        activity_type: Annotated[Literal["audit", "sessions"], Field(description="Type of activity to retrieve")] = "audit",
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        filter_by: Annotated[str, Field(description="SCIM filter for audit activities. See docstring for complete syntax.")] = "",
        environment: Annotated[str, Field(description="Environment name (like 'Production') or leave empty for default")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get activity and audit information for a specific configured environment.
        
        RECOMMENDED WORKFLOW:
        1. First call create_date_range("1 week ago", "now") to get proper date filter
        2. Copy the 'scim_filter' result to the filter_by parameter below
        3. Optionally add additional filters with 'and' operator
        
        Activity Types:
        • audit - Audit logs and administrative actions (REQUIRES date range filter)
        • sessions - Environment-wide session activity
        
        SCIM Filter Syntax for Audit Activities (filter_by parameter):
        
        REQUIRED: Date range filter (MUST be included):
        • recordedat gt "2024-06-01T00:00:00Z" and recordedat lt "2024-06-22T23:59:59Z"
        
        Date Operators:
        • gt (greater than), lt (less than), ge (greater than or equal), le (less than or equal)
        
        OPTIONAL Additional Filters (can be added with 'and'):
        
        Population Filters:
        • resources.population.id eq "uuid" - Events for specific population
        
        Actor/User Filters:
        • actors.user.id eq "uuid" - Events performed by specific user ID
        • actors.user.name eq "username" - Events performed by specific user name
        • actors.client.id eq "uuid" - Events performed by specific client ID
        
        Action Filters:
        • action.type eq "AUTHENTICATION" - Specific action types
        Common types: AUTHENTICATION, PASSWORD_RESET, USER_PROVISIONING, etc.
        
        Resource Filters:
        • resources.id eq "uuid" - Events for specific resource ID
        • resources.type eq "USER" - Resource types: USER | ENVIRONMENT | ORGANIZATION | ALL
        
        Organization/Environment Filters:
        • org.id eq "uuid" - Events for specific organization
        • environment.id eq "uuid" - Events for specific environment
        
        Correlation ID:
        • correlationid eq "correlation-id" - Events with specific correlation ID
        
        Tags:
        • tags eq "adminIdentityEvent" - Admin identity events only
        
        Supported SCIM Operators:
        • eq (equals), gt (greater than), lt (less than), ge (>=), le (<=)
        • and (logical AND), or (logical OR)
        
        NOT SUPPORTED (will cause 400 errors):
        • result.status - Not filterable in PingOne audit API
        • ne (not equal), co (contains), ew (ends with), sw (starts with)
        • pr (present), in (includes), not (logical NOT)
        
        Example Valid Filters:
        • 'recordedat gt "2024-06-01T00:00:00Z" and recordedat lt "2024-06-22T23:59:59Z"'
        • 'recordedat gt "2024-06-20T00:00:00Z" and action.type eq "AUTHENTICATION"'
        • 'recordedat gt "2024-06-01T00:00:00Z" and resources.type eq "USER"'
        • 'recordedat gt "2024-06-01T00:00:00Z" and actors.user.name eq "admin@company.com"'
        • 'recordedat gt "2024-06-01T00:00:00Z" and resources.population.id eq "uuid"'
        
        TIP: Use datetime tools for easy date filtering:
        • create_date_range("1 week ago", "now") - Creates complete filter string
        • parse_relative_time("yesterday") - Converts to timestamp  
        • get_current_time(buffer_hours=-24) - Gets timestamp for 24 hours ago
        
        Common Date Ranges (use datetime tools):
        • Last 24 hours: create_date_range("1 day ago", "now")
        • Last week: create_date_range("1 week ago", "now")  
        • Yesterday: create_date_range("yesterday", "today")
        • Custom: create_date_range("3 days ago", "1 hour ago")
        
        For security monitoring, compliance auditing, and troubleshooting.
        Note: To filter by success/failure, review the 'result' field in the response data programmatically.
        """
        try:
            logger.info("SERVER: Executing get_pingone_environment_activity")
            if ctx:
                await ctx.info("Executing get_pingone_environment_activity")
                await ctx.report_progress(15, 100)
            
            environment = environment.strip() if environment else ""
            filter_by = filter_by.strip() if filter_by else ""
            
            # Map activity types to endpoints
            endpoint_map = {
                "audit": "activities",
                "sessions": "sessions"
            }
            
            endpoint = endpoint_map.get(activity_type)
            if not endpoint:
                raise ToolError(f"Invalid activity type: {activity_type}")
            
            # Validate required filter for audit activities
            if activity_type == "audit" and not filter_by:
                raise ToolError("Audit activities require a date range filter. Use create_date_range() tool first to generate proper filter. Example: 'recordedat gt \"2024-06-01T00:00:00Z\" and recordedat lt \"2024-06-22T23:59:59Z\"'")
            
            if activity_type == "audit" and "recordedat" not in filter_by.lower():
                raise ToolError("Audit activities must include recordedat date range filter. Use create_date_range() tool to generate proper filter. Example: 'recordedat gt \"2024-06-01T00:00:00Z\" and recordedat lt \"2024-06-22T23:59:59Z\"'")
            
            # Check for unsupported filters that cause 400 errors
            if activity_type == "audit" and filter_by:
                unsupported_filters = [
                    "result.status", "result.description", "ne ", "co ", "ew ", "sw ", 
                    "pr ", "in ", " not ", "starts with", "contains", "ends with"
                ]
                for unsupported in unsupported_filters:
                    if unsupported in filter_by.lower():
                        raise ToolError(f"Filter contains unsupported attribute/operator: '{unsupported}'. PingOne audit API only supports: eq, gt, lt, ge, le, and, or. Use docstring for valid filter attributes.")
            
            query_params = {"limit": limit}
            if filter_by:
                query_params["filter"] = filter_by
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=endpoint,
                query_params=query_params,
                environment=environment,
                paginated=True,
                page_size=limit
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'Activity data not found')
                
                if "400" in str(error_details) and activity_type == "audit":
                    if "not supported in filter" in str(error_details):
                        raise ToolError(f"Invalid audit filter - unsupported attribute. Check docstring for valid filter attributes. Only eq, gt, lt, ge, le, and, or operators are supported. Error: {error_details}")
                    else:
                        raise ToolError(f"Invalid audit filter format. Use create_date_range() tool to generate proper date range. Ensure format: 'recordedat gt \"2024-06-01T00:00:00Z\" and recordedat lt \"2024-06-22T23:59:59Z\"'. Error: {error_details}")
                elif "404" in str(error_details):
                    raise ToolError(f"Environment '{environment}' not found or no {activity_type} data available.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for {activity_type} data in environment '{environment}'. Check API scopes: p1:read:activities")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            activities = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields for audit activities
            if activity_type == "audit":
                simplified_activities = []
                for activity in activities:
                    actors = activity.get("actors", {})
                    action = activity.get("action", {})
                    result_info = activity.get("result", {})
                    resources = activity.get("resources", [])
                    
                    simplified_activity = {
                        "id": activity.get("id"),
                        "createdAt": activity.get("createdAt"),
                        "recordedAt": activity.get("recordedAt"),
                        "action": {
                            "type": action.get("type"),
                            "description": action.get("description")
                        },
                        "result": {
                            "status": result_info.get("status"),
                            "description": result_info.get("description")
                        },
                        "actors": {
                            "user": actors.get("user", {}).get("name") if actors.get("user") else None,
                            "client": actors.get("client", {}).get("name") if actors.get("client") else None
                        },
                        "resources": [{"type": r.get("type"), "name": r.get("name")} for r in resources] if resources else [],
                        "correlationId": activity.get("correlationId")
                    }
                    # Remove None values
                    simplified_activity = {k: v for k, v in simplified_activity.items() if v is not None}
                    simplified_activities.append(simplified_activity)
                activities = simplified_activities
            
            if ctx:
                await ctx.info(f"Retrieved {len(activities)} {activity_type} activities")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "environment_name": environment or "default",
                "activity_type": activity_type,
                "activities": activities,
                "environment": env_info,
                "summary": {
                    "activity_count": len(activities),
                    "limit_applied": limit,
                    "filter_applied": filter_by or "none",
                    "time_range": "Based on recordedat filter" if activity_type == "audit" else "Recent activities",
                    "usage_note": f"Activity data for {activity_type} monitoring and analysis",
                    "filter_note": "To filter by success/failure, use result.status field in response data programmatically"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting {activity_type} activity for environment {environment}: {str(e)}")
            logger.exception(f"Error in get_pingone_environment_activity")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    logger.info("Registered PingOne environment management tools")