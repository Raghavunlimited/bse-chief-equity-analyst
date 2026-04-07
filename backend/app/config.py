from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = BASE_DIR / "nse_cache"
DB_PATH = DATA_DIR / "swing_trader.db"

@dataclass
class Config:
    """Application configuration"""

    # Data paths
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    raw_dir: Path = RAW_DIR
    processed_dir: Path = PROCESSED_DIR
    cache_dir: Path = CACHE_DIR
    db_path: Path = DB_PATH

    # Trading parameters
    risk_per_trade: float = 0.02  # 2% risk per trade
    min_traded_value: float = 10_00_00_000  # 10 Cr minimum avg traded value
    min_price: float = 50.0  # Minimum stock price

    # Screener parameters
    rsi_min: float = 55.0
    rsi_max: float = 70.0
    breakout_threshold: float = 0.98  # Within 2% of 20-day high
    volume_multiplier: float = 1.5  # Volume > 1.5x average

    # ATR-based targets
    stop_loss_atr_multiple: float = 1.0
    target_atr_multiple: float = 2.0

    def __post_init__(self):
        """Create directories if they don't exist"""
        for dir_path in [self.data_dir, self.raw_dir, self.processed_dir, self.cache_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

config = Config()
