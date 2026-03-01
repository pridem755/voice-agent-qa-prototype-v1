"""
Application configuration using Pydantic settings.

Loads environment variables from .env file and provides
type-safe access to all configuration values.
"""
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All values are loaded from .env file. See .env.example for
    required variables and their descriptions.
    """
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )
    
    # Twilio configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    target_phone_number: str = "+18054398008"
    
    # OpenAI configuration
    openai_api_key: str
    openai_model: str = "gpt-4o"
    
    # Deepgram configuration
    deepgram_api_key: str
    
    # ElevenLabs configuration
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
    
    # Server configuration
    server_port: int = 8000
    public_host: str
    
    # Behavior configuration
    call_timeout_seconds: int = 600  # 10 minutes
    max_turns: int = 40  # Maximum conversation turns


# Global settings instance
settings = Settings()