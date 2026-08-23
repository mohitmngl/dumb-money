import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dumbmoney-dev-secret-key")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
US_DB = os.path.join(BASE_DIR, "screener.db")
INDIA_DB = os.path.join(BASE_DIR, "india.db")
CRYPTO_DB = os.path.join(BASE_DIR, "crypto.db")

DB_PATHS = {"US": US_DB, "INDIA": INDIA_DB, "CRYPTO": CRYPTO_DB}

DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")
DELTA_BASE_URL = "https://api.india.delta.exchange"
DELTA_WS_URL = "wss://socket.india.delta.exchange"
DELTA_PUBLIC_WS_URL = "wss://public-socket.india.delta.exchange"

INDIA_INDICES = ["^NSEI", "^NSEBANK", "^BSESN", "^BSEIDX"]
INDIA_EXCLUDES = ["^", ".OLD", ".DE", ".SG", ".HK"]
