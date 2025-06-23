<div align="center">
  <a href="https://fctr.io">
    <img src="https://fctr.io/images/logo.svg" alt="fctr.io" width="110" height="auto">
  </a>
</div>

<div align="center">
  <h2>PingOne MCP Server (v.1.0-alpha)</h2>
</div>

<div align="center">
  <h3> **🚀 NEW:** **Complete Transport Support - STDIO & HTTP with Tool Call Visibility!**</h3>
</div>


<div align="center">
The PingOne MCP Server is a powerful tool that enables AI models to interact directly with your PingOne environment using the Model Context Protocol (MCP). Built specifically for identity engineers, security teams, and PingOne administrators, it implements the MCP specification to transform how AI assistants can help manage and analyze PingOne resources.
</div>

<div align="center">
 <a href="https://modelcontextprotocol.io/introduction">Learn about MCP</a></p>
</div>

<div align="center">
<h3>Quick Demo</h3>
<p >
  <img src="images/mcp-server.gif" alt="PingOne MCP Server Demo" width="1024px" height="auto">
</p>
</div>


## 📋 Table of Contents

- [📋 Table of Contents](#-table-of-contents)
- [🔍 What is the Model Context Protocol?](#-what-is-the-model-context-protocol)
- [⚠️ IMPORTANT: Security \& Limitations](#️-important-security--limitations)
  - [🔄 Data Flow \& Privacy](#-data-flow--privacy)
  - [📊 Context Window Limitations](#-context-window-limitations)
  - [🚨 HTTP Transport Security Warning](#-http-transport-security-warning)
- [🛠️ Available Tools](#️-available-tools)
  - [🏢 Environment Management](#-environment-management)
  - [👥 User Management](#-user-management)
  - [🔐 MFA \& Security](#-mfa--security)
  - [👨‍👩‍👧‍👦 Population Management](#-population-management)
  - [🏘️ Group Management](#️-group-management)
  - [🕐 DateTime Utilities](#-datetime-utilities)
  - [Example Use Cases:](#example-use-cases)
- [🚀 Quick Start](#-quick-start)
  - [Prerequisites](#prerequisites)
- [🧠 Supported AI Providers](#-supported-ai-providers)
  - [Currently Supported Providers:](#currently-supported-providers)
  - [Installation](#installation)
  - [Configuration \& Usage](#configuration--usage)
  - [Supported Transports and Launching](#supported-transports-and-launching)
    - [1. Standard I/O (STDIO) - Recommended](#1-standard-io-stdio---recommended)
    - [2. Streamable HTTP Transport - Modern \& Recommended](#2-streamable-http-transport---modern--recommended)
    - [3. Interactive Client](#3-interactive-client)
- [⚠️ Good to Know](#️-good-to-know)
  - [Production Ready 🚀](#production-ready-)
  - [Security First 🛡️](#security-first-️)
  - [Current Capabilities 🔍](#current-capabilities-)
- [🗺️ Roadmap](#️-roadmap)
- [🆘 Need Help?](#-need-help)
- [💡 Feature Requests \& Ideas](#-feature-requests--ideas)
- [👥 Contributors](#-contributors)
- [⚖️ Legal Stuff](#️-legal-stuff)

&nbsp;

## 🔍 What is the Model Context Protocol?

<div align="left">
<p>The Model Context Protocol (MCP) is an open standard that enables AI models to interact with external tools and services in a structured, secure way. It provides a consistent interface for AI systems to discover and use capabilities exposed by servers, allowing AI assistants to extend their functionality beyond their training data.</p>

<p>Think of MCP as the "USB-C of AI integration" - just as USB-C provides a universal standard that allows various devices to connect and communicate regardless of manufacturer, MCP creates a standardized way for AI models to discover and interact with different services without custom integration for each one. This "plug-and-play" approach means developers can build tools once and have them work across multiple AI assistants, while users benefit from seamless integration without worrying about compatibility issues.</p>

<p><strong>Example:</strong> "Show me all locked user accounts in our Production environment, then check which of those users have MFA devices enrolled." <em>The AI uses PingOne MCP Server to query user accounts with account.status eq "LOCKED", then checks MFA enrollment for each user - all through natural language commands.</em></p>
</div>

## ⚠️ IMPORTANT: Security & Limitations

Please read this section carefully before using PingOne MCP Server.

### 🔄 Data Flow & Privacy

When you make a request, the interaction happens directly between the LLM and the PingOne MCP tools - the client application is no longer in the middle. All data returned by these tools (including complete user profiles, group memberships, MFA devices, audit logs, etc.) is sent to and stored in the LLM's context during the entire transaction for that conversation.

**Key Privacy Considerations:**
- The LLM (Claude, GPT, etc.) receives and processes all PingOne data retrieved by the tools
- This data remains in the LLM's context for the duration of the conversation
- You must be comfortable with your PingOne user data being processed by the LLM provider's systems
- Before using these tools, ensure you're comfortable with PingOne data being sent to the AI model's servers

### 📊 Context Window Limitations

**🚨 CRITICAL LIMITATION:** Due to MCP design and LLM context window constraints, you  can only effectively work with **70-90 users maximum** per operation. This is not a technical limitation of PingOne APIs, but rather a fundamental constraint of how much data can fit in an LLM's context window.

**Recommendation:** Always limit user queries and avoid bulk operations.

**Examples:**

❌ **Avoid these types of requests:**
- "Get all users in our tenant and analyze their login patterns" (could be thousands of users)
- "Find all users without MFA and create a report" (potentially hundreds of users)
- "List all users in the Employee population" (likely exceeds context limits)

✅ **Better approaches:**
- "Get the 50 most recently created users in the Contractor population"
- "Find users with email domain @contractor.com, limit to first 30 results" 
- "Show me users whose names start with 'John' in the Production environment"
- "Get audit activity for authentication failures in the last 24 hours"

**Working Within Limits:**
- Use SCIM filters to narrow results: `enabled eq false and type eq "Employee"`
- Use pagination limits: Never exceed 70-90 users in a single request
- Focus on specific populations or user attributes
- Use date filters for audit queries to limit scope

### 🚨 HTTP Transport Security Warning

The HTTP transport mode has significant security risks:
- It opens an unauthenticated HTTP server with full access to your PingOne tenant
- No authentication or authorization is provided
- Anyone who can reach the network port can issue commands to your PingOne environment

**Best Practice:** Only use the STDIO transport method (default mode) unless you have specific security controls in place and understand the risks.

## 🛠️ Available Tools

The PingOne MCP Server provides comprehensive identity management capabilities:

### 🏢 Environment Management
- `list_configured_environments` - **START HERE** - List all environments configured for this MCP server
- `list_pingone_environments` - List ALL environments in your PingOne organization 
- `get_pingone_environment` - Get detailed environment information and configuration
- `list_pingone_environment_resources` - List applications and API resources in an environment
- `get_pingone_environment_activity` - Get audit logs and session activity with date filtering

### 👥 User Management
- `list_pingone_users` - Search users with advanced SCIM filtering (enabled, population, email domain, etc.)
- `get_pingone_user` - Get detailed user information including lifecycle status and MFA settings
- `get_pingone_user_sessions` - Get user login sessions with browser, device, and location details

### 🔐 MFA & Security
- `list_pingone_user_mfa_devices` - List all MFA devices for a user (SMS, TOTP, FIDO2, etc.)
- `get_pingone_user_mfa_device` - Get detailed MFA device information and status

### 👨‍👩‍👧‍👦 Population Management  
- `list_pingone_populations` - List all populations (Employee, Contractor, Customer, etc.)
- `get_pingone_population` - Get population details and password policies

### 🏘️ Group Management
- `list_pingone_groups` - List groups with filtering by name, population, or description
- `get_pingone_group` - Get group details with optional member information
- `list_pingone_group_members` - List all members of a specific group

### 🕐 DateTime Utilities
- `get_current_time` - Get current UTC time with optional offset (e.g., "24 hours ago")
- `parse_relative_time` - Convert natural language to timestamps ("yesterday", "last week")
- `create_date_range` - Create date ranges for audit queries ("1 week ago" to "now")

### Example Use Cases:
- **Security Analysis**: "Show me all failed authentication attempts from yesterday in Production"
- **Compliance Auditing**: "Find all users without MFA enrolled in the Employee population"  
- **User Support**: "Get login sessions for user john.smith@company.com"
- **Environment Management**: "List all custom API resources in our Staging environment"
- **Group Analysis**: "Show me all members of the IT-Administrators group"

## 🚀 Quick Start

### Prerequisites

✅ Python 3.12+ installed on your machine  
✅ PingOne tenant with appropriate API access  
✅ An MCP-compatible AI client (Claude Desktop, Microsoft Copilot Studio, etc.)  

> **⚠️ Important Model Compatibility Note:**  
> Not all AI models work with this MCP server. Testing has only been performed with:
> - GPT-4.0
> - Claude 3.5 Sonnet
> - Google Gemini 2.0
>
> You must use latest model versions that explicitly support tool calling/function calling capabilities.

## 🧠 Supported AI Providers

The PingOne MCP Server supports multiple AI providers through its flexible configuration system.

### Currently Supported Providers:

| Provider | Environment Variable | Description |
|----------|---------------------|-------------|
| **OpenAI** | `AI_PROVIDER=openai` | Connect to OpenAI API with models like GPT-4o. Requires an OpenAI API key. |
| **Azure OpenAI** | `AI_PROVIDER=azure_openai` | Use Azure-hosted OpenAI models with enhanced security and compliance features. |
| **Anthropic** | `AI_PROVIDER=anthropic` | Connect to Anthropic's Claude models (primarily tested with Claude 3.5 Sonnet). |
| **Google Vertex AI** | `AI_PROVIDER=vertex_ai` | Use Google's Gemini models via Vertex AI. Requires Google Cloud service account. |
| **OpenAI Compatible** | `AI_PROVIDER=openai_compatible` | Connect to any OpenAI API-compatible endpoint, such as Fireworks.ai, Ollama, or other providers. |

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/pingone-mcp-server.git
cd pingone-mcp-server

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

> **⚠️ NOTICE:** If you clone this repository anew or pull updates, always make sure to re-run `pip install -r requirements.txt` to ensure all dependencies are up-to-date.

### Configuration & Usage

Create a config file with your PingOne settings:

```bash
# Copy the sample config
cp .env.sample .env

# Edit the .env file with your settings
# Required: PingOne environment details and LLM settings
```

**Sample .env configuration for Multi-Environment Setup:**
```bash
# PingOne Organization Settings
PING_REGION=NA
PING_ORG_ID=your-organization-id

# Default Environment
PING_DEFAULT_ENV=Production

# Environment 1: Production
PING_ENV_1_NAME=Production
PING_ENV_1_ID=prod-environment-id
PING_ENV_1_CLIENT_ID=prod-client-id
PING_ENV_1_CLIENT_SECRET=prod-client-secret
PING_ENV_1_ALIASES=prod,production,live

# Environment 2: Staging  
PING_ENV_2_NAME=Staging
PING_ENV_2_ID=staging-environment-id
PING_ENV_2_CLIENT_ID=staging-client-id
PING_ENV_2_CLIENT_SECRET=staging-client-secret
PING_ENV_2_ALIASES=stage,staging,test

# Environment 3: Development
PING_ENV_3_NAME=Development
PING_ENV_3_ID=dev-environment-id
PING_ENV_3_CLIENT_ID=dev-client-id
PING_ENV_3_CLIENT_SECRET=dev-client-secret
PING_ENV_3_ALIASES=dev,development,sandbox

# AI Provider Configuration (choose one)
AI_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key

# Optional: Logging
LOG_LEVEL=INFO
```

### Supported Transports and Launching

The PingOne MCP Server supports multiple transport protocols:

#### 1. Standard I/O (STDIO) - Recommended

- **Security**: ✅ Direct communication through standard input/output streams
- **Use case**: Ideal for desktop AI assistants like Claude Desktop
- **Performance**: ✅ Lightweight and efficient
- **Visibility**: ✅ Full tool call logging and transparency

**Configuration for Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "pingone-mcp-server": {
      "command": "/path/to/pingone-mcp-server/venv/python",
      "args": [
        "/path/to/pingone-mcp-server/main.py"
      ],
      "env": {
        "PING_REGION": "NA",
        "PING_ORG_ID": "your-organization-id",
        "PING_DEFAULT_ENV": "Production",
        "PING_ENV_1_NAME": "Production",
        "PING_ENV_1_ID": "prod-environment-id",
        "PING_ENV_1_CLIENT_ID": "prod-client-id",
        "PING_ENV_1_CLIENT_SECRET": "prod-client-secret",
        "PING_ENV_1_ALIASES": "prod,production,live",
        "PING_ENV_2_NAME": "Staging",
        "PING_ENV_2_ID": "staging-environment-id",
        "PING_ENV_2_CLIENT_ID": "staging-client-id",
        "PING_ENV_2_CLIENT_SECRET": "staging-client-secret",
        "PING_ENV_2_ALIASES": "stage,staging,test",
        "AI_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "your-anthropic-api-key"
      }
    }
  }
}
```

**Testing STDIO Transport:**
```bash
cd clients
python pingone-mcp-client.py --server ../main.py
```

#### 2. Streamable HTTP Transport - Modern & Recommended

**Features**: ✅ Real-time event streaming, session management, tool call visibility

**Starting the HTTP Server:**
```bash
# Start server
python main.py --http

# Server will start on http://localhost:3000/mcp
```

**Testing HTTP Transport:**
```bash
cd clients
python pingone-mcp-client.py --http http://localhost:3000/mcp
```

**Features:**
- ✅ **Real-time tool visibility** - See exactly which PingOne APIs are being called
- ✅ **Session management** - Maintains connection state
- ✅ **Event streaming** - Live progress updates during operations
- ✅ **Better error handling** - Detailed error responses
- ✅ **Modern protocol** - Based on latest MCP specifications

#### 3. Interactive Client

**For testing and development:**

```bash
cd clients
python pingone-mcp-client.py --server ../main.py

# Or for HTTP transport:
python pingone-mcp-client.py --http http://localhost:3000/mcp
```

**Client Features:**
- 🔍 **Tool call visibility**: See exactly which tools are being called
- 💬 **Interactive shell**: Continuous query support
- 🛠️ **Tool inspection**: Use `tools` command to see available tools
- 🔧 **Debug mode**: Use `debug on` for detailed message exchanges
- 📊 **Structured results**: Clean JSON output formatting

**Example Client Session:**
```
PingOne MCP Client
Type 'exit' to quit
Type 'tools' to show available tools
Type 'debug on' to enable debug mode

Enter your query: find users with email domain @contractor.com in staging environment
Processing query...
2025-06-22T08:55:49.125Z [INFO] [pingone-mcp-server] Directly calling tool: list_pingone_users
Query processed successfully

╭─ Result ─╮
│ {       │
│   "users": [ │
│     {         │
│       "id": "user-uuid-here", │
│       "username": "jane.doe", │
│       "email": "jane.doe@contractor.com", │
│       "enabled": true, │
│       "type": "Contractor" │
│     }       │
│   ]         │
│ }           │
╰───────────╯

Enter your query: show me audit activity for authentication failures yesterday
Processing query...
2025-06-22T08:55:52.125Z [INFO] [pingone-mcp-server] Directly calling tool: create_date_range
2025-06-22T08:55:53.096Z [INFO] [pingone-mcp-server] Directly calling tool: get_pingone_environment_activity
Query processed successfully

╭─ Result ─╮
│ {       │
│   "activities": [ │
│     {         │
│       "action": {"type": "AUTHENTICATION"}, │
│       "result": {"status": "failed"}, │
│       "actors": {"user": "failed.user@company.com"}, │
│       "recordedAt": "2025-06-21T14:30:15Z" │
│     }       │
│   ]         │
│ }           │
╰───────────╯
```

## ⚠️ Good to Know

### Production Ready 🚀
* Stable release with comprehensive tool coverage
* Full user lifecycle management capabilities
* Multi-environment support for Production/Staging/Development workflows
* Robust error handling and logging
* Tested with multiple AI providers
* Ready for enterprise environments

### Security First 🛡️
* Designed for least-privilege operation
* Secure authentication with PingOne APIs
* Multi-environment isolation
* Comprehensive audit logging
* Tool call transparency and monitoring

### Current Capabilities 🔍
* Complete user and group management operations
* Advanced SCIM filtering and search across populations
* Audit log analysis with natural language date ranges
* MFA device management and compliance checking
* Real-time tool call visibility
* Multiple transport protocols
* Rich client applications for testing
* Production-ready error handling

## 🗺️ Roadmap

**v1.0.0 - Current**
- [x] Complete user management with SCIM filtering
- [x] Group and population management
- [x] MFA device management
- [x] Audit log analysis with datetime tools
- [x] Multi-environment support
- [x] STDIO and HTTP transport support
- [x] Tool call visibility and logging
- [x] Advanced client applications
- [x] Multiple AI provider support

**Future Releases:**
- [ ] Application management operations
- [ ] User provisioning and lifecycle workflows
- [ ] Advanced compliance reporting
- [ ] Authentication policy management
- [ ] Risk and sign-on policy tools
- [ ] Approval workflows for sensitive operations
- [ ] Role-based access control for MCP operations
- [ ] Bulk operations with automatic chunking

## 🆘 Need Help?

Before raising an issue, check:
1. 📝 Multi-environment configuration in `.env` file
2. 🔑 PingOne API permissions and credentials for each environment
3. 🔌 MCP client compatibility
4. 📊 Context window limits (70-90 users maximum)
5. 📊 Server logs for error details

**Getting Support:**
- 📚 Check the documentation above
- 🐛 [Report bugs on GitHub](https://github.com/yourusername/pingone-mcp-server/issues)
- 💡 [Request features on GitHub](https://github.com/yourusername/pingone-mcp-server/issues)

**Common Issues:**
- **"Too many results"**: Use SCIM filters to limit user queries under 70-90 users
- **"Environment not found"**: Run `list_configured_environments` first to see available environments
- **"Invalid filter"**: Check tool documentation for supported SCIM filter attributes

## 💡 Feature Requests & Ideas

Have an idea or suggestion? [Open a feature request](https://github.com/yourusername/pingone-mcp-server/issues/new?labels=enhancement) on GitHub!

## 👥 Contributors

Interested in contributing? We'd love to have you! Open an issue or submit a pull request.

## ⚖️ Legal Stuff

Check out [`LICENSE`](LICENSE) for the full license details.

---

🌟 © 2025 PingOne MCP Server. Made with ❤️ for the PingOne and AI communities.