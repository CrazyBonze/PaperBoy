from pydantic import BaseSettings
from system_message import system_message


class Settings(BaseSettings):
    token: str = ""
    guild = int
    channels = [int]
    message_lifetime: int = 60  # Default to 60 seconds or 1 minute
    selenium_url: str = "http://selenium:4444/wd/hub"
    openai_api_key: str
    openai_model: str = "gpt-3.5-turbo-16k"
    system_message: str = system_message

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
