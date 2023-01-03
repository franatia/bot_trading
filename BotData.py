from binance import Client, AsyncClient, BinanceSocketManager
from ModelTools import ModelTools
from binance.enums import *


class BotData:
    def __init__(self, currency: str, start_day: str or int, end_day: str or int, interval, user_key: str,
                 secret_key: str, first_period_ema, second_period_ema):
        self.currency = currency
        self.start_day = start_day
        self.end_day = end_day
        self.interval = interval
        self.binance_client = Client(user_key, secret_key)

        self.client_socket: AsyncClient = None
        self.bm: BinanceSocketManager = None

        self.first_period_ema = first_period_ema
        self.second_period_ema = second_period_ema

        self.model_tools = ModelTools(self.currency, self.start_day, self.end_day, interval=interval,
                                      first_period_ema=first_period_ema, second_period_ema=second_period_ema)
        self.klines = self.model_tools.klines
        self.first_ema, self.second_ema = self.model_tools.first_ema, self.model_tools.second_ema
        self.rsi = self.model_tools.rsi
        self.dmi = self.model_tools.dmi
        self.dmi_markers = self.model_tools.momentums
        self.markers = self.model_tools.calculateSupportsAndResistors(self.model_tools.klines, 'CLOSE',
                                                                      downPercentage=.998, climbPercentage=1.002)

    def restart(self):
        self.model_tools = ModelTools(self.currency, self.start_day, self.end_day, interval=self.interval,
                                      first_period_ema=self.first_period_ema, second_period_ema=self.second_period_ema)
        self.klines = self.model_tools.klines
        self.first_ema, self.second_ema = self.model_tools.first_ema, self.model_tools.second_ema
        self.rsi = self.model_tools.rsi
        self.dmi = self.model_tools.dmi
        self.dmi_markers = self.model_tools.momentums
        self.markers = self.model_tools.calculateSupportsAndResistors(self.model_tools.klines, 'CLOSE',
                                                                      downPercentage=.998, climbPercentage=1.002)

    def restart_end_day(self):

        last_kline = self.binance_client.get_historical_klines(symbol=self.currency, interval=self.interval, start_str=self.klines[len(self.klines) - 1][0], end_str=self.end_day, klines_type=HistoricalKlinesType.FUTURES)
        last_kline = last_kline[len(last_kline) - 1]

        self.klines.append(last_kline)
        self.klines.remove(self.klines[0])

        self.model_tools.endPeriod = self.end_day
        self.model_tools.klines = self.klines
        self.model_tools.setTradeData()
        self.first_ema, self.second_ema = self.model_tools.first_ema, self.model_tools.second_ema
        self.rsi = self.model_tools.rsi
        self.dmi = self.model_tools.dmi
        self.dmi_markers = self.model_tools.momentums
        self.markers = self.model_tools.calculateSupportsAndResistors(self.model_tools.klines, 'CLOSE',
                                                                      downPercentage=.998, climbPercentage=1.002)

    def restart_ema(self, who):

        if who == 'FIRST':
            self.model_tools.firstPeriod = self.first_period_ema
            self.model_tools.setTradeData()
            self.first_ema = self.model_tools.first_ema

        elif who == 'SECOND':
            self.model_tools.secondPeriod = self.second_period_ema
            self.model_tools.setTradeData()
            self.second_ema = self.model_tools.second_ema

    def put_currency(self, c: str):
        self.currency = c
        self.restart()

    def put_start_day(self, sd: str or int):
        self.start_day = sd
        self.restart()

    def put_end_day(self, ed: str or int):
        self.end_day = ed
        self.restart_end_day()

    def put_interval(self, interval):
        self.interval = interval
        self.restart()

    def put_first_period(self, fp: int):
        self.first_period_ema = fp
        self.restart_ema('FIRST')

    def put_second_period(self, sp: int):
        self.second_period_ema = sp
        self.restart_ema('SECOND')
