"""Main MCP server implementation for PingOne using FastMCP 2.8.1."""

import logging
from fastmcp import FastMCP

logger = logging.getLogger("ping_mcp")

def create_server():
    """Create and configure the PingOne MCP server using FastMCP 2.8.1."""
    try:
        # Create server with modern FastMCP features
        mcp = FastMCP(
            name="PingOne MCP Server",
            instructions="""
            This server provides PingOne Identity Cloud management capabilities.
            Use list_pingone_users() to search and filter users with SCIM expressions.
            Use get_pingone_user() to retrieve detailed user information.
            All operations require proper PingOne API credentials in environment variables.
            """,
            # Use built-in error masking instead of custom handling
            mask_error_details=False,  # Show detailed errors for debugging
            # Remove this line - it causes the deprecation warning
            stateless_http=True,  # 
        )
        
        # Initialize PingOne client
        from ping_mcp.utils.ping_client import PingOneClient
        from ping_mcp.utils.config import ConfigManager
        
        logger.info("Initializing PingOne client")
        config = ConfigManager.load_config()
        ping_client = PingOneClient(config)
        
        # Register tools directly - no registry needed
        logger.info("Registering PingOne tools")
        from ping_mcp.tools.user_tools import register_user_tools
        from ping_mcp.tools.population_tools import register_population_tools
        from ping_mcp.tools.factors_tools import register_user_factor_tools
        from ping_mcp.tools.group_tools import register_group_tools
        from ping_mcp.tools.environment_tools import register_environment_tools
        from ping_mcp.tools.datetime_tools import register_datetime_tools
        register_user_tools(mcp, ping_client)
        register_population_tools(mcp, ping_client)
        register_user_factor_tools(mcp, ping_client)
        register_group_tools(mcp, ping_client)
        register_environment_tools(mcp, ping_client)
        register_datetime_tools(mcp, ping_client)
        
        # Store client reference for potential cleanup
        mcp.ping_client = ping_client
        
        logger.info("PingOne MCP server created successfully with user management tools")
        
        return mcp
    
    except Exception as e:
        logger.error(f"Error creating PingOne MCP server: {e}")
        raise

# Keep the run functions for compatibility but they won't be used with the new main.py
def run_with_stdio(server):
    """Run the server with STDIO transport (secure, default)."""
    logger.info("Starting PingOne server with STDIO transport")
    server.run()  # FastMCP defaults to STDIO

def run_with_sse(server, host="0.0.0.0", port=3000, reload=False):
    """Run the server with SSE transport (deprecated)."""
    logger.warning("SSE transport is deprecated in FastMCP 2.8.1, use --http instead")
    logger.info(f"Starting PingOne server with SSE transport on {host}:{port}")
    
    try:
        server.run(transport="sse", host=host, port=port)
    except (ValueError, TypeError) as e:
        logger.warning(f"SSE transport failed ({e}), falling back to HTTP")
        run_with_http(server, host, port)

def run_with_http(server, host="0.0.0.0", port=3000):
    """Run the server with HTTP transport (modern, recommended for web)."""
    logger.info(f"Starting PingOne server with HTTP transport on {host}:{port}")
    
    try:
        server.run(transport="streamable-http", host=host, port=port)
    except TypeError as e:
        logger.warning(f"Host/port not supported in this FastMCP version: {e}")
        server.run(transport="streamable-http")

if __name__ == "__main__":
    server = create_server()
    run_with_stdio(server)