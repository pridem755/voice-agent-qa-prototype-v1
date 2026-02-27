from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
    #-----Twilio ----------------------------------------------------------
    # Your Twilio Account SID and Auth Token — found at console.twilio.com
    twilio_account_sid: str
    twilio_auth_token: str

    # The Twilio phone number your bot calls FROM (must be in your account)
    # Format: E.164 e.g. +12223334444
    twilio_from_number: str

    # The fixed test line for this assessment — do not change
    target_phone_number: str = "+18054398008"

    #----------OpenAI--------------------------------------------------------------
    # Used for both the Patient Brain and the post-call QA analyser
    openai_api_key: str

    # GPT-4o is the right choice here: fast enough for real-time conversation
    # (~400 ms), and smart enough to play a believable patient persona
    openai_model: str = "gpt-4o"

    #----------Deepgram--------------------------------------------------------------
    # Real-time streaming ASR. Deepgram's Nova-2 model has ~200 ms latency
    # which is acceptable for a phone conversation turn-taking cadence.
    deepgram_api_key: str

    #----------ElevenLabs-----------------------------------------------------------
    # TTS provider. "Rachel" is a clear, neutral voice suited to phone audio.
    # Swap voice_id to change persona voice.
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    #------ Server------------------------------------------------------------------
    # FastAPI listens on this port; ngrok must tunnel to the same port
    server_port: int = 8000

    # ngrok assigns a random subdomain each run. Set this to the ngrok URL
    # (without https://) so TwiML can reference the correct WebSocket address.
    # Example: abc123.ngrok.io
    public_host: str

    #----- Behaviour--------------------------------------------------------------
    # Maximum seconds to wait for a call to complete before force-hanging up.
    # Prevents runaway calls if the agent loops or hangs.
    call_timeout_seconds: int = 600

    # Maximum LLM turns before the patient brain politely ends the call.
    # Keeps costs bounded and avoids infinite conversations.
    max_turns: int = 40

    #class Config:
        # Read from a .env file in the project root if present
        #env_file = ".env"
        #env_file_encoding = "utf-8"


# Singleton — import this everywhere rather than constructing a new Settings()
settings = Settings()
