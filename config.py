"""Environment-based configuration for ITIL Reflexion Agent."""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Configuration loaded from environment variables."""

    # LLM Settings
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # Temperature tuning per agent role
    actor_temperature: float = field(default_factory=lambda: float(os.getenv("ACTOR_TEMPERATURE", "0.7")))
    evaluator_temperature: float = field(default_factory=lambda: float(os.getenv("EVALUATOR_TEMPERATURE", "0.3")))
    reflector_temperature: float = field(default_factory=lambda: float(os.getenv("REFLECTOR_TEMPERATURE", "0.5")))

    # Reflexion loop settings
    max_iterations: int = field(default_factory=lambda: int(os.getenv("MAX_ITERATIONS", "3")))
    score_threshold: int = field(default_factory=lambda: int(os.getenv("SCORE_THRESHOLD", "90")))

    # ServiceNow Settings (direct REST API)
    servicenow_instance: str = field(default_factory=lambda: os.getenv("SERVICENOW_INSTANCE", ""))
    servicenow_username: str = field(default_factory=lambda: os.getenv("SERVICENOW_USERNAME", ""))
    servicenow_password: str = field(default_factory=lambda: os.getenv("SERVICENOW_PASSWORD", ""))

    # MCP Settings (alternative to direct REST)
    servicenow_mcp_url: str = field(default_factory=lambda: os.getenv("SERVICENOW_MCP_URL", ""))
    mcp_server_port: int = field(default_factory=lambda: int(os.getenv("MCP_SERVER_PORT", "8100")))

    # Server Settings
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8080")))
    cors_origins: list = field(default_factory=lambda: os.getenv(
        "CORS_ORIGINS",
        "https://vuduvations.io,https://www.vuduvations.io,http://localhost:3000"
    ).split(","))

    # Data
    data_dir: str = field(default_factory=lambda: os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    ))

    @property
    def use_servicenow(self) -> bool:
        """True if any ServiceNow connection method is configured."""
        return bool(self.servicenow_instance) or bool(self.servicenow_mcp_url)

    @property
    def use_servicenow_direct(self) -> bool:
        """True if direct REST API credentials are configured."""
        return bool(self.servicenow_instance) and bool(self.servicenow_username)


config = Config()
