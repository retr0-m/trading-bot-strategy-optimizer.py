from binance.client import Client

class BinanceClient:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)

    def market_buy(self, symbol, qty):
        return self.client.order_market_buy(
            symbol=symbol,
            quantity=qty
        )

    def market_sell(self, symbol, qty):
        return self.client.order_market_sell(
            symbol=symbol,
            quantity=qty
        )

    def balance(self, asset="USDT"):
        balances = self.client.get_asset_balance(asset)
        return float(balances["free"])