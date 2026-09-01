import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StreetManagerConfig:
    base_url: str = ""
    username: str = ""
    password: str = ""
    api_key: str = ""
    timeout: int = 30


class StreetManagerClient:
    CONFIG_FILE = Path("config") / "street_manager.json"

    def __init__(self):
        self.config = self.load_config()

    def load_config(self) -> StreetManagerConfig:
        if not self.CONFIG_FILE.exists():
            return StreetManagerConfig()

        with open(self.CONFIG_FILE, "r", encoding="utf-8-sig") as file:
            data = json.load(file)

        return StreetManagerConfig(**data)

    @property
    def configured(self) -> bool:
        return bool(
            self.config.base_url
            and (
                self.config.api_key
                or (
                    self.config.username
                    and self.config.password
                )
            )
        )

    def diagnostic_summary(self) -> dict:
        return {
            "configured": self.configured,
            "base_url": self.config.base_url,
            "timeout": self.config.timeout,
        }
