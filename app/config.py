from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    confluence_base_url: str = ""
    confluence_api_token: str = ""
    confluence_email: str = ""
    confluence_root_page_id: str = ""
    github_mcp_server_url: str = ""
    github_mcp_token: str = ""
    deepseek_api_key: str = ""
    github_webhook_secret: str = ""


settings = Settings()
