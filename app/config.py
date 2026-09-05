from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8080
    max_upload_mb: int = 200
    ffmpeg: str = "ffmpeg"

    @property
    def tracks_dir(self) -> Path:
        return self.data_dir / "tracks"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def backgrounds_dir(self) -> Path:
        return self.data_dir / "backgrounds"

    def ensure_dirs(self) -> None:
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.backgrounds_dir.mkdir(parents=True, exist_ok=True)


config = AppConfig()
