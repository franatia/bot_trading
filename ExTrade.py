from binance import Client


class ExTrade:
    def __int__(self, user_key: str, secret_key: str):
        self.user_key = user_key
        self.secret_key = secret_key
        self.binance_client = Client(self.user_key, self.secret_key)
        self.order = None
        self.take_profit_order = None
        self.stop_loss_order = None

    def ex_futures_trade(self, tp, sl, side, positionSide, quantity, currency):
        self.order = self.binance_client.futures_create_order(
            symbol=currency,
            side=side,
            positionSide=positionSide,
            type='MARKET',
            quantity=quantity,
            timeInForce='GTC'
        )

        self.take_profit_order = self.binance_client.futures_create_order(
            symbol=currency,
            side='SELL',
            type='TAKE_PROFIT_MARKET',
            positionSide=positionSide,
            quantity=quantity,
            stopPrice=tp
        )

        self.stop_loss_order = self.binance_client.futures_create_order(
            symbol=currency,
            side='SELL',
            type='STOP_MARKET',
            positionSide=positionSide,
            quantity=quantity,
            stopPrice=sl
        )