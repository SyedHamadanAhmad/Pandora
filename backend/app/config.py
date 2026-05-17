from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pandora:pandora@postgres:5432/pandora"
    rabbitmq_url: str = "amqp://pandora:pandora@rabbitmq:5672/"
    secret_key: str = "dev-secret"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "pandora"
    minio_secret_key: str = "pandora-secret"
    minio_bucket: str = "pandora-images"
    deepseek_api_key: str = ""


settings = Settings()
