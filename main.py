"""
Main entry point for the PingOne MCP Server using FastMCP 2.8.1.
Run this file to start the server.
"""
import os
import sys
import logging
import argparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ping_mcp")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="PingOne MCP Server")
    
    # Transport flags
    parser.add_argument("--http", action="store_true", 
                      help="Use HTTP transport (recommended for web)")
    parser.add_argument("--sse", action="store_true", 
                      help="Use SSE transport (deprecated, falls back to HTTP)")
    parser.add_argument("--stdio", action="store_true", 
                      help="Use STDIO transport (default, secure)")
    parser.add_argument("--iunderstandtherisks", action="store_true",
                      help="Acknowledge security risks of network transports")
    
    # HTTP configuration
    parser.add_argument("--host", default="127.0.0.1", 
                      help="Host to bind to for HTTP transport (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=3000, 
                      help="Port for HTTP transport (default: 3000)")
    
    # General configuration
    parser.add_argument("--log-level", default="INFO", 
                      choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                      help="Set logging level (default: INFO)")
    
    return parser.parse_args()

def main():
    """Start the PingOne MCP server."""
    # Parse arguments
    args = parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load environment variables
    load_dotenv()
    
    # Check for required environment variables
    required_vars = ["PING_REGION", "PING_ORG_ID", "PING_CLIENT_ID", "PING_CLIENT_SECRET"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Create a .env file with:")
        logger.error("PING_REGION=north_america")
        logger.error("PING_ORG_ID=your_org_id_here")
        logger.error("PING_CLIENT_ID=your_client_id_here")
        logger.error("PING_CLIENT_SECRET=your_client_secret_here")
        logger.error("PING_DEFAULT_ENV=Production")
        logger.error("PING_ENVIRONMENTS={\"Production\":\"env_id\",\"Development\":\"env_id\"}")
        return 1
    
    try:
        # Import server module
        from ping_mcp.server import create_server, run_with_http, run_with_sse, run_with_stdio
        
        # Create server
        server = create_server()
        
        # Determine transport
        if args.http:
            if not args.iunderstandtherisks:
                logger.error("HTTP transport requires --iunderstandtherisks flag")
                logger.error("HTTP transport exposes server over network - ensure proper security")
                return 1
            
            logger.warning("SECURITY: HTTP transport exposes server over network")
            run_with_http(server, args.host, args.port)
            
        elif args.sse:
            if not args.iunderstandtherisks:
                logger.error("SSE transport requires --iunderstandtherisks flag")
                return 1
            
            logger.warning("SECURITY: SSE transport exposes server over network")
            logger.warning("DEPRECATED: SSE transport is deprecated, use --http")
            run_with_sse(server, args.host, args.port)
            
        else:
            # Default to STDIO (secure)
            logger.info("Using STDIO transport (secure, recommended)")
            run_with_stdio(server)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        logger.exception("Full error details:")
        return 1

if __name__ == "__main__":
    sys.exit(main())