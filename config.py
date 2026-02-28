from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
    #-----Twilio ----------------------------------------------------------
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    target_phone_number: str = "+18054398008"

    #----------OpenAI--------------------------------------------------------------
    openai_api_key: str
    openai_model: str = "gpt-4o"

    #----------Deepgram-------------------------------------------------------------
    deepgram_api_key: str

    #----------ElevenLabs-----------------------------------------------------------
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    #------ Server------------------------------------------------------------------
    server_port: int = 8000
    public_host: str

    #----- Behaviour--------------------------------------------------------------
    call_timeout_seconds: int = 600
    max_turns: int = 40

    #class Config:
        #Read from a .env file in the project root if present
        #env_file = ".env"
        #env_file_encoding = "utf-8"

settings = Settings()
