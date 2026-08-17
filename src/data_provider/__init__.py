from src.data_provider.base import MarketDataProvider, MarketDataError, Quote, HistoricalHigh


def get_provider(provider_name: str) -> MarketDataProvider:
    """Factory: returns a MarketDataProvider instance for the given name."""
    if provider_name == "yfinance":
        from src.data_provider.yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    raise ValueError(f"Unknown market data provider: {provider_name}")


__all__ = ["MarketDataProvider", "MarketDataError", "Quote", "HistoricalHigh", "get_provider"]
