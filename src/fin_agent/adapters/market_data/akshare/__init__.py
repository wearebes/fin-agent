"""akshare market data adapter (domestic China data sources)."""

from fin_agent.adapters.market_data.akshare.client import AKShareClient
from fin_agent.adapters.market_data.akshare.config import AKShareConfig

__all__ = ["AKShareClient", "AKShareConfig"]
