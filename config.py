import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

@dataclass(frozen=True)
class Settings:
    api_key: str
    domain: int
    batch_size: int
    db_path: Path = ROOT / "data" / "sellers.db"
    export_dir: Path = ROOT / "exports"
    log_dir: Path = ROOT / "logs"

def get_settings():
    key = os.getenv("KEEPA_API_KEY", "").strip()
    if not key or key.startswith("replace_"):
        raise RuntimeError("Add your Keepa API key to .env.")
    return Settings(key, int(os.getenv("KEEPA_DOMAIN", "1")),
                    min(100, int(os.getenv("KEEPA_SELLER_BATCH_SIZE", "100"))))
