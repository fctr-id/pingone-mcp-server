"""Datetime parsing and formatting utilities for PingOne MCP server."""

import logging
from datetime import datetime, timedelta, timezone
import dateparser
from typing import Annotated, Optional
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field

logger = logging.getLogger("ping_mcp_server")

def register_datetime_tools(server: FastMCP, ping_client):
    """Register datetime utility tools with the MCP server."""
    
    @server.tool()
    async def get_current_time(
        buffer_hours: Annotated[int, Field(description="Optional number of hours to add/subtract from current time (negative for past)")] = 0,
        format_for_pingone: Annotated[bool, Field(description="Format for PingOne API compatibility (ISO 8601 with Z suffix)")] = True,
        ctx: Context | None = None
    ) -> dict:
        """Get the current date and time in UTC, formatted for PingOne API usage.
        
        Returns current UTC timestamp, useful for PingOne audit queries and date filtering.
        Use buffer_hours to get times in the past (negative) or future (positive).
        
        Examples:
        - buffer_hours=0: Current time
        - buffer_hours=-24: 24 hours ago  
        - buffer_hours=-168: 1 week ago (7*24 hours)
        """
        try:
            logger.info("SERVER: Executing get_current_time")
            if ctx:
                await ctx.info(f"Getting current time with buffer of {buffer_hours} hours")
                await ctx.report_progress(25, 100)
            
            # Get current UTC time
            now = datetime.now(timezone.utc)
            
            # Add buffer if specified
            if buffer_hours != 0:
                now += timedelta(hours=buffer_hours)
                if ctx:
                    direction = "future" if buffer_hours > 0 else "past"
                    await ctx.info(f"Applied {abs(buffer_hours)} hour buffer to {direction}")
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            # Format for PingOne API compatibility - WITHOUT microseconds
            if format_for_pingone:
                # PingOne expects ISO 8601 with Z suffix for UTC, no microseconds
                formatted_time = now.strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                # Standard ISO 8601 with timezone offset
                formatted_time = now.isoformat()
            
            if ctx:
                await ctx.info(f"Generated timestamp: {formatted_time}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "timestamp": formatted_time,
                "timezone": "UTC",
                "buffer_applied_hours": buffer_hours,
                "usage_examples": [
                    f'recordedat gt "{formatted_time}"',
                    f'createdAt gt "{formatted_time}"',
                    f'updatedAt lt "{formatted_time}"'
                ]
            }
            
        except Exception as e:
            if ctx:
                await ctx.error(f"Error getting current time: {str(e)}")
            logger.exception("Error in get_current_time")
            raise ToolError(f"Failed to get current time: {str(e)}")
    
    @server.tool()
    async def parse_relative_time(
        time_expression: Annotated[str, Field(description="Natural language time expression (e.g., '2 days ago', 'last week', 'yesterday', '1 hour ago')")],
        format_for_pingone: Annotated[bool, Field(description="Format for PingOne API compatibility (ISO 8601 with Z suffix)")] = True,
        ctx: Context | None = None
    ) -> dict:
        """Parse natural language time expressions into PingOne API-compatible timestamps.
        
        Converts human-readable time expressions into ISO 8601 formatted timestamps
        suitable for PingOne audit queries and SCIM filters.
        
        Supported expressions:
        - "2 days ago", "1 week ago", "3 months ago"
        - "yesterday", "last week", "last month"  
        - "1 hour ago", "30 minutes ago"
        - "beginning of today", "end of yesterday"
        - "start of this week", "end of last month"
        
        Perfect for constructing audit date ranges like:
        recordedat gt "parsed_start_time" and recordedat lt "parsed_end_time"
        """
        try:
            logger.info("SERVER: Executing parse_relative_time")
            if ctx:
                await ctx.info(f"Parsing relative time expression: '{time_expression}'")
                await ctx.report_progress(25, 100)
            
            # Validate input
            if not time_expression or not time_expression.strip():
                raise ToolError("time_expression cannot be empty")
            
            time_expression = time_expression.strip()
            
            if ctx:
                await ctx.report_progress(50, 100)
            
            # Parse using dateparser with timezone awareness
            parsed_time = dateparser.parse(
                time_expression, 
                settings={
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'TO_TIMEZONE': 'UTC',
                    'PREFER_DAY_OF_MONTH': 'first'  # For expressions like "last month"
                }
            )
            
            if parsed_time is None:
                # Try common PingOne-specific patterns
                common_patterns = {
                    "today": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
                    "yesterday": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1),
                    "this week": datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday()),
                    "last week": datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday() + 7),
                }
                
                parsed_time = common_patterns.get(time_expression.lower())
                
                if parsed_time is None:
                    raise ToolError(f"Could not parse time expression: '{time_expression}'. Try expressions like '2 days ago', 'yesterday', '1 week ago', or '30 minutes ago'")
            
            if ctx:
                await ctx.report_progress(75, 100)
            
            # Ensure timezone awareness
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC
                parsed_time = parsed_time.astimezone(timezone.utc)
            
            # Format for PingOne API compatibility - WITHOUT microseconds
            if format_for_pingone:
                # PingOne expects ISO 8601 with Z suffix for UTC, no microseconds
                formatted_time = parsed_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                # Standard ISO 8601 with timezone offset
                formatted_time = parsed_time.isoformat()
            
            if ctx:
                await ctx.info(f"Successfully parsed '{time_expression}' to: {formatted_time}")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "original_expression": time_expression,
                "timestamp": formatted_time,
                "timezone": "UTC",
                "parsed_datetime": {
                    "year": parsed_time.year,
                    "month": parsed_time.month,
                    "day": parsed_time.day,
                    "hour": parsed_time.hour,
                    "minute": parsed_time.minute,
                    "second": parsed_time.second
                },
                "usage_examples": [
                    f'recordedat gt "{formatted_time}"',
                    f'createdAt lt "{formatted_time}"',
                    f'updatedAt gte "{formatted_time}"'
                ]
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error parsing time expression '{time_expression}': {str(e)}")
            logger.exception(f"Error parsing time expression '{time_expression}'")
            raise ToolError(f"Failed to parse time expression: {str(e)}")
    
    @server.tool()
    async def create_date_range(
        start_expression: Annotated[str, Field(description="Start time expression (e.g., '1 week ago', 'yesterday')")],
        end_expression: Annotated[str, Field(description="End time expression (e.g., 'now', 'today', '1 hour ago')")] = "now",
        ctx: Context | None = None
    ) -> dict:
        """Create a date range for PingOne audit queries and SCIM filters.
        
        Generates start and end timestamps from natural language expressions,
        formatted for direct use in PingOne API calls.
        
        Returns a complete SCIM filter string ready for audit activities:
        recordedat gt "start_time" and recordedat lt "end_time"
        
        Common use cases:
        - Last 24 hours: start="1 day ago", end="now"
        - Last week: start="1 week ago", end="now"  
        - Yesterday: start="yesterday", end="today"
        - Custom range: start="3 days ago", end="1 day ago"
        """
        try:
            logger.info("SERVER: Executing create_date_range")
            if ctx:
                await ctx.info(f"Creating date range from '{start_expression}' to '{end_expression}'")
                await ctx.report_progress(15, 100)
            
            # Parse start time
            if start_expression.lower() == "now":
                start_time = datetime.now(timezone.utc)
            else:
                start_parsed = dateparser.parse(
                    start_expression, 
                    settings={'RETURN_AS_TIMEZONE_AWARE': True, 'TO_TIMEZONE': 'UTC'}
                )
                if start_parsed is None:
                    raise ToolError(f"Could not parse start time expression: '{start_expression}'")
                start_time = start_parsed.astimezone(timezone.utc)
            
            if ctx:
                await ctx.report_progress(40, 100)
            
            # Parse end time
            if end_expression.lower() == "now":
                end_time = datetime.now(timezone.utc)
            else:
                end_parsed = dateparser.parse(
                    end_expression,
                    settings={'RETURN_AS_TIMEZONE_AWARE': True, 'TO_TIMEZONE': 'UTC'}
                )
                if end_parsed is None:
                    raise ToolError(f"Could not parse end time expression: '{end_expression}'")
                end_time = end_parsed.astimezone(timezone.utc)
            
            if ctx:
                await ctx.report_progress(65, 100)
            
            # Validate range
            if start_time >= end_time:
                raise ToolError(f"Start time ({start_time}) must be before end time ({end_time})")
            
            # Format for PingOne API - WITHOUT microseconds
            start_formatted = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_formatted = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Create SCIM filter string for audit activities
            scim_filter = f'recordedat gt "{start_formatted}" and recordedat lt "{end_formatted}"'
            
            # Calculate duration
            duration = end_time - start_time
            duration_hours = duration.total_seconds() / 3600
            
            if ctx:
                await ctx.info(f"Created date range: {duration_hours:.1f} hours ({duration.days} days)")
                await ctx.report_progress(100, 100)
            
            return {
                "success": True,
                "start_time": start_formatted,
                "end_time": end_formatted,
                "scim_filter": scim_filter,
                "duration": {
                    "total_seconds": duration.total_seconds(),
                    "hours": duration_hours,
                    "days": duration.days
                },
                "expressions": {
                    "start": start_expression,
                    "end": end_expression
                },
                "usage_examples": [
                    f"Use in audit activities: filter_by='{scim_filter}'",
                    f"Alternative filters: 'createdAt gt \"{start_formatted}\" and createdAt lt \"{end_formatted}\"'",
                    f"User activity: 'lastSignOn.at gt \"{start_formatted}\"'"
                ]
            }
            
        except ToolError:
            raise
        except Exception as e:
            if ctx:
                await ctx.error(f"Error creating date range: {str(e)}")
            logger.exception("Error in create_date_range")
            raise ToolError(f"Failed to create date range: {str(e)}")
    
    logger.info("Registered PingOne datetime utility tools")