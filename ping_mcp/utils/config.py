import os
import re
import logging
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger("ping_mcp")

@dataclass
class EnvironmentConfig:
    """Configuration for a single PingOne environment."""
    name: str
    id: str
    client_id: str
    client_secret: str
    aliases: List[str]
    
    def matches(self, input_name: str) -> bool:
        """Check if this environment matches the given input (name or alias)."""
        input_lower = input_name.lower().strip()
        if not input_lower:
            return False
            
        # Check exact name match
        if self.name.lower() == input_lower:
            return True
            
        # Check alias matches
        return any(alias.lower() == input_lower for alias in self.aliases)

@dataclass
class PingOneConfig:
    """Configuration for PingOne MCP server."""
    region: str
    org_id: str
    default_env: str
    environments: Dict[str, EnvironmentConfig]  # name -> EnvironmentConfig mapping
    env_type: Optional[str] = None
    max_requests_per_second: int = 50
    max_retries: int = 3
    request_timeout: int = 30
    default_page_size: int = 100
    max_page_size: int = 1000

class ConfigManager:
    """Manages configuration loading and validation."""
    
    # Regional URL mappings
    REGION_URLS = {
        "north_america": {
            "api_base": "https://api.pingone.com",
            "auth_base": "https://auth.pingone.com"
        },
        "europe": {
            "api_base": "https://api.pingone.eu", 
            "auth_base": "https://auth.pingone.eu"
        },
        "asia_pacific": {
            "api_base": "https://api.pingone.asia",
            "auth_base": "https://auth.pingone.asia"
        }
    }
    
    @staticmethod
    def discover_environments() -> Dict[str, EnvironmentConfig]:
        """Discover all environments from PING_ENV_N_* variables."""
        environments = {}
        
        # Pattern to match PING_ENV_N_NAME variables
        env_pattern = re.compile(r'^PING_ENV_(\d+)_NAME$')
        
        # Find all environment indices
        env_indices = set()
        for key in os.environ:
            match = env_pattern.match(key)
            if match:
                env_indices.add(int(match.group(1)))
        
        logger.info(f"Found environment indices: {sorted(env_indices)}")
        
        # Build environment configs
        for index in env_indices:
            try:
                env_config = ConfigManager._build_environment_config(index)
                if env_config:
                    environments[env_config.name] = env_config
                    logger.info(f"Loaded environment: {env_config.name} (aliases: {env_config.aliases})")
            except Exception as e:
                logger.warning(f"Failed to load environment {index}: {e}")
                continue
        
        return environments
    
    @staticmethod
    def _build_environment_config(index: int) -> Optional[EnvironmentConfig]:
        """Build environment config for a specific index."""
        prefix = f"PING_ENV_{index}_"
        
        # Required fields
        name = os.getenv(f"{prefix}NAME")
        env_id = os.getenv(f"{prefix}ID")
        client_id = os.getenv(f"{prefix}CLIENT_ID")
        client_secret = os.getenv(f"{prefix}CLIENT_SECRET")
        
        # Check required fields
        if not all([name, env_id, client_id, client_secret]):
            missing = []
            if not name: missing.append(f"{prefix}NAME")
            if not env_id: missing.append(f"{prefix}ID") 
            if not client_id: missing.append(f"{prefix}CLIENT_ID")
            if not client_secret: missing.append(f"{prefix}CLIENT_SECRET")
            
            logger.warning(f"Environment {index} missing required fields: {missing}")
            return None
        
        # Optional aliases
        aliases_str = os.getenv(f"{prefix}ALIAS", "")
        aliases = [alias.strip() for alias in aliases_str.split(",") if alias.strip()] if aliases_str else []
        
        return EnvironmentConfig(
            name=name,
            id=env_id,
            client_id=client_id,
            client_secret=client_secret,
            aliases=aliases
        )
    
    @staticmethod
    def load_config() -> PingOneConfig:
        """Load configuration from environment variables."""
        
        # Required global settings
        region = os.getenv("PING_REGION")
        org_id = os.getenv("PING_ORG_ID")
        default_env = os.getenv("PING_DEFAULT_ENV")
        
        if not all([region, org_id, default_env]):
            missing = []
            if not region: missing.append("PING_REGION")
            if not org_id: missing.append("PING_ORG_ID")
            if not default_env: missing.append("PING_DEFAULT_ENV")
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Discover environments
        environments = ConfigManager.discover_environments()
        
        if not environments:
            raise ValueError("No environments configured. Please set PING_ENV_1_NAME, PING_ENV_1_ID, etc.")
        
        # Validate default environment exists
        if default_env not in environments:
            # Try to find by alias
            default_env_config = None
            for env_config in environments.values():
                if env_config.matches(default_env):
                    default_env_config = env_config
                    default_env = env_config.name  # Use the actual name
                    break
            
            if not default_env_config:
                available = [f"{name} (aliases: {', '.join(config.aliases)})" for name, config in environments.items()]
                raise ValueError(f"Default environment '{default_env}' not found. Available environments:\n" + "\n".join(available))
        
        # Optional settings with defaults
        env_type = os.getenv("PING_ENV_TYPE") or None
        max_requests_per_second = int(os.getenv("PING_MAX_REQUESTS_PER_SECOND", "50"))
        max_retries = int(os.getenv("PING_MAX_RETRIES", "3"))
        request_timeout = int(os.getenv("PING_REQUEST_TIMEOUT", "30"))
        default_page_size = int(os.getenv("PING_DEFAULT_PAGE_SIZE", "100"))
        max_page_size = int(os.getenv("PING_MAX_PAGE_SIZE", "1000"))
        
        config = PingOneConfig(
            region=region,
            org_id=org_id,
            default_env=default_env,
            environments=environments,
            env_type=env_type,
            max_requests_per_second=max_requests_per_second,
            max_retries=max_retries,
            request_timeout=request_timeout,
            default_page_size=default_page_size,
            max_page_size=max_page_size
        )
        
        # Validate configuration
        ConfigManager.validate_config(config)
        
        return config
    
    @staticmethod
    def validate_config(config: PingOneConfig) -> None:
        """Validate configuration settings."""
        # Validate region
        if config.region not in ConfigManager.REGION_URLS:
            valid_regions = list(ConfigManager.REGION_URLS.keys())
            raise ValueError(f"Invalid region '{config.region}'. Valid regions: {valid_regions}")
        
        # Validate rate limiting settings
        if not 1 <= config.max_requests_per_second <= 100:
            raise ValueError("max_requests_per_second must be between 1 and 100")
        
        if not 0 <= config.max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        
        if not 1 <= config.request_timeout <= 300:
            raise ValueError("request_timeout must be between 1 and 300 seconds")
        
        if not 1 <= config.default_page_size <= 1000:
            raise ValueError("default_page_size must be between 1 and 1000")
        
        if not 1 <= config.max_page_size <= 1000:
            raise ValueError("max_page_size must be between 1 and 1000")
        
        if config.default_page_size > config.max_page_size:
            raise ValueError("default_page_size cannot be greater than max_page_size")
        
        # Validate environment names are unique
        env_names = [env.name.lower() for env in config.environments.values()]
        if len(env_names) != len(set(env_names)):
            raise ValueError("Environment names must be unique (case-insensitive)")
        
        # Validate aliases don't conflict with environment names or other aliases
        all_names_and_aliases = set()
        for env in config.environments.values():
            # Check environment name
            name_lower = env.name.lower()
            if name_lower in all_names_and_aliases:
                raise ValueError(f"Environment name '{env.name}' conflicts with another name or alias")
            all_names_and_aliases.add(name_lower)
            
            # Check aliases
            for alias in env.aliases:
                alias_lower = alias.lower()
                if alias_lower in all_names_and_aliases:
                    raise ValueError(f"Alias '{alias}' in environment '{env.name}' conflicts with another name or alias")
                all_names_and_aliases.add(alias_lower)
        
        logger.info("Configuration validation passed")
    
    @staticmethod
    def get_api_base_url(region: str) -> str:
        """Get API base URL for a region."""
        if region not in ConfigManager.REGION_URLS:
            raise ValueError(f"Invalid region: {region}")
        return ConfigManager.REGION_URLS[region]["api_base"]
    
    @staticmethod
    def get_auth_base_url(region: str) -> str:
        """Get auth base URL for a region."""
        if region not in ConfigManager.REGION_URLS:
            raise ValueError(f"Invalid region: {region}")
        return ConfigManager.REGION_URLS[region]["auth_base"]
    
    @staticmethod
    def resolve_environment(config: PingOneConfig, environment_input: str = "") -> Tuple[str, EnvironmentConfig]:
        """
        Resolve environment input to (env_name, env_config) with smart matching.
        
        Args:
            config: PingOne configuration
            environment_input: User input like "development", "dev", "prod", or ""
            
        Returns:
            (environment_name, environment_config)
        """
        if not environment_input:
            # Use default environment
            env_name = config.default_env
            env_config = config.environments[env_name]
            return env_name, env_config
        
        # Try to find matching environment
        for env_name, env_config in config.environments.items():
            if env_config.matches(environment_input):
                return env_name, env_config
        
        # Environment not found - provide helpful error
        available = []
        for env_name, env_config in config.environments.items():
            aliases_str = f" (aliases: {', '.join(env_config.aliases)})" if env_config.aliases else ""
            available.append(f"'{env_name}'{aliases_str}")
        
        raise ValueError(f"Environment '{environment_input}' not found. Available environments: {', '.join(available)}")
    
    @staticmethod
    def get_available_environments(config: PingOneConfig) -> List[Dict[str, any]]:
        """Get list of available environments with details."""
        environments = []
        for env_name, env_config in config.environments.items():
            environments.append({
                "name": env_name,
                "id": env_config.id,
                "aliases": env_config.aliases,
                "is_default": env_name == config.default_env
            })
        return environments
    
    @staticmethod
    def get_environment_credentials(config: PingOneConfig, env_name: str) -> Tuple[str, str]:
        """Get client_id and client_secret for an environment."""
        _, env_config = ConfigManager.resolve_environment(config, env_name)
        return env_config.client_id, env_config.client_secret
    
    @staticmethod
    def get_environment_id(config: PingOneConfig, env_name: str) -> str:
        """Get environment ID for a given environment name."""
        _, env_config = ConfigManager.resolve_environment(config, env_name)
        return env_config.id
    
    @staticmethod
    def is_valid_environment(config: PingOneConfig, env_name: str) -> bool:
        """Check if an environment name is valid."""
        try:
            ConfigManager.resolve_environment(config, env_name)
            return True
        except ValueError:
            return False