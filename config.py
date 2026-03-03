from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All values are loaded from .env file. See README.md for
    required variables and their descriptions.
    """
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  
    )
    
    # Twilio configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    target_phone_number: str = "ADD_TARGET_PHONE_NUMBER_HERE"
    
    # OpenAI configuration
    openai_api_key: str
    openai_model: str = "gpt-4o"
    
    # Deepgram configuration
    deepgram_api_key: str
    
    # ElevenLabs configuration
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  
    
    # Server configuration
    server_port: int = 8000
    public_host: str
    
    # Behavior configuration
    call_timeout_seconds: int = 600  
    max_turns: int = 40 


# Global settings instance
settings = Settings()