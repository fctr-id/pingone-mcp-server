"""Population management tools for PingOne MCP server."""

import logging
import re
from typing import List, Dict, Any, Optional, Union, Annotated, Literal
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..utils.ping_client import PingOneClient
from ..utils.normalize_ping_responses import PingOneResponseHandler

logger = logging.getLogger("ping_mcp_server")

def register_population_tools(server: FastMCP, ping_client: PingOneClient):
    """Register all population-related tools with the MCP server."""
    
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @server.tool()
    async def list_pingone_populations(
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all populations in the PingOne environment.
        
        Returns population names, IDs, and basic metadata. Use the returned UUIDs 
        in list_pingone_users filter_by parameter like: 'population.id eq "uuid"'.
        
        Populations typically represent organizational units like employees, 
        contractors, or external users.
        """
        try:
            # Add server-side tool logging
            logger.info("Executing list_pingone_populations")
            if ctx:
                await ctx.info("Executing list_pingone_populations")
                await ctx.report_progress(20, 100)
            
            environment = environment.strip() if environment else ""
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint="populations",
                query_params=None,
                environment=environment,
                paginated=True,
                page_size=100
            )
            
            if ctx:
                await ctx.report_progress(80, 100)
            
            if not result["success"]:
                error_msg = f"PingOne API error: {result.get('error', 'Unknown error')}"
                if ctx:
                    await ctx.error(error_msg)
                raise ToolError(error_msg)
            
            populations = result["items"]
            env_info = result.get("environment", {})
            
            # Extract key fields for easy identification
            simplified_populations = []
            for pop in populations:
                simplified_pop = {
                    "id": pop.get("id"),
                    "name": pop.get("name"),
                    "description": pop.get("description", ""),
                    "default": pop.get("default", False),
                    "userCount": pop.get("userCount", 0)
                }
                simplified_populations.append(simplified_pop)
            
            if ctx:
                await ctx.info(f"Retrieved {len(populations)} populations")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "populations": simplified_populations,
                "environment": env_info,
                "summary": {
                    "total_count": len(populations),
                    "usage_note": "Use the 'id' field in list_pingone_users filter: 'population.id eq \"uuid\"'"
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error listing populations: {str(e)}")
            logger.exception("Error in list_pingone_populations")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    @server.tool()
    async def get_pingone_population(
        population_id: Annotated[str, Field(description="Population UUID from list_pingone_populations")],
        include_password_policy: Annotated[bool, Field(description="Include password policy details")] = False,
        environment: Annotated[str, Field(description="Environment name. Leave empty to use default from .env file")] = "",
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Get detailed information about a specific population.
        
        Requires population UUID from list_pingone_populations. Returns comprehensive 
        population configuration including user count, password policies, and settings.
        """
        try:
            # Add server-side tool logging
            logger.info("Executing get_pingone_population")
            if ctx:
                await ctx.info("Executing get_pingone_population")
                await ctx.report_progress(15, 100)
            
            population_id = population_id.strip()
            environment = environment.strip() if environment else ""
            
            # Validate UUID format
            if not is_valid_uuid(population_id):
                raise ToolError(f"Invalid UUID format: {population_id}. Use list_pingone_populations to find correct UUID.")
            
            query_params = {}
            if include_password_policy:
                query_params["include"] = "passwordPolicy"
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            result = await ping_client.get(
                endpoint=f"populations/{population_id}",
                query_params=query_params if query_params else None,
                environment=environment,
                paginated=False
            )
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            if not result["success"]:
                error_details = result.get('error', 'Population not found')
                
                if "400" in str(error_details) or "INVALID_REQUEST" in str(error_details):
                    raise ToolError(f"Invalid population ID. Use list_pingone_populations to find correct UUID.")
                elif "404" in str(error_details):
                    raise ToolError(f"Population {population_id} not found.")
                elif "403" in str(error_details):
                    raise ToolError(f"Access denied for population {population_id}.")
                else:
                    raise ToolError(f"API error: {error_details}")
            
            population = result["item"]
            env_info = result.get("environment", {})
            
            if ctx:
                await ctx.info(f"Retrieved population data for {population_id}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "population": population,
                "environment": env_info,
                "included_data": {
                    "password_policy": include_password_policy
                }
            }
            
        except ToolError:
            raise
        except Exception as e:
            if 'rate limit' in str(e).lower():
                raise ToolError('Rate limit exceeded. Wait and retry.')
            
            if ctx:
                await ctx.error(f"Error getting population {population_id}: {str(e)}")
            logger.exception(f"Error in get_pingone_population for {population_id}")
            raise ToolError(f"Unexpected error: {str(e)}")
    
    logger.info("Registered PingOne population management tools")