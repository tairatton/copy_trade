"""
Configuration settings - โหลดจาก .env.master, .env.slave เท่านั้น
"""

from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values
from loguru import logger


@dataclass
class MT5Account:
    """MT5 account credentials."""
    login: int
    password: str
    server: str
    mt5_path: str
    label: str = ""


@dataclass
class Settings:
    """Application settings."""
    master: MT5Account = None
    slave: MT5Account = None

    # Hardcoded defaults (ไม่ต้องมี .env)
    poll_interval_ms: int = 500         # ตรวจสอบ master ทุก 500ms
    max_slippage_points: int = 20       # slippage สูงสุด
    log_level: str = "INFO"
    log_file: str = "logs/copytrade.log"


def _load_account(env_file: str) -> MT5Account:
    """Load MT5 account from a .env file."""
    if not Path(env_file).exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ {env_file}")

    values = dotenv_values(env_file)

    login = values.get("MT5_LOGIN", "")
    if not login:
        raise ValueError(f"MT5_LOGIN ไม่ได้ระบุใน {env_file}")

    return MT5Account(
        login=int(login),
        password=values.get("MT5_PASSWORD", ""),
        server=values.get("MT5_SERVER", ""),
        mt5_path=values.get("MT5_PATH", ""),
        label=values.get("ACCOUNT_LABEL", ""),
    )


def load_settings(base_dir: str = None) -> Settings:
    """Load settings from .env.master and .env.slave only."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    base_dir = Path(base_dir)

    master = _load_account(str(base_dir / ".env.master"))
    slave = _load_account(str(base_dir / ".env.slave"))

    logger.info(f"✅ Master: {master.label} (Login: {master.login}, Server: {master.server})")
    logger.info(f"✅ Slave:  {slave.label} (Login: {slave.login}, Server: {slave.server})")

    return Settings(master=master, slave=slave)
