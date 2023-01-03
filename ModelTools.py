import asyncio
import datetime
import time

import numpy as np
import pandas
from ta.momentum import rsi as _rsi
from ta.trend import sma_indicator as _sma_indicator

import requests

from binance import Client, ThreadedWebsocketManager
from binance.enums import HistoricalKlinesType
import websockets

api_key = 'dIXuGb6b1CFjGb6nqn7Vyav7cKm0JwVSv3al62rBruM82Xmsjq4t4tMcNbFoYFsr'
api_secret = 'aNPDlOhEzk9WLKaLxnkFOTQT6BQ4p7ttXDzSlWK25drrMFY2pWHXszNLtQmwvHSq'

client = Client(api_key, api_secret)

class ModelTools:

    def __init__(self, currency: str, startPeriod: str, endPeriod: str, interval, first_period_ema, second_period_ema):
        self.client = client
        self.currency = currency
        self.startPeriod = startPeriod
        self.endPeriod = endPeriod
        self.interval = interval

        self.klines = self.client.get_historical_klines(symbol=self.currency.upper(), interval=self.interval, start_str=self.startPeriod, end_str=self.endPeriod, klines_type=HistoricalKlinesType.FUTURES)
        self.currentPeriod = None
        self.patterns = None

        # EMA Values
        self.firstPeriod = first_period_ema
        self.secondPeriod = second_period_ema
        self.first_ema = self.getEMA(self.klines, self.firstPeriod)
        self.second_ema = self.getEMA(self.klines, self.secondPeriod)

        self.dmi = self.getDMI(self.klines, 14)
        self.dmiPeriod = None
        self.momentums = None

        self.sentiment = self.getSentiment()

        self.bb = None

        self.rsi = self.getRSI(self.klines)
        self.rsiCrosses = self.getRSICrosses(self.rsi)

        # Average volume amount
        # Cantidad de volumen promedio
        self.averageVolume = 0

        # Supports and resistors above the closing price of the candle
        # Soportes y resistencias por encima del precio de cierre de la vela
        self.markersEnd = self.calculateSupportsAndResistors(self.klines, 'ENDS')

        # Supports and resistors from the closing price of the candle
        # Soportes y resistencias desde el precio de cierre de la vela
        self.markersClose = self.calculateSupportsAndResistors(self.klines, 'CLOSE', True)

        # VolumeProfile
        self.volumeProfile = self.getVolumeProfile(self.klines)
        # EMA's crosses that set a new trend
        # Cruces de las EMA que marcan nueva tendencia
        self.emaCrosses = self.getEmaCrosses([self.firstPeriod, self.secondPeriod], [self.first_ema, self.second_ema])

        # Average trend duration from EMA's crosses
        # Duracion media de tendencia de los cruces de la EMA
        self.averageTrendDuration = self.getTrendDuration(self.emaCrosses)

        # Larger Support or resistency volume
        # Soporte o resistencia de mayor volumen
        # Current Price Mark
        # Marca de precio actual
        self.currentPriceMark = 0

        self.lastTrade = None

        # PricePrediction
        #self.newPricePrediction(self.klines)
        self.setTradeData()

    def add_kline(self, date_end: int):
        diff_date = self.endPeriod - self.startPeriod
        self.endPeriod = date_end
        self.startPeriod = date_end - diff_date
        self.klines = self.client.get_historical_klines(symbol=self.currency.upper(), interval=self.interval, start_str=self.startPeriod, end_str=self.endPeriod, klines_type=HistoricalKlinesType.FUTURES)
        self.setTradeData()

    def setTradeData(self):

        # EMA Values
        self.first_ema = self.getEMA(self.klines, self.firstPeriod)
        self.second_ema = self.getEMA(self.klines, self.secondPeriod)

        self.dmi = self.getDMI(self.klines, 14)

        self.bb = None

        self.sentiment = self.getSentiment()

        self.rsi = self.getRSI(self.klines)
        self.rsiCrosses = self.getRSICrosses(self.rsi)

        # Average volume amount
        # Cantidad de volumen promedio
        self.averageVolume = 0

        # Supports and resistors above the closing price of the candle
        # Soportes y resistencias por encima del precio de cierre de la vela
        self.markersEnd = self.calculateSupportsAndResistors(self.klines, 'ENDS')

        # Supports and resistors from the closing price of the candle
        # Soportes y resistencias desde el precio de cierre de la vela
        self.markersClose = self.calculateSupportsAndResistors(self.klines, 'CLOSE', True)

        # VolumeProfile
        self.volumeProfile = self.getVolumeProfile(self.klines)
        # EMA's crosses that set a new trend
        # Cruces de las EMA que marcan nueva tendencia
        self.emaCrosses = self.getEmaCrosses([self.firstPeriod, self.secondPeriod], [self.first_ema, self.second_ema])

        # Average trend duration from EMA's crosses
        # Duracion media de tendencia de los cruces de la EMA
        self.averageTrendDuration = self.getTrendDuration(self.emaCrosses)

        lastEmaCross, bfEmaCross = self.emaCrosses[len(self.emaCrosses) - 1], self.emaCrosses[len(self.emaCrosses) - 2]
        trendDirection = lastEmaCross['type']

        self.currentPeriod = self.getTrendData(bfEmaCross['data'][0]['date'], lastEmaCross['data'][0]['date'],
                                          self.klines[len(self.klines) - 1][6], trendDirection)
        self.dmiPeriod = self.getDMIPeriod(self.currentPeriod[0][6], self.currentPeriod[len(self.currentPeriod) - 1][6])
        self.momentums = self.getDMIMomentum(self.dmi)
        self.patterns = self.calculateSupportsAndResistors(self.klines, 'CLOSE', True)

    def someMatchPattern(self, date: int):

        value_return = None

        for i in self.patterns:
            if i['date'] == date:
                value_return = 1 if i['type'] == 'negative' else 2
                break
            else:
                value_return = 0

        return value_return

    def getSentiment(self):
        _d = datetime.datetime.now()
        _d_string = f'{_d.strftime("%d")}/{_d.strftime("%m")}/{_d.strftime("%Y")} 00:00:01'
        _d = datetime.datetime.strptime(_d_string, '%d/%m/%Y %H:%M:%S')
        _de = datetime.datetime.strptime('17/08/2017 00:00:10', '%d/%m/%Y %H:%M:%S')

        _d_ts = _d.timestamp()
        _de_ts = _de.timestamp()

        _diff = int((_d_ts - _de_ts) * 1000 / 86400000)

        _res = requests.get(f'https://api.alternative.me/fng/?limit={_diff}&format=json&date_format=us')

        _res = _res.json()['data']

        _res.reverse()

        for i in _res:
            _str = i['timestamp'].split('-')
            i['timestamp'] = int(datetime.datetime.strptime(f'{_str[1]}/{_str[0]}/{_str[2]} 20:59:59', '%d/%m/%Y %H:%M:%S').timestamp()*1000) + 999

        return _res

    def isAnyCandlePattern(self, date: int):

        bl = False
        i = None

        for item in self.patterns:
            if item['date'] == date:
                bl = True
                i = item
                break

        return bl, i

    @staticmethod
    def getTrendDuration(emaBreak: list):

        lastItem = None
        times = []
        value = 0

        for item in emaBreak:

            if lastItem is None:
                lastItem = item
                continue

            times.append(item['data'][0]['date'] - lastItem['data'][0]['date'])

            lastItem = item

        for item in times:

            value += item

            if times.index(item) == len(times) - 1:
                value = value / len(times)

        return value

    @staticmethod
    def getHistoricalMaxVolume(entry):
        max = []

        for item in entry:

            if len(max) == 0:
                max = item
            elif (float(max[5]) < float(item[5])) or (float(max[7]) < float(item[7])):
                max = item

    @staticmethod
    def getHistoricalMinPrice(entry):
        min = []

        for item in entry:

            if len(min) == 0:
                min = item
            elif float(min[3]) > float(item[3]):
                min = item

        return min

    @staticmethod
    def getHistoricalMinClosePrice(entry):
        min = []

        for item in entry:

            if len(min) == 0:
                min = item
            elif float(min[4]) > float(item[4]):
                min = item

        return min

    @staticmethod
    def getHistoricalMaxPrice(entry):
        max = []

        for item in entry:

            if len(max) == 0:
                max = item
            elif float(max[2]) < float(item[2]):
                max = item

    @staticmethod
    def getHistoricalMaxClosePrice(entry):
        max = []

        for item in entry:

            if len(max) == 0:
                max = item
            elif float(max[4]) < float(item[4]):
                max = item

        return max

    @staticmethod
    def getHistoricalAnyData(entry, type_data):
        data = []

        if type_data == 'MAX_VOLUME':

            for item in entry:

                if (len(data) == 0):
                    data = item
                elif (float(data[5]) < float(item[5])) or (float(data[7]) < float(item[7])):
                    data = item

        elif type_data == 'MIN_PRICE':

            for item in entry:

                if len(data) == 0:
                    data = item
                elif float(data[3]) > float(item[3]):
                    data = item

        elif type_data == 'MIN_CLOSE_PRICE':

            for item in entry:

                if len(data) == 0:
                    data = item
                elif float(data[4]) > float(item[4]):
                    data = item

        elif type_data == 'MAX_PRICE':

            for item in entry:

                if len(data) == 0:
                    data = item
                elif float(data[2]) < float(item[2]):
                    data = item

        elif type_data == 'MAX_CLOSE_PRICE':

            for item in entry:

                if (len(data) == 0):
                    data = item
                elif (float(data[4]) < float(item[4])):
                    data = item

        elif type_data == 'ALL':

            for item in entry:

                if (len(data) == 0):
                    data = {
                        "maxVolume": item,
                        "minPrice": item,
                        "minClosePrice": item,
                        "maxPrice": item,
                        "maxClosePrice": item
                    }
                    continue

                if (float(data["maxVolume"][5]) < float(item[5])) or (float(data["maxVolume"][7]) < float(item[7])):
                    data['maxVolume'] = item

                if float(data['minPrice'][3]) > float(item[3]):
                    data['minPrice'] = item

                if float(data['minClosePrice'][4]) > float(item[4]):
                    data['minClosePrice'] = item

                if float(data['maxPrice'][2]) < float(item[2]):
                    data['maxPrice'] = item

                if float(data['maxClosePrice'][4]) < float(item[4]):
                    data['maxClosePrice'] = item

    def getEMA(self, entry, period):
        periodTimes = []

        ema = []

        for item in entry:

            if len(periodTimes) < period:

                periodTimes.append(item)

                if len(periodTimes) == period:

                    if len(ema) == 0:

                        ema.append({
                            "value": self.calculateEMA(periodTimes, None),
                            "date": item[6]
                        })

                    else:

                        value = self.calculateEMA(periodTimes, ema[len(ema) - 1]['value'])
                        ema.append({
                            "value": value,
                            "date": periodTimes[len(periodTimes) - 1][6]
                        })

                    periodTimes.remove(periodTimes[0])

        return ema

    @staticmethod
    def calculateEMA(entry, beforeEma):
        ema = None

        if beforeEma is None:

            value = 0

            for item in entry:
                value += float(item[4])

            ema = value / len(entry)

        else:

            a = (2 / (len(entry) + 1))
            value = a * float(entry[len(entry) - 1][4]) + (1 - a) * beforeEma
            ema = value

        return ema

    @staticmethod
    def calculateSupportsAndResistors(entry: list, mode: str, pattern: bool = False, downPercentage: float = 0,
                                      climbPercentage: float = 0):
        values = []

        for item in entry:

            if mode == 'CLOSE':

                if len(values) == 0:
                    values.append({
                        'value': [float(item[4])],
                        'type': 'null',
                        'date': item[6],
                        'volume': [float(item[7])]
                    })

                    continue

                itemValue = float(item[4])
                valueToCompare = values[len(values) - 1]
                divider = valueToCompare['value'][0]

                res = itemValue / divider

                if res <= (downPercentage if bool(downPercentage) else 0.92) or (
                        1 >= res >= (downPercentage if bool(downPercentage) else 0.92)):

                    if valueToCompare['type'] == 'negative':

                        if not valueToCompare['ok']:
                            values.remove(valueToCompare)

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'positive' and (
                            downPercentage + .0005 if bool(downPercentage) else 0.96) >= res > (
                            downPercentage if bool(downPercentage) else 0.92) and not valueToCompare['ok']:

                        index = values.index(valueToCompare)
                        values.pop(index)

                        valueToCompare['ok'] = True

                        values.insert(index, valueToCompare)

                        if pattern:

                            if res <= 0.95:
                                values.append({
                                    'value': [itemValue],
                                    'type': 'negative',
                                    'date': item[6],
                                    'volume': [float(item[7])],
                                    'ok': False
                                })

                    elif valueToCompare['type'] == 'positive' and res <= (
                            downPercentage if bool(downPercentage) else 0.92):

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'null' and res <= (downPercentage if bool(downPercentage) else 0.92):

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                elif res >= (climbPercentage if bool(climbPercentage) else 1.08) or (
                        1 <= res <= (climbPercentage if bool(climbPercentage) else 1.08)):

                    if valueToCompare['type'] == 'positive':

                        if not valueToCompare['ok']:
                            values.remove(valueToCompare)

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'negative' and (
                            climbPercentage - .0005 if bool(climbPercentage) else 1.08) <= res < (
                            climbPercentage if bool(climbPercentage) else 1.08) and not valueToCompare['ok']:

                        index = values.index(valueToCompare)
                        values.pop(index)

                        valueToCompare['ok'] = True

                        values.insert(index, valueToCompare)

                        if pattern:

                            if res >= 1.05:
                                values.append({
                                    'value': [itemValue],
                                    'type': 'positive',
                                    'date': item[6],
                                    'volume': [float(item[7])],
                                    'ok': False
                                })

                    elif valueToCompare['type'] == 'negative' and res >= (
                            climbPercentage if bool(climbPercentage) else 1.08):

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'null' and res >= (
                            climbPercentage if bool(climbPercentage) else 1.08):

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

            if mode == 'ENDS':

                if len(values) == 0:
                    values.append({
                        'value': [float(item[4])],
                        'type': 'null',
                        'date': item[6],
                        'volume': [float(item[7])]
                    })

                    continue

                itemValue = float(item[4])
                valueToCompare = values[len(values) - 1]
                divider = valueToCompare['value'][0]

                res = itemValue / divider

                if res > 1:
                    itemValue = float(item[2])
                elif res < 1:
                    itemValue = float(item[3])

                res = itemValue / divider

                if res <= 0.92 or (1 >= res >= 0.92):

                    if valueToCompare['type'] == 'negative' and not valueToCompare['ok']:
                        values.remove(valueToCompare)

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'positive' and 0.96 >= res > 0.92 and not valueToCompare['ok']:

                        index = values.index(valueToCompare)
                        values.pop(index)

                        valueToCompare['ok'] = True

                        values.insert(index, valueToCompare)

                    elif valueToCompare['type'] == 'positive' and res <= 0.92:

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'null':

                        values.append({
                            'value': [itemValue],
                            'type': 'negative',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                elif res >= 1.08 or (1 <= res <= 1.08):

                    if valueToCompare['type'] == 'positive' and not valueToCompare['ok']:
                        values.remove(valueToCompare)

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'negative' and 1.04 <= res < 1.08 and not valueToCompare['ok']:

                        index = values.index(valueToCompare)
                        values.pop(index)

                        valueToCompare['ok'] = True

                        values.insert(index, valueToCompare)

                    elif valueToCompare['type'] == 'negative' and res >= 1.08:

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

                    elif valueToCompare['type'] == 'null':

                        values.append({
                            'value': [itemValue],
                            'type': 'positive',
                            'date': item[6],
                            'volume': [float(item[7])],
                            'ok': False
                        })

        return values

    def getVolumeProfile(self, entry):
        average = self.calculateVolumeAverage(entry)
        self.averageVolume = average

        values = []

        for item in entry:

            volume = float(item[7])

            if volume > average:

                openCandle = float(item[2])
                closeCandle = float(item[4])
                resPrice = openCandle / closeCandle

                if resPrice > 1:

                    values.append({
                        'value': [(closeCandle + float(item[3])) / 2],
                        'date': item[6],
                        'volume': float(item[7])
                    })

                elif resPrice < 1:

                    values.append({
                        'value': [(closeCandle + float(item[2])) / 2],
                        'date': item[6],
                        'volume': float(item[7])
                    })

                else:

                    values.append({
                        'value': [(closeCandle + openCandle + float(item[2]) + float(item[3])) / 4],
                        'date': item[6],
                        'volume': float(item[7])
                    })

        value = None

        for item in values:

            if value == None:
                value = item

                values.remove(value)

                continue

            price = item['value'][0]
            volume = item['volume']
            valuePrice = value['value'][0]
            valueVolume = value['volume']

            resPrice = price / valuePrice
            resVolume = volume / valueVolume

            if 1.05 >= resPrice >= 0.95 and 1.05 >= resVolume >= 0.95:

                if len(value['value']) > 1:

                    a = value['value'][0] / value['value'][1]

                    if a > 1 and (price / value['value'][1]) > 1:

                        value['value'].remove(value['value'][1])
                        value['value'].append(price)

                    elif a < 1 and (price / value['value'][0]) < 1:
                        value['value'].remove(value['value'][0])
                        value['value'].insert(0, price)

                else:

                    value['value'].append(price)

                value['volume'] = (valueVolume + volume) / 2

            values.append(value)

            value = item

            values.remove(item)

        return self.sortValuesVolumeProfile(values)

    @staticmethod
    def calculateVolumeAverage(entry):
        value = 0
        amount = 0

        for item in entry:
            value += float(item[7])
            amount += 1

        value = value / amount
        amount = 0
        for item in entry:

            if value < float(item[7]):
                value += float(item[7])
                amount += 1

        value = value / amount

        return value

    @staticmethod
    def sortValuesVolumeProfile(entry):
        values = []

        for item in entry:

            if len(values) == 0:
                values.append(item)

                continue

            for value in values:

                if value['volume'] < item['volume']:
                    values.insert(values.index(value), item)

                    break

                if values.index(value) == len(values) - 1:
                    values.append(item)

        return values

    def newPricePrediction(self, entry: list):

        # Primero obtenemos los valores de la tendencia actual
        # First we get the current tendency's values

        lastEmaCross, bfEmaCross = self.emaCrosses[len(self.emaCrosses) - 1], self.emaCrosses[len(self.emaCrosses) - 2]
        trendDirection = lastEmaCross['type']

        currentPeriod = self.getTrendData(bfEmaCross['data'][0]['date'], lastEmaCross['data'][0]['date'],
                                          entry[len(entry) - 1][6], trendDirection)
        self.currentPeriod = currentPeriod

        # Determinate the trend direction

        # Then we analyze the state of the DMI
        dmiPeriod = self.getDMIPeriod(currentPeriod[0][6], currentPeriod[len(currentPeriod) - 1][6])
        self.dmiPeriod = dmiPeriod

        status, momentums, adxPeaks, peaksPosDI, peaksNegDI = self.getDMIPattern(dmiPeriod, trendDirection)

        mayorAdxPeak = None

        for item in adxPeaks:

            if mayorAdxPeak is None:
                mayorAdxPeak = item
                continue

            if mayorAdxPeak['value'] < item['value']:
                mayorAdxPeak = item

        # Then we detect in where part we are of the trend

        # 1. Detect the largest volume candle, and verified if match with the candle from day when higher DMIs points
        # 1. a) If don't match, so get the candle with downer minimum. Anyway conserve the DMIs points mark
        # 2. Corroborate if the support marked by the minimum candle has already been closed
        # 2. a) If don't closed it, calculate what is the Liquidates percentage
        # 3. Analysed the DMIs pattern:
        # If from the DMIs points mark, the DMIs points decreased; and after that, the ADX touched ceiling and descended
        # *Consolidation*
        # *Trend exhaustion*
        # (BASED ON THE PREVIOUS ARTICLE) In the moment where the ADX touched ceiling is when kickback happens
        # 4. If the price doesn't hit the support marked by the largest volume candle. We wait will happens that,
        # and parallel corroborate if the ADX decreased, and -DI, because we will buy in this price support
        # 4. a) If the price hit the price support, or hit before the analysis. We will buy if the price doesn´t cross
        # the EMA99, or doesn't exceed it by 10%/15%, and the ADX doesn't exceed the DIs values, or doesn't touched ceiling

        lastDay = currentPeriod[len(currentPeriod) - 1]
        lastEma50 = self.ema50[len(self.ema50) - 1]
        lastEma99 = self.ema99[len(self.ema99) - 1]
        lastDMI = self.dmi[len(self.dmi) - 1]

        candlePattern = self.calculateSupportsAndResistors(currentPeriod, 'CLOSE', True)
        self.patterns = candlePattern
        lastCandlePattern = candlePattern[len(candlePattern) - 1]
        lastNegCandlePattern = None
        lastPosCandlePattern = None
        for item in candlePattern:
            if item['type'] == 'positive':
                lastPosCandlePattern = item
            elif item['type'] == 'negative':
                lastNegCandlePattern = item

        dataReturn = {}

        lastMomentum = momentums[len(momentums) - 1]
        lastNegMomentum = None
        lastPosMomentum = None
        for item in momentums:
            if not bool(item['DI']['type']):
                lastNegMomentum = item
            elif bool(item['DI']['type']):
                lastPosMomentum = item

        # If the trend direction is bear
        if not bool(trendDirection):

            largerVolumeCandle = self.getCandleByDate(lastNegMomentum['DI']['date'], currentPeriod)
            lvc = self.getLargerVolumeCandle(currentPeriod, lastNegMomentum['DI']['date'])
            rsiPeaks = self.getRSIPeaks(self.rsi, 5)
            lastRSIPeak, lastPosRSIPeak, lastNegRSIPeak = self.getRSIPeaksRequired(rsiPeaks)

            if float(lvc[3]) < float(lvc[3]):
                largerVolumeCandle = lvc

            # Principal support
            sp = 0
            sc = 0
            if not (lastNegMomentum['ADX'] is None) if not bool(trendDirection) else not (
                    lastPosMomentum['ADX'] is None):
                sp = self.getBBSupport(
                    self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection), lastNegMomentum))
                sc = self.getMajorSupportCandle(currentPeriod, dmiPeriod, bool(trendDirection), lastNegMomentum)
            elif lastNegMomentum['ADX'] is None and momentums[momentums.index(lastNegMomentum) - 1]['DI']['type'] == 0:
                sp = self.getBBSupport(self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection),
                                                                momentums[momentums.index(lastNegMomentum) - 1]))
                sc = self.getMajorSupportCandle(currentPeriod, dmiPeriod, bool(trendDirection),
                                                momentums[momentums.index(lastNegMomentum) - 1])

            primaryCandle = None

            if sc != largerVolumeCandle:
                if float(largerVolumeCandle[3]) < float(sc[3]):
                    primaryCandle = largerVolumeCandle
                else:
                    primaryCandle = sc
            else:
                primaryCandle = largerVolumeCandle

            if status == '012':

                if lastCandlePattern['type'] == 'positive':
                    if lastMomentum['ADX'] is None:
                        if dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] == lastMomentum['DI']['value'] and float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 0.99:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        elif dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] >= 33 and float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 0.99 and self.getCandleType(lastDay):
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        elif not self.getCandleType(lastDay) and lastCandlePattern['value'][0] > lastEma99['value'] > candlePattern[len(candlePattern) - 2]['value'][0] and lastCandlePattern['date'] > lastMomentum['DI']['date'] > candlePattern[len(candlePattern) - 2]['date']:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        elif float(lastDay[4]) > float(self.getCandleByDate(lastMomentum['DI']['date'], currentPeriod)[4]) and dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] < lastMomentum['DI']['value']:
                            bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                            if self.getCandleType(lastDay) and float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 1:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            elif lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1] >= 1 and bl:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                    elif not(lastMomentum['ADX'] is None):
                        if float(lastDay[4]) < lastCandlePattern['value'][0] and lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[0] >= 1:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        elif float(lastDay[4]) < lastCandlePattern['value'][0] and lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[0] < 1:
                            if 1.03 >= float(lastDay[4]) / self.bb[1][len(self.klines) - 1] >= 0.98:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])

                elif lastCandlePattern['type'] == 'negative':
                    if dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] >= 25:
                        if 1.02 >= lastCandlePattern['value'][0] / lastEma99['value'] >= 0.98 or 1.02 >= \
                                lastCandlePattern['value'][0] / lastEma50['value'] >= 0.98 or 1.02 >= \
                                lastCandlePattern['value'][0] / self.bb[1][len(self.klines) - 1] >= 0.98:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
            elif status == '011':
                if lastCandlePattern['type'] == 'positive':

                    guideCandle = self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection),
                                                           lastNegMomentum)

                    if float(guideCandle[4]) < lastCandlePattern['value'][0] and lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1] >= 0.98:

                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])

                    else:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])

                elif lastCandlePattern['type'] == 'negative':
                    isHit = None
                    if lastMomentum['DI']['type'] == 0 and momentums[momentums.index(lastMomentum) - 1]['DI']['type'] == 0:
                        guideCandle = self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection), momentums[momentums.index(lastMomentum) - 1])
                        for item in currentPeriod:

                            if float(item[4]) < float(guideCandle[3]) and candlePattern[candlePattern.index(lastCandlePattern) - 1]['date'] <= item[6]:
                                isHit = True
                                break
                            else:
                                isHit = False

                    if not (isHit is None):
                        if isHit and dmiPeriod[len(dmiPeriod) - 1]['ADX'] / lastMomentum['DI']['value'] >= 0.95:

                            msp = self.getMajorSupportCandle(currentPeriod, dmiPeriod, bool(trendDirection),
                                                             lastMomentum)

                            if not (msp is None) and msp == lastDay:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            elif float(lastDay[4]) / self.bb[2][len(self.klines) - 1] < 1 and float(lastDay[4]) / sp < 1:
                                dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'adx', {'a': 0}, '5%', lastDay[6])

                        elif isHit and dmiPeriod[len(dmiPeriod) - 1]['ADX'] / lastMomentum['DI']['value'] < 0.95:
                            if dmiPeriod[len(dmiPeriod) - 1]['DI']['negative'] >= 35:
                                dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                            elif bool(lastRSIPeak['type']) and lastRSIPeak['rsi'] > lastRSIPeak['ma']:
                                if lastRSIPeak['rsi'] / 50 >= 0.920:
                                    dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                                else:
                                    if lastNegCandlePattern['date'] <= lastMomentum['DI']['date'] > candlePattern[candlePattern.index(lastNegCandlePattern) - 1]['date']:
                                        dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 1}, '5%', lastDay[6])
                                    else:
                                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])

                        elif not isHit:
                            sp = self.getBBSupport(self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection), momentums[momentums.index(lastMomentum) - 1]))
                            dataReturn = self.makeDataReturn('BUY', 'price', {'a': sp}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
            elif status == '013' or status == '021':
                if lastCandlePattern['type'] == 'positive':
                    if lastCandlePattern['value'][0] > sp:
                        if 1.03 >= lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[1] >= 0.98:
                            dataReturn = self.makeDataReturn('BUY', 'price', {'a': sp}, '5%', lastDay[6])
                        elif lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[0] >= 0.98:
                            bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                            if bl:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])

                elif lastCandlePattern['type'] == 'negative':

                    if lastDay == sc:
                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                    elif float(lastDay[4]) < sp:
                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                    else:
                        if float(lastCandlePattern['value'][0]) / sp <= 1.03 and self.getCandleType(lastDay):
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'price', {'a': sp}, '5%', lastDay[6])
            elif status == '041':
                if lastCandlePattern['type'] == 'negative':

                    if lastCandlePattern['value'][0] / sp <= 1.02:

                        if dmiPeriod[len(dmiPeriod) - 1]['DI']['negative'] < peaksNegDI[len(peaksNegDI) - 1]['value']:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                    elif 1.02 >= lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[1] > 0.98:
                        bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                        if bl:
                            dataReturn = self.makeDataReturn('BUY', 'now',  {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji','b': '>'}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
            elif status == '071':
                if lastCandlePattern['type'] == 'negative':
                    if lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[2] <= 1.02:
                        if lastCandlePattern['value'][0] / sp <= 1.02 and float(lastDay[4]) / lastCandlePattern['value'][0] <= 1.03:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 1}, lastDay[6])
                    elif 0.97 <= lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[1] <= 1.02:
                        bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                        if bl:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': '>', 'b': 'doji'}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'candle', {'a': '>', 'b': 'doji'}, '5%', lastDay[6])
            elif status == '051':

                if dmiPeriod[len(dmiPeriod) - 1]['ADX'] > 35 and not (lastMomentum['ADX'] is None):
                    if lastCandlePattern['type'] == 'positive' and self.bb[1][len(self.klines) - 1] > lastCandlePattern['value'][0] and sp < float(lastDay[4]):
                        dataReturn['type'] = 'BUY'
                        dataReturn['VT'] = 'price'
                        dataReturn['move'] = {
                            'a': sp
                        }
                        dataReturn['TP'] = '5%'
                        dataReturn['date'] = lastDay[6]
                    elif lastCandlePattern['type'] == 'negative' and sp > lastCandlePattern['value'][0] and float(lastDay[4]) / self.bb[1][len(self.klines) - 1] < 1.03:
                        dataReturn['type'] = 'BUY'
                        dataReturn['VT'] = 'now'
                        dataReturn['TP'] = '5%'
                        dataReturn['date'] = lastDay[6]
                    elif lastCandlePattern['type'] == 'positive' and self.bb[1][len(self.klines) - 1] < lastCandlePattern['value'][0] < self.bb[0][len(self.klines) - 1]:
                        dataReturn['type'] = 'SELL'
                        dataReturn['VT'] = 'bb'
                        dataReturn['move'] = {
                            'a': 0,
                            'b': 1
                        }
                        dataReturn['TP'] = '5%'
                        dataReturn['date'] = lastDay[6]
                elif dmiPeriod[len(dmiPeriod) - 1]['DI']['negative'] < dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] < dmiPeriod[len(dmiPeriod) - 1]['ADX']:
                    if self.bb[2][len(self.klines) - 1] / sp < 1.02 and float(lastDay[4]) > self.bb[1][len(self.klines) - 1]:
                        if lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1] < 0.97:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': sp
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        elif 0.99 >= lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1] >= 0.97:
                            dataReturn['type'] = 'SELL'
                            dataReturn['VT'] = 'bb'
                            dataReturn['move'] = {
                                'a': 0
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        elif 0.99 < lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1]:
                            dataReturn['type'] = 'SELL'
                            dataReturn['VT'] = 'bb'
                            dataReturn['move'] = {
                                'a': 0
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                else:
                    if lastCandlePattern['type'] == 'negative' and 1.03 > float(lastDay[4]) / self.bb[1][len(self.klines) - 1] > 0.97 and lastPosCandlePattern['value'][0] / self.getBBbyDate(lastPosCandlePattern['date'])[1] > 1.05:

                        if dmiPeriod[len(dmiPeriod) - 1]['DI']['negative'] > dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] and dmiPeriod[len(dmiPeriod) - 1]['ADX'] > 30:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'now'
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        else:
                            print('check status 051')
                    elif lastCandlePattern['type'] == 'negative' and dmiPeriod[len(dmiPeriod) - 1]['ADX'] <= 30 >= dmiPeriod[len(dmiPeriod) - 1]['DI']['negative']:

                        if self.bb[1][len(self.klines) - 1] > float(lastDay[4]):
                            if float(lastDay[4]) / sp > 0.98:
                                dataReturn['type'] = 'BUY'
                                dataReturn['VT'] = 'price'
                                dataReturn['move'] = {
                                    'a': sp
                                }
                                dataReturn['TP'] = '5%'
                                dataReturn['date'] = lastDay[6]
                            else:
                                if float(largerVolumeCandle[3]) > float(lastDay[4]):
                                    dataReturn['type'] = 'BUY'
                                    dataReturn['VT'] = 'now'
                                    dataReturn['TP'] = '5%'
                                    dataReturn['date'] = lastDay[6]
                                else:
                                    dataReturn['type'] = 'BUY'
                                    dataReturn['VT'] = 'price'
                                    dataReturn['move'] = {
                                        'a': float(largerVolumeCandle[3])
                                    }
                                    dataReturn['TP'] = '5%'
                                    dataReturn['date'] = lastDay[6]
                        else:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'candle'
                            dataReturn['move'] = {
                                'a': '>'
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]

                    else:
                        print('check status 051')
            elif status == '053':

                if lastCandlePattern['type'] == 'negative':
                    if not self.checkTheEvent(False, currentPeriod, primaryCandle) and self.bb[1][len(self.klines) - 1] / float(lastDay[4]) <= 1.02 and not lastPosCandlePattern['value'][0] / self.getBBbyDate(lastPosCandlePattern['date'])[1] > 1.05:
                        if sp > lastCandlePattern['value'][0]:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': float(largerVolumeCandle[3])
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        else:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': sp
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                    elif 0.96 <= lastCandlePattern['value'][0] / sp <= 1.04:

                        if float(lastDay[4]) > lastCandlePattern['value'][0] and float(lastDay[4]) / self.bb[len(self.klines) - 1][1] > 0.99:
                            dataReturn['type'] = 'SELL'
                            dataReturn['VT'] = 'bb'
                            dataReturn['move'] = {
                                'a': 0
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        else:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': sp
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                    else:
                        dataReturn['type'] = 'BUY'
                        dataReturn['VT'] = 'candle'
                        dataReturn['move'] = {
                            'a': '>'
                        }
                        dataReturn['TP'] = '5%'
                        dataReturn['date'] = lastDay[6]
            elif status == '044':

                isDoji = self.isDojiCandle(lastDay)

                if lastCandlePattern['type'] == 'negative':
                    if lastPosCandlePattern['value'][0] / self.getBBbyDate(lastPosCandlePattern['date'])[0] < 0.99:
                        dataReturn['type'] = 'BUY'
                        dataReturn['VT'] = 'price'
                        dataReturn['TP'] = '5%'
                        dataReturn['move'] = {
                            'a': sp
                        }
                        dataReturn['date'] = lastDay[6]
                    else:
                        if 0.98 <= float(lastDay[4]) / self.bb[1][len(self.klines) - 1] <= 1.02:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': self.bb[1][len(self.klines) - 1]
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        elif float(lastDay[4]) / self.bb[1][len(self.klines) - 1] < 0.98:
                            dataReturn['type'] = 'BUY'
                            dataReturn['VT'] = 'price'
                            dataReturn['move'] = {
                                'a': sp
                            }
                            dataReturn['TP'] = '5%'
                            dataReturn['date'] = lastDay[6]
                        elif float(lastDay[4]) / self.bb[1][len(self.klines) - 1] > 1.02:
                            if 0.98 <= lastNegCandlePattern['value'][0] / self.getBBbyDate(lastNegCandlePattern['date'])[1] <= 1.02:
                                if isDoji and self.getDojiType(lastDay):
                                    dataReturn['type'] = 'SELL'
                                    dataReturn['VT'] = 'price'
                                    dataReturn['move'] = {
                                        'a': float(lastDay[2])
                                    }
                                    dataReturn['TP'] = '5%'
                                    dataReturn['date'] = lastDay[6]
                                elif isDoji:
                                    dataReturn['type'] = 'SELL'
                                    dataReturn['VT'] = 'now'
                                    dataReturn['TP'] = '5%'
                                    dataReturn['date'] = lastDay[6]
                                else:
                                    guidePattern = None
                                    if lastCandlePattern['type'] == 'negative':
                                        guidePattern = lastPosCandlePattern
                                    else:
                                        candlePattern.reverse()
                                        for item in candlePattern:
                                            if candlePattern.index(item) > candlePattern.index(lastCandlePattern) and item['type'] == 'positive':
                                                guidePattern = item
                                                break
                                    if guidePattern['value'][0] / self.getBBbyDate(guidePattern['date'])[0] > 1:
                                        dataReturn['type'] = 'SELL'
                                        dataReturn['VT'] = 'price'
                                        dataReturn['move'] = {
                                            'a': guidePattern['value'][0]
                                        }
                                        dataReturn['TP'] = '5%'
                                        dataReturn['date'] = lastDay[6]
                                    else:
                                        dataReturn['type'] = 'SELL'
                                        dataReturn['VT'] = 'bb'
                                        dataReturn['move'] = {
                                            'a': 0
                                        }
                                        dataReturn['TP'] = '5%'
                                        dataReturn['date'] = lastDay[6]
                elif lastCandlePattern['type'] == 'positive':
                    if lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[0] >= 0.97 or float(self.getCandleByDate(lastCandlePattern['date'], currentPeriod)[2]) / self.getBBbyDate(lastCandlePattern['date'])[0] >= 0.98:
                        dataReturn = self.makeDataReturn('SELL', 'candle', {'a': 'doji', 'b': '<'}, '5%', lastDay[6])
                    else:
                        if 0.98 <= float(self.getCandleByDate(lastCandlePattern['date'], currentPeriod)[4]) / self.getBBbyDate(lastCandlePattern['date'])[1] <= 1.02:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji', 'b': '<'}, '5%', lastDay[6])
                        elif float(lastDay[2]) / self.bb[1][len(self.klines) - 1] < 0.98:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji', 'b': '<'}, '5%', lastDay[6])
                            if 0.98 <= lastPosCandlePattern['value'][0] / self.getBBbyDate(lastPosCandlePattern['date'])[1] <= 1.02:
                                if isDoji and self.getDojiType(lastDay):
                                    dataReturn = self.makeDataReturn('SELL', 'price', {
                                        'a': float(lastDay[2])
                                    }, '5%', lastDay[6])
                                elif isDoji:
                                    dataReturn = self.makeDataReturn('SELL', 'now', '5%', lastDay[6])
                                else:
                                    dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji', 'b': '<'}, '5%',
                                                                     lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji', 'b': '<'}, '5%', lastDay[6])
            elif status == '043':
                bl, candle = self.hasAnyDojiCandle(currentPeriod,lastCandlePattern['date'], lastCandlePattern)
                if lastCandlePattern['type'] == 'negative':
                    if bl and (1.02 >= float(lastDay[4]) / self.bb[1][len(self.klines) - 1] >= 0.97 or 1.01 >= float(lastDay[3]) / self.bb[2][len(self.klines) - 1] or 1 >= float(lastDay[3]) / sp):
                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                    else:
                        if lastPosCandlePattern['value'][0] / self.getBBbyDate(lastPosCandlePattern['date'])[0] >= 0.980:
                            if 1.030 >= lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[1] >= 0.970 and \
                                1.00 >= lastNegRSIPeak['rsi'] / 50 >= 0.920:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            elif (lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[1] <= 0.970 or \
                                    lastNegRSIPeak['rsi'] / 50 <= 0.920) and lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[2] > 1.040:
                                dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                            elif lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[2] <= 1.030 \
                                    and (1.00 >= lastNegRSIPeak['rsi'] / 50 >= 0.920 or 1.050 >= lastNegRSIPeak['rsi'] / 30):
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji', 'b': '>'}, '5%', lastDay[6])

                        else:
                            for item in candlePattern:
                                value = item['value'][0]
                                if lastMomentum['DI']['date'] < item['date'] < lastDay[6]:
                                    if item['type'] == 'positive':
                                        if 1.02 >= float(lastDay[4]) / value >= 0.98:
                                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                        elif 1.02 >= float(lastDay[3]) / value:
                                            if not self.getDojiType(lastDay):
                                                dataReturn = self.makeDataReturn('BUY', 'price',
                                                                                 {'a': float(lastDay[3])},
                                                                                 '5%',
                                                                                 lastDay[6])
                                            else:
                                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                    else:
                                        if 1.02 >= float(lastDay[4]) / value >= 0.98:
                                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                        elif 1.02 >= float(lastDay[3]) / value:
                                            if not self.getDojiType(lastDay):
                                                dataReturn = self.makeDataReturn('BUY', 'price',
                                                                                 {'a': float(lastDay[3])},
                                                                                 '5%',
                                                                                 lastDay[6])
                                            else:
                                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])

            elif status == '042':
                isDoji = self.isDojiCandle(lastDay)
                if lastCandlePattern['type'] == 'positive':
                    if not isDoji:
                        bl, candle = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                        if bl:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'candle', {'a': 'doji', 'b': '<'}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
            elif status == '031':
                if lastCandlePattern['type'] == 'negative':
                    if dmiPeriod[len(dmiPeriod) - 1]['DI']['negative'] > dmiPeriod[len(dmiPeriod) - 1]['ADX'] >= 22:
                        if 1.02 >= float(lastDay[4]) / self.bb[2][len(self.klines) - 1] and 1.02 >= float(lastDay[4]) / sp:
                            dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                        elif 1.02 < float(lastDay[4]) / sp:
                            dataReturn = self.makeDataReturn('BUY', 'price', {'a': sp}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
            else:
                print(status)
        elif bool(trendDirection):

            rsiPeaks = self.getRSIPeaks(self.rsi, 8)

            largerVolumeCandle = self.getCandleByDate(lastMomentum['DI']['date'], currentPeriod)
            lvc = self.getLargerVolumeCandle(currentPeriod, lastMomentum['DI']['date'])

            if float(lvc[3]) < float(lvc[3]):
                largerVolumeCandle = lvc

            # Principal support
            sc = self.getMajorSupportCandle(currentPeriod, dmiPeriod, bool(trendDirection), lastPosMomentum)

            primaryCandle = self.getHistoricalMaxClosePrice(currentPeriod)

            if status == '011':
                sp = self.getBBSupport(
                    self.getGuideCandleForBB(currentPeriod, dmiPeriod, bool(trendDirection), lastMomentum))
                if lastCandlePattern['type'] == 'negative':
                    if lastMomentum['DI']['date'] == lastDay[6]:
                        dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                    else:
                        if sp == 0:
                            dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                        elif float(lastDay[4]) == sp or float(lastDay[4]) < sp or 1.02 >= lastCandlePattern['value'][0] / sp:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        elif 1.03 >= float(lastDay[4]) / self.bb[1][len(self.klines) - 1] >= 0.97:
                            dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0, 'b': 1}, '5%', lastDay[6])
                        elif float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 1.02:
                            isDoji = self.isDojiCandle(lastDay)
                            if isDoji:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                elif lastCandlePattern['type'] == 'positive':
                    if sp == 0:
                        dataReturn = self.makeDataReturn('BUY', 'di', {'a': 0}, '5%', lastDay[6])
                    elif 1.03 >= lastCandlePattern['value'][0] / self.bb[1][len(self.klines) - 1] or 0.97 <= lastCandlePattern['value'][0] / self.bb[0][len(self.klines) - 1]:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('BUY', 'price', {'a': 0}, '5%', lastDay[6])
            elif status == '012':
                if lastCandlePattern['type'] == 'positive':
                    if lastMomentum['DI']['date'] == dmiPeriod[len(dmiPeriod) - 1]['date']:
                        if dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] < dmiPeriod[len(dmiPeriod) - 1]['ADX'] and float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 0.98 and self.rsi[len(self.rsi) - 1]['rsi'] >= 70:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        elif dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] < dmiPeriod[len(dmiPeriod) - 1]['ADX']:
                            dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                        elif dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] >= dmiPeriod[len(dmiPeriod) - 1]['ADX']:
                            dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                    else:
                        if not bool(peaksPosDI[len(peaksPosDI) - 1]['type']):
                            if bool(peaksPosDI[len(peaksPosDI) - 2]['type']) and bool(peaksPosDI[len(peaksPosDI) - 2]['value'] >= self.getDMIDataByDate(dmiPeriod, peaksPosDI[len(peaksPosDI) - 2])['date'])['ADX']:
                                if float(lastDay[4]) / self.bb[0][len(self.klines)] < 0.97:
                                    dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                else:
                                    dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                            else:
                                    dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                        else:
                            if peaksPosDI[len(peaksPosDI) - 1]['value'] >= 35 and float(lastDay[4]) / self.bb[0][len(self.klines) - 1] >= 0.98 and self.rsi[len(self.rsi) - 1]['rsi'] >= 70:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
            elif status == '014':
                ap, _, _ = self.getDMIPeaks(dmiPeriod, 1)

                if lastCandlePattern['type'] == 'positive':
                    if 1.02 >= ap[len(ap) - 1]['value'] / ap[len(ap) - 3]['value'] >= 0.98:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    elif bool(momentums[momentums.index(lastMomentum) - 1]['DI']['type']):
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                elif lastCandlePattern['type'] == 'negative':
                    dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
            elif status == '042' or status == '032':
                if lastCandlePattern['type'] == 'positive':
                    if peaksPosDI[len(peaksPosDI) - 1]['value'] == dmiPeriod[len(dmiPeriod) - 1]['DI']['positive']:
                        patternCandle = self.getCandleByDate(lastCandlePattern['date'], currentPeriod)
                        patternBB = self.getBBbyDate(lastCandlePattern['date'])
                        if self.rsi[len(self.rsi) - 1]['rsi'] / 70 >= 0.97 or (bool(rsiPeaks[len(rsiPeaks) - 1]['type']) and float(patternCandle[4]) / patternBB[0] >= 0.97):
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                    elif dmiPeriod[len(dmiPeriod) - 1]['DI']['positive'] / peaksPosDI[len(peaksPosDI) - 1]['value'] <= 0.9:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
            elif status == '022':
                if lastCandlePattern['type'] == 'negative':
                    if self.rsi[len(self.rsi) - 1]['rsi'] / self.rsi[len(self.rsi) - 1]['ma'] <= 0.9:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                elif lastCandlePattern['type'] == 'positive':
                    isDeplete = self.checkRSIDepletion(
                        rsiPeaks,
                        (self.rsiCrosses[len(self.rsiCrosses) - 1] if self.rsiCrosses[len(self.rsiCrosses) - 1]['type'] == 1 else self.rsiCrosses[len(self.rsiCrosses) - 2]),
                        (rsiPeaks[len(rsiPeaks) - 1] if rsiPeaks[len(rsiPeaks) - 1]['type'] == 1 else rsiPeaks[len(rsiPeaks) - 2])
                    )
                    if isDeplete:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
            elif status == '072':
                if lastCandlePattern['type'] == 'positive':
                    if 1.02 >= lastCandlePattern['value'][0] / float(self.getHistoricalMaxClosePrice(currentPeriod)[4]) >= 0.98:
                        if 1.02 >= rsiPeaks[len(rsiPeaks) - 1]['rsi'] / rsiPeaks[len(rsiPeaks) - 1]['ma'] and peaksPosDI[len(peaksPosDI) - 1]['value'] < lastMomentum['DI']['value']:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        elif peaksPosDI[len(peaksPosDI) - 1]['value'] < lastMomentum['DI']['value']:
                            if rsiPeaks[len(rsiPeaks) - 1]['rsi'] < 70 and bool(rsiPeaks[len(rsiPeaks) - 1]['type']):
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                isDeplete = self.checkRSIDepletion(
                                    rsiPeaks,
                                    (self.rsiCrosses[len(self.rsiCrosses) - 1] if
                                     self.rsiCrosses[len(self.rsiCrosses) - 1]['type'] == 1 else self.rsiCrosses[
                                        len(self.rsiCrosses) - 2]),
                                    (rsiPeaks[len(rsiPeaks) - 1] if rsiPeaks[len(rsiPeaks) - 1]['type'] == 1 else
                                     rsiPeaks[len(rsiPeaks) - 2])
                                )
                                if isDeplete or not bool(self.rsiCrosses[len(self.rsiCrosses) - 1]['type']):
                                    dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                                else:
                                    dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                    else:
                        if rsiPeaks[len(rsiPeaks) - 1]['rsi'] < 70 and bool(rsiPeaks[len(rsiPeaks) - 1]['type']):
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            isDeplete = self.checkRSIDepletion(
                                rsiPeaks,
                                (self.rsiCrosses[len(self.rsiCrosses) - 1] if
                                 self.rsiCrosses[len(self.rsiCrosses) - 1]['type'] == 1 else self.rsiCrosses[
                                    len(self.rsiCrosses) - 2]),
                                (rsiPeaks[len(rsiPeaks) - 1] if rsiPeaks[len(rsiPeaks) - 1]['type'] == 1 else
                                 rsiPeaks[len(rsiPeaks) - 2])
                            )
                            if isDeplete or not bool(self.rsiCrosses[len(self.rsiCrosses) - 1]['type']):
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
            elif status == '052':
                if lastCandlePattern['type'] == 'positive':
                    if candlePattern[len(candlePattern) - 3]['value'][0] == float(self.getHistoricalMaxClosePrice(currentPeriod)[4]):
                        isCanceledPrice = self.isCanceledPrice(candlePattern, self.getMaxPattern(candlePattern))
                        if not isCanceledPrice:
                            isExhaust = self.detectBearishExhaustion(currentPeriod, candlePattern[len(candlePattern) - 2]['date'])
                            if isExhaust:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        if lastCandlePattern['value'][0] / self.getBBbyDate(lastCandlePattern['date'])[0] > 0.98:
                            bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                            if bl:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'candle', {'a': '<'}, '5%', lastDay[6])
                elif lastCandlePattern['type'] == 'negative':
                    patternBB = self.getBBbyDate(lastCandlePattern['date'])
                    if bool(peaksPosDI[len(peaksPosDI) - 1]['type']) and rsiPeaks[len(rsiPeaks) - 1]['rsi'] > 50:
                        dataReturn = self.makeDataReturn('BUY', 'rsi', {'a': 1}, '5%', lastDay[6])
                    elif not bool(peaksPosDI[len(peaksPosDI) - 1]['type']):
                        afterNegativePattern = None
                        for item in candlePattern:
                            if item['date'] < lastCandlePattern['date'] and item['type'] == 'negative':
                                afterNegativePattern = item
                        if self.getRSIByDate(self.rsi, lastCandlePattern['date'])['rsi'] / 50 <= 1.05:
                            if afterNegativePattern['value'][0] <= lastCandlePattern['value'][0] and self.getRSIByDate(self.rsi, lastCandlePattern['date'])['rsi'] <= self.getRSIByDate(self.rsi, afterNegativePattern['date'])['rsi']:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            else:
                                if lastCandlePattern['value'][0] / patternBB[2] <= 1.02 and self.isDojiCandle(lastDay):
                                    dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                else:
                                    isCanceledPrice = self.isCanceledPrice(candlePattern,
                                                                           self.getMaxPattern(candlePattern))
                                    if not isCanceledPrice:
                                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                                    else:
                                        dataReturn = self.makeDataReturn('BUY', 'candle', {'a': '>'}, '5%', lastDay[6])
                        else:
                            if lastCandlePattern['value'][0] / patternBB[2] <= 1.02:
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            elif lastCandlePattern['value'][0] / patternBB[1] <= 0.98:
                                dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'rsi', {'a': 1}, '5%', lastDay[6])
            elif status == '054':
                if lastCandlePattern['type'] == 'positive':
                    patternCandle = self.getCandleByDate(lastCandlePattern['date'], currentPeriod)
                    patternBB = self.getBBbyDate(lastCandlePattern['date'])
                    patternRSI = self.getRSIByDate(self.rsi, lastCandlePattern['date'])
                    if self.getHistoricalMaxClosePrice(currentPeriod) == patternCandle:
                        dmiSelected = self.getDMIDataByDate(dmiPeriod, lastCandlePattern['date'])
                        if dmiSelected['DI']['positive'] <= 28 and dmiSelected['DI']['positive'] == peaksPosDI[len(peaksPosDI) - 1]['value']:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            if float(patternCandle[4]) / patternBB[0] >= 0.98:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            elif 1.03 >= float(patternCandle[4]) / patternBB[1] >= 0.97:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
                    elif float(patternCandle[4]) / patternBB[0] >= 0.98 or patternRSI['rsi'] / 70 >= 0.97:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    elif 1.03 >= float(patternCandle[4]) / patternBB[1] >= 0.97:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'rsi', {'a': 0}, '5%', lastDay[6])
            elif status == '044':
                if lastCandlePattern['type'] == 'positive':
                    patternCandle = self.getCandleByDate(lastCandlePattern['date'], currentPeriod)
                    patternBB = self.getBBbyDate(lastCandlePattern['date'])
                    if float(patternCandle[4]) / patternBB[0] >= 0.97 or self.getHistoricalMaxClosePrice(currentPeriod) == patternCandle:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    elif 1.03 >= float(patternCandle[4]) / patternBB[1] >= 0.97:
                        ap = None
                        for item in candlePattern:
                            if item['date'] < lastCandlePattern['date'] and item['type'] == 'positive':
                                ap = item
                        if self.getHistoricalMaxClosePrice(currentPeriod) == self.getCandleByDate(ap['date'], currentPeriod):
                            dataReturn = self.makeDataReturn('BUY', 'price', {'a': lastNegCandlePattern['value']}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        if 1.03 < float(patternCandle[4]) / patternBB[1]:
                            bl, _ = self.hasAnyDojiCandle(currentPeriod, lastCandlePattern['date'], lastCandlePattern)
                            if bl:
                                dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('SELL', 'bb', {'a': 0}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
            elif status == '043':
                if lastCandlePattern['type'] == 'negative':
                    patternCandle = self.getCandleByDate(lastCandlePattern['date'], currentPeriod)
                    patternRSI = self.getRSIByDate(self.rsi, lastCandlePattern['date'])
                    patternBB = self.getBBbyDate(lastCandlePattern['date'])
                    isCanceled = self.isCanceledPrice(candlePattern, self.getMaxPattern(candlePattern))
                    if not isCanceled:
                        if (float(patternCandle[4]) / patternBB[2] <= 1.02 or float(patternCandle[3]) / patternBB[2] <= 1.02) and self.isRSIPeakByDate(rsiPeaks, patternCandle[6], 0):
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        elif not bool(self.rsiCrosses[len(self.rsiCrosses) - 1]['type']) and 1.05 >= patternRSI['rsi'] / 50:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReutrn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                    else:
                        bl, item = self.isRSIPeakByDate(rsiPeaks, patternCandle[6], 0)
                        if float(patternCandle[4]) / patternBB[2] <= 1 and bl and item['rsi'] / 29 <= 1.00:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            if self.checkBullCycleFinish(momentums):
                                dataReturn = self.makeDataReturn('BUY', 'rsi', {'a': 2}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'rsi', {'a': 1}, '5%', lastDay[6])
            elif status == '041':
                patternCandle = self.getCandleByDate(lastCandlePattern['date'], currentPeriod)
                patternBB = self.getBBbyDate(lastCandlePattern['date'])
                patternRSI = self.getRSIByDate(self.rsi, lastCandlePattern['date'])
                if lastCandlePattern['type'] == 'negative':
                    if 1.05 >= patternRSI['rsi'] / 30:
                        dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                    elif float(lastDay[4]) > lastCandlePattern['value'][0]:
                       isExhaustion = self.detectBearishExhaustion(currentPeriod, candlePattern[len(candlePattern) - 2]['date'])
                       if isExhaustion:
                           dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                       else:
                           dataReturn = self.makeDataReturn('BUY', 'rsi', {'a': 1}, '5%', lastDay[6])
                    elif float(patternCandle[4]) / patternBB[2] <= 1.03:
                        isBreak = False
                        for item in candlePattern:
                            if item['date'] <= lastCandlePattern['date'] and self.getMaxPattern(candlePattern) == candlePattern[len(candlePattern) - 2] and item['type'] == 'negative':
                                if lastCandlePattern['value'][0] / item['value'][0] < 1.02:
                                    isBreak = True
                                    break
                        if isBreak:
                            dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                        else:
                            if patternRSI['rsi'] / 50 <= 1.02 and self.isRSIPeakByDate(rsiPeaks, lastCandlePattern['date'], 0):
                                dataReturn = self.makeDataReturn('BUY', 'now', {}, '5%', lastDay[6])
                            else:
                                dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                    else:
                        if candlePattern[len(candlePattern) - 1]['value'][0] < self.getMaxPattern(candlePattern)['value'][0]:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('BUY', 'bb', {'a': 2}, '5%', lastDay[6])
                elif lastCandlePattern['type'] == 'positive':
                    if not bool(self.rsiCrosses[len(self.rsiCrosses) - 1]['type']):
                        if 1.00 >= patternRSI['rsi'] / patternRSI['ma'] >= 0.95 and bool(rsiPeaks[len(rsiPeaks) - 1]['type']) and float(patternCandle[4]) / patternBB[1] <= 0.97:
                            dataReturn = self.makeDataReturn('BUY', 'candle', {'a': 'doji'}, '5%', lastDay[6])
                        else:
                            dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])
                    else:
                        dataReturn = self.makeDataReturn('SELL', 'now', {}, '5%', lastDay[6])

        self.sendData(dataReturn)

    def sendData(self, data: dict, callback: bool = False):

        isExecuted = False

        lastDay = self.klines[len(self.klines) - 1]

        if data['type'] == 'SELL':
            if data['VT'] == 'now':
                isExecuted = True
            elif data['VT'] == 'price':
                _, lastPosPattern, _ = self.getPatternsRequired(self.patterns)
                if 0.95 > float(lastDay[4]) / data['move']['a']:
                    if float(lastDay[4]) / float(self.getCandleByDate(lastPosPattern['date'], self.currentPeriod)[1]) < 1.00:
                        isExecuted = True
                    else:
                        if callback and data['cb_price'] is int:
                            isExecuted = True
                        else:
                            pass
                elif 0.95 < float(lastDay[4]) / data['move']['a'] <= 1.00:
                    if callback and data['cb_price'] == 1:
                        isExecuted = True
                    elif callback and data['cb_price'] == 0:
                        if not self.getCandleType(lastDay) and \
                                (float(lastDay[4]) / float(self.getCandleByDate(lastPosPattern['date'], self.currentPeriod)[1]) < 1.00 or self.isDojiCandle(lastDay)):
                            isExecuted = True
                    else:
                        data['cb_price'] = 0
                elif 1.00 < float(lastDay[4]) / data['move']['a'] <= 1.05:
                    if callback and data['cb_price'] == 2:
                        isExecuted = True
                    elif callback and data['cb_price'] == 1:
                        if not self.getCandleType(lastDay) and \
                                (float(lastDay[4]) / float(self.getCandleByDate(lastPosPattern['date'], self.currentPeriod)[1]) < 1.00 or self.isDojiCandle(lastDay)):
                            isExecuted = True
                    else:
                        data['cb_price'] = 1
                elif 1.05 < float(lastDay[4]) / data['move']['a'] <= 1.10:
                    if callback and data['cb_price'] == 2:
                        isExecuted = True
                    else:
                        data['cb_price'] = 2
            elif data['VT'] == 'candle':
                if data['move']['a'] == 'doji':
                    if self.isDojiCandle(lastDay) or float(lastDay[4]) / float(self.getLastBullCandle(self.currentPeriod)[1]) < 1:
                        isExecuted = True
                    else:
                        pass
                elif data['move']['a'] == '<':
                    if float(lastDay[4]) / float(self.getLastBullCandle(self.currentPeriod)[1]) < 1:
                        isExecuted = True
                    else:
                        pass
            elif data['VT'] == 'bb':
                if data['move']['a'] == 0:
                    posCandle = self.getCandleByDate(self.patterns[len(self.patterns) - 1]['date'])
                    lastPeak, lastPosPeak, lastNegPeak = self.getRSIPeaksRequired(self.getRSIPeaks(self.rsi, 5))
                    if float(posCandle[4]) / self.getBBbyDate(posCandle[6])[0] > 1 or 1.080 >= lastPosPeak['rsi'] / 50 >= 0.920:
                        if self.getCandleType(lastDay) and float(lastDay[4]) / self.getBBbyDate(lastDay[6])[0] < 1:
                            isExecuted = True
                        elif float(posCandle[1]) > float(lastDay[4]):
                            isExecuted = True
                        else:
                            pass
                    else:
                        negCandle = self.getLastBearCandle(self.currentPeriod)
                        if float(negCandle[4]) / float(posCandle[1]) < 1:
                            isExecuted = True
            elif data['VT'] == 'rsi':
                if data['move']['a'] == 0:
                    _, lastPosPattern, _ = self.getPatternsRequired(self.patterns)
                    rsi_p = self.getRSIByDate(self.rsi, lastPosPattern['date'])
                    last_rsi = self.rsi[len(self.rsi) - 1]
                    if rsi_p['rsi'] >= 70 and last_rsi['ma'] > last_rsi['rsi'] < rsi_p['rsi'] and \
                            (self.isDojiCandle(self.getLastBearCandle(self.currentPeriod)) or self.checkBearishEngulfing(self.currentPeriod, lastPosPattern)):
                        isExecuted = True

        elif data['type'] == 'BUY':
            if data['VT'] == 'now':
                isExecuted = True
            elif data['VT'] == 'price':
                _, _, lastNegPattern = self.getPatternsRequired(self.patterns)
                if 1.05 < float(lastDay[4]) / data['move']['a']:
                    if float(lastDay[4]) / float(self.getCandleByDate(lastNegPattern['date'], self.currentPeriod)[1]) > 1.00:
                        isExecuted = True
                    else:
                        if callback and data['cb_price'] is int:
                            isExecuted = True
                        else:
                            pass

                elif 1.00 < float(lastDay[4]) / data['move']['a'] <= 1.05:
                    if callback and data['cb_price'] == 1:
                        isExecuted = True
                    elif callback and data['cb_price'] == 0:
                        if self.getCandleType(lastDay) and \
                                (float(lastDay[4]) / float(self.getCandleByDate(lastNegPattern['date'], self.currentPeriod)[1]) > 1.00 or self.isDojiCandle(lastDay)):

                            isExecuted = True
                    else:
                        data['cb_price'] = 0

                elif 0.95 < float(lastDay[4]) / data['move']['a'] <= 1.00:
                    if callback and data['cb_price'] == 2:
                        isExecuted = True
                    elif callback and data['cb_price'] == 1:
                        if self.getCandleType(lastDay) and \
                                (float(lastDay[4]) / float(self.getCandleByDate(lastNegPattern['date'], self.currentPeriod)[1]) > 1.00 or self.isDojiCandle(lastDay)):

                            isExecuted = True
                    else:
                        data['cb_price'] = 1

                elif 0.90 < float(lastDay[4]) / data['move']['a'] <= 0.95:
                        if callback and data['cb_price'] == 2:
                            isExecuted = True
                        else:
                            data['cb_price'] = 2
            elif data['VT'] == 'di':
                adx, pos, neg = self.getDMIPeaks(self.dmiPeriod, 5)
                if data['move']['a'] == 0:
                    lastNeg = neg[len(neg) - 1]
                    if lastNeg['value'] == self.momentums[len(self.momentums) - 1]['DI']['value']:
                        pass
                    elif bool(lastNeg['type']) and lastNeg['value'] >= 35 and self.rsi[len(self.rsi) - 1]['rsi'] < 30:
                        isExecuted = True
                    else:
                        pass
            elif data['VT'] == 'bb':
                if data['move']['a'] == 2:
                    negCandle = self.getLastBearCandle(self.currentPeriod)
                    if float(negCandle[4]) / self.getBBbyDate(negCandle[6])[2] < 1:
                        if self.getCandleType(lastDay) and float(lastDay[4]) / self.getBBbyDate(lastDay[6])[2] > 1:
                            isExecuted = True
                        elif float(negCandle[1]) < float(lastDay[4]):
                            isExecuted = True
                        else:
                            pass
                    else:
                        posCandle = self.getLastBullCandle(self.currentPeriod)
                        if float(negCandle[1]) / float(posCandle[4]) < 1:
                            isExecuted = True
            elif data['VT'] == 'candle':
                lastPattern, _, _ = self.getPatternsRequired(self.patterns)
                if data['move']['a'] == '>':
                    lbc = self.getLastBullCandle(self.currentPeriod)
                    lbrc = self.getLastBearCandle(self.currentPeriod)
                    if float(lbc[4]) / float(lbrc[1]) > 1 and \
                            lbc[6] > lbrc[6]:
                        isExecuted = True
                    else:
                        pass
                elif data['move']['b'] == '<':
                    if not(self.lastTrade is None) and lastPattern['type'] == 'positive' and self.lastTrade['type'] == 'BUY':
                        isExecuted = True
                        data['type'] = 'SELL'
                    elif lastPattern['type'] == 'negative':
                        return self.newPricePrediction(self.klines)
                    else:
                        if data['move']['a'] == 'doji':
                            if self.isDojiCandle(lastDay) or float(lastDay[4]) / float(
                                    self.getLastBullCandle(self.currentPeriod)[1]) < 1:
                                isExecuted = True
                            else:
                                pass
                        elif data['move']['a'] == '>':
                            lbc = self.getLastBullCandle(self.currentPeriod)
                            lbrc = self.getLastBearCandle(self.currentPeriod)
                            if float(lbc[4]) / float(lbrc[1]) > 1 and \
                                    lbc[6] > lbrc[6]:
                                isExecuted = True
                            else:
                                pass
            elif data['VT'] == 'rsi':
                if data['move']['a'] == 1:
                    _, _, lastNegPattern = self.getPatternsRequired(self.patterns)
                    bfPattern = self.patterns[self.patterns.index(lastNegPattern) - 1]
                    rsi_p = self.getRSIByDate(self.rsi, lastNegPattern['date'])
                    last_rsi = self.rsi[len(self.rsi) - 1]
                    peaks = self.getRSIPeaks(self.rsi, 5)
                    if peaks[len(peaks) - 1]['date'] == lastNegPattern['date'] and \
                       bfPattern['value'][0] / float(self.getHistoricalMaxClosePrice(self.currentPeriod)[4]) >= 0.97 and \
                       (1.060 >= peaks[len(peaks) - 1]['rsi'] / 50 >= 0.90 or 1.150 >= peaks[len(peaks) - 1]['rsi'] / 30):
                        isExecuted = True
                elif data['move']['a'] == 2:
                    _, _, lastNegPattern = self.getPatternsRequired(self.patterns)
                    bfPattern = self.patterns[self.patterns.index(lastNegPattern) - 1]
                    rsi_p = self.getRSIByDate(self.rsi, lastNegPattern['date'])
                    last_rsi = self.rsi[len(self.rsi) - 1]
                    peaks = self.getRSIPeaks(self.rsi, 5)
                    lastPeak, _, lastNegPeak = self.getRSIPeaksRequired(peaks)
                    if lastNegPeak['date'] == lastNegPattern['date'] and \
                       bfPattern['value'][0] / float(self.getHistoricalMaxClosePrice(self.currentPeriod)[4]) >= 0.97 and \
                       (1.01 >= lastNegPeak['rsi'] / 30):
                        isExecuted = True

        if not isExecuted:
            t_sleep = self.getDiffBetweenDays() / 1000
            time.sleep(t_sleep if t_sleep > -1 else t_sleep * -1)
            d = datetime.datetime.now()
            ts = d.timestamp()
            ts = ts * 1000
            d = datetime.datetime.fromtimestamp((ts - 86400000) / 1000)
            self.endPeriod = f'{date.strftime("%d")} {date.strftime("%b")}, {date.strftime("%Y")}'
            self.setTradeData()
            self.sendData(data, callback=True)
        else:
            pass
    def getRSIPeaksRequired(self, peaks: list):
        last = None
        p = None
        n = None

        for item in peaks:
            last = item
            if bool(last['type']):
                p = item
            else:
                n = item
        return last, p, n

    def checkBullCycleFinish(self, momentums: list):
        bl = False
        lastItem = momentums[len(momentums) - 1]
        if momentums.index(lastItem) - 1 < 0:
            return False
        elif (bool(momentums[momentums.index(lastItem) - 2]['DI']['type']) and \
             not bool(momentums[momentums.index(lastItem) - 1]['DI']['type']) and \
             bool(lastItem['DI']['type'])) or \
            (bool(momentums[momentums.index(lastItem) - 1]['DI']['type']) and \
             bool(lastItem['DI']['type'])):
            return True
        else:
            return False

    def checkBearishEngulfing(self, entry: list, pattern: dict):

        lpc = self.getCandleByDate(pattern['date'], self.currentPeriod)
        next_c=  self.getCandleByDate(pattern['date'] + 86400000, self.currentPeriod)
        if float(next_c[4]) < float(lpc[1]):
            return True
        else:
            return False

    def getPatternsRequired(self, entry):
        last = None
        pos = None
        neg = None
        for item in entry:
            if item['type'] == 'positive':
                pos = item
            elif item['type'] == 'negative':
                neg = item
            last = item
        return last, pos, neg

    def getLastBullCandle(self, entry: list):
        candle = None
        entry.reverse()
        for item in entry:
            if float(item[1]) / float(item[4]) < 1:
                candle = item
                break
        entry.reverse()
        return candle

    def getLastBearCandle(self, entry: list):
        candle = None
        entry.reverse()
        for item in entry:
            if float(item[1]) / float(item[4]) > 1:
                candle = item
                break
        entry.reverse()
        return candle

    def getDiffBetweenDays(self):
        date = self.klines[len(self.klines) - 1][6]
        nextDay = date + 86400000
        diff = nextDay - datetime.datetime.now().timestamp()*1000
        return diff

    def sideSellClients(self):

        clients = []
        for item in clients:
            client = Client(item[0], item[1])
            client.create_order(
                symbol='BTCUSDT',
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=client.get_asset_balance('BTC'),
            )

    def isRSIPeakByDate(self, rsiPeaks: list, date:int, t: int):
        bl = False
        i = None
        for item in rsiPeaks:
            if item['date'] == date and item['type'] == t:
                value = True
                i = item
        return bl, i

    def detectBearishExhaustion(self, period: list, date: int):
        isExhaust = False
        neg = [0, 0]
        pos = [0, 0]
        for item in period:
            if item[6] > date:
                if float(item[1]) / float(item[4]) < 1:
                    pos[0] += float(item[4]) - float(item[1])
                    pos[1] += 1
                else:
                    neg[0] += float(item[1]) - float(item[4])
                    neg[1] += 1
        if pos[0] > neg[0] and pos[1] < neg[1]:
            isExhaust = True
        elif pos[0] < neg[0] and pos[1] < neg[1] / 2:
            isExhaust = True
        else:
            isExhaust = False
        return isExhaust

    def getMaxPattern(self, candlePattern: list):
        value = None
        for item in candlePattern:
            if item['type'] == 'positive':
                if value is None:
                    value = item
                    continue
                elif value['value'][0] < item['value'][0]:
                    value = item
        return value

    def isCanceledPrice(self, candlePattern: list, guidePattern: list):
        isCanceled = False
        for item in candlePattern:
            if item['value'][0] / guidePattern['value'][0] >= 0.97 and item['type'] == guidePattern['type']:
                isCanceled = True
                break
        return isCanceled

    def getRSIByDate(self, entry: list, date:int):
        value = {}
        entry.reverse()
        for item in entry:
            if item['date'] == date:
                value = item
                break
        entry.reverse()
        return value

    def checkRSIDepletion(self, peaks: list, guideCross: dict, peakGuide: dict):
        t = guideCross['type']
        isDeplete = False
        peaks.reverse()
        for item in peaks:
            if item['type'] == t and peakGuide['date'] > item['date'] >= guideCross['period'][0]['date'] and item['rsi'] >= 70:
                if 1.03 >= item['rsi'] / peakGuide['rsi'] >= 0.97:
                    isDeplete = True
                    break
        peaks.reverse()
        return isDeplete

    def getRSIPeaks(self, entry: list, percentage: int = 0):
        values = []
        up = 1.1
        down = 0.9
        if percentage != 0:
            up = 1 + percentage / 100
            down = 1 - percentage / 100

        for item in entry:
            if not bool(len(values)):
                values.append({
                    'rsi': item['rsi'],
                    'ma': item['ma'],
                    'date': item['date'],
                    'type': None
                })
                continue

            av = values[len(values) - 1]
            res = item['rsi'] / av['rsi']
            if res > 1:
                if av['type'] is None:
                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'type': 1
                    })
                elif bool(av['type']):
                    values.remove(av)
                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'type': 1
                    })
                elif not bool(av['type']) and res >= up:
                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'type': 1
                    })
            elif res < 1:
                if av['type'] is None:
                    values.append({
                            'rsi': item['rsi'],
                            'ma': item['ma'],
                            'date': item['date'],
                            'type': 0
                    })
                elif not bool(av['type']):
                    values.remove(av)
                    values.append({
                            'rsi': item['rsi'],
                            'ma': item['ma'],
                            'date': item['date'],
                            'type': 0
                    })
                elif bool(av['type']) and res <= down:
                    values.append({
                            'rsi': item['rsi'],
                            'ma': item['ma'],
                            'date': item['date'],
                            'type': 0
                    })
        return values

    def getRSICrosses(self, entry: list):
        values = []

        for item in entry:
            if item['ma'] is None:
                continue

            if item['rsi'] > item['ma']:
                if len(values) == 0:
                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'period': [item],
                        'type': 1
                    })
                elif not bool(values[len(values) - 1]['type']) and item['rsi'] / item['ma'] >= 1.2:
                    afterValue = values[len(values) - 1]
                    newPeriod = self.correctRSIPeriod(afterValue['period'], bool(afterValue['type']))
                    afterValue['period'] = newPeriod

                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'period': self.getRSIPeriod(entry, item['date'], not bool(afterValue['type'])),
                        'type': 1
                    })
                else:
                    values[len(values) - 1]['period'].append(item)
            elif item['rsi'] < item['ma']:
                if len(values) == 0:
                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'period': [item],
                        'type': 0
                    })
                elif bool(values[len(values) - 1]['type']) and item['rsi'] / item['ma'] <= 0.8:
                    afterValue = values[len(values) - 1]
                    newPeriod = self.correctRSIPeriod(afterValue['period'], bool(afterValue['type']))
                    afterValue['period'] = newPeriod

                    values.append({
                        'rsi': item['rsi'],
                        'ma': item['ma'],
                        'date': item['date'],
                        'period': self.getRSIPeriod(entry, item['date'], not bool(afterValue['type'])),
                        'type': 0
                    })
                else:
                    values[len(values) - 1]['period'].append(item)
        return values

    def correctRSIPeriod(self, period: list, t: bool):
        index = 0
        for item in period:
            if not t:
                if period[index]['rsi'] > item['rsi']:
                    index = period.index(item)
            elif t:
                if period[index]['rsi'] < item['rsi']:
                    index = period.index(item)
        return period[:index + 1]

    def getRSIPeriod(self, entry: list, date: int, t: bool):
        period = []
        guide = []
        entry.reverse()
        for item in entry:
            if not t and not (item['ma'] is None):
                if item['date'] <= date:
                    guide.append(item)
                if item['rsi'] / item['ma'] >= 1.2 and len(guide) > 1:
                    break
            elif t and not (item['ma'] is None):
                if item['date'] <= date:
                    guide.append(item)
                if item['rsi'] / item['ma'] <= 0.8 and len(guide) > 1:
                    break
        entry.reverse()
        if not t:
            maxValue = None
            for item in guide:
                if maxValue is None:
                    maxValue = item
                elif maxValue['rsi'] < item['rsi']:
                    maxValue = item
            guide.reverse()
            for i in range(guide.index(maxValue), len(guide)):
                period.append(guide[i])
        elif t:
            minValue = None
            for item in guide:
                if minValue is None:
                    minValue = item
                elif minValue['rsi'] > item['rsi']:
                    minValue = item
            guide.reverse()
            for i in range(guide.index(minValue), len(guide)):
                period.append(guide[i])

        return period

    def getDMIDataByDate(self, dmiPeriod: list, date: int):
        value = None
        dmiPeriod.reverse()
        for item in dmiPeriod:
            if item['date'] == date:
                value = item
                break
        return value


    def getCandleType(self, candle):
        if float(candle[1]) / float(candle[4]) > 1:
            return False
        else:
            return True

    def hasAnyDojiCandle(self, entry: list, dg: int, cp:dict):
        entry.reverse()
        bl = False
        candle = []
        for item in entry:
            if item[6] >= dg and self.isDojiCandle(item):
                if self.getDojiType(item) and 0.98 <= float(item[2]) / cp['value'][0]:
                    bl = True
                    candle = item
                    break
                elif not self.getDojiType(item) and float(item[4]) / cp['value'][0] >= 0.97:
                    bl = True
                    candle = item
                    break

        return bl, candle

    def makeDataReturn(self, t: str, vt: str, move: dict, tp: str, date: int):
        value = {
            'type': t,
            'VT': vt,
            'move': move,
            'TP': tp,
            'date': date
        }
        return value

    def getMajorSupportCandle(self, candlePeriod: list, dmiPeriod: list, trend: bool, momentum: dict):
        adx, pos, neg = self.getDMIPeaks(dmiPeriod, 2)
        candleGuide = None

        if not bool(momentum['DI']['type']):
            neg.reverse()
            for item in neg:
                if momentum['DI']['date'] < item['date'] <= (
                momentum['ADX']['date'] if not (momentum['ADX'] is None) else item['date']) and item[
                    'value'] > 35 and bool(item['type']):
                    candleGuide = self.getCandleByDate(item['date'], candlePeriod)
                    break
        elif bool(momentum['DI']['type']):
            dmiValue = None
            dmiPeriod.reverse()
            for item in dmiPeriod:
                if item['DI']['positive'] == momentum['DI']['value'] and item['DI']['positive'] / dmiPeriod[dmiPeriod.index(item) + 1]['DI']['positive'] <= 1.02:
                    dmiValue = dmiPeriod[dmiPeriod.index(item) + 1]
                    break
                elif item['DI']['positive'] == momentum['DI']['value']:
                    dmiValue = item
                    break
            dmiPeriod.reverse()
            candleGuide = self.getCandleByDate(dmiValue['date'], candlePeriod)

        return candleGuide

    def getGuideCandleForBB(self, candlePeriod: list, dmiPeriod: list, trend: bool, momentum: dict):
        adx, pos, neg = self.getDMIPeaks(dmiPeriod, 2)
        candleGuide = None

        if not bool(momentum['DI']['type']):
            neg.reverse()
            for item in neg:
                if momentum['DI']['date'] < item['date'] <= (momentum['ADX']['date'] if not (momentum['ADX'] is None) else item['date']) and item['value'] > 35 and bool(item['type']):
                    candleGuide = self.getCandleByDate(item['date'], candlePeriod)
                    break
        elif bool(momentum['DI']['type']):
            pos.reverse()
            for item in pos:
                if momentum['DI']['date'] < item['date'] <= (momentum['ADX']['date'] if not (momentum['ADX'] is None) else item['date']) and item['value'] > 35 and bool(item['type']):
                    candleGuide = self.getCandleByDate(item['date'], candlePeriod)
                    break

        return candleGuide

    def checkTheEvent(self, condition: bool, entry: list, lvc: list):
        value = None
        for item in entry:
            if not condition:
                if float(item[4]) / float(lvc[3]) < 1.03:
                    value = True
                    break
                else:
                    value = False
        return value

    def getBBbyDate(self, date: int):
        value = None
        for item in self.klines:
            if item[6] == date:
                value = [self.bb[0][self.klines.index(item)], self.bb[1][self.klines.index(item)], self.bb[2][self.klines.index(item)]]
                break
        return value

    def getBBSupport(self, guide: list):

        if guide is None or not guide:
            return 0
        else:
            index = self.klines.index(guide)
            return self.bb[2][index]

    def getBB(self, entry: list):
        pass
        """close = self.getCloseData(entry)
        bb = ta.bbands(np.array(close), length=20, nbdevup=2, nbdevdn=2, mamode=0)
        return bb"""

    def getRSI(self, entry: list):

        closes = self.getCloseData(self.klines)

        rsi = _rsi(pandas.Series(closes), window=14)
        ma = _sma_indicator(rsi, window=20)
        values = []
        for i in range(0, len(rsi)):
            if str(rsi[i]) != 'nan':
                values.append({
                    'rsi': rsi[i],
                    'ma': None if str(ma[i]) == 'nan' else ma[i],
                    'date': entry[i][6]
                })
        return values

    def getCloseData(self, entry: list):
        closes = []
        for item in entry:
            closes.append(float(item[4]))
        return closes

    def getDojiType(self, candle: list):

        open = float(candle[1])
        openDate = candle[0]
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        closeDate = candle[6]

        upRes = high - open
        btRes = close - low

        if upRes > btRes:
            return True
        else:
            return False

    def isDojiCandle(self, candle: list):

        open = float(candle[1])
        openDate = candle[0]
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        closeDate = candle[6]

        trend = None

        dif = abs(open - close)
        highDif = abs(high - open)
        lowDif = abs(low - open)

        if highDif / dif >= 3 or lowDif / dif >= 3:
            return True
        else:
            return False

    def getCandleByDate(self, date: int, entry: list):

        candle = None
        for item in entry:
            if item[6] == date:
                candle = item
                break

        return candle

    def getDMIPattern(self, entry: list, trendDirection: int):

        # status 011: Bear Trend don't consolidate
        # status 012: Bull Trend don't consolidate
        # status 013: Bear trend in consolidate
        # status 014: Bull trend in consolidate
        # status 021: Bear Trend consolidate
        # status 022: Bull trend consolidate
        # status 031: Big bearish candle, or with high volume
        # status 032: Big bull candle, or with high volume
        # status 041: Bearish regression complete (BUY)
        # status 042: Bull regression complete (SELL)
        # status 043: Bearish regression incomplete
        # status 044: Bull regression incomplete
        # status 051: Continue bearish trend, or is exhausting
        # status 052: continue bull trend, or is exhausting
        # status 053: Bearish trend will flip trend soon
        # status 054: Bull trend will flip trend soon
        # status 061: Bearish trend revive
        # status 062: Bull trend revive
        # status 071: Bear price is exhasting in the DMI value, but it broken some support
        # status 072: Bull price is exhausting in the DMI value, but it broken some resistance

        # First filter the values from the differents metrics
        ADX = []
        posDI = []
        negDI = []

        for item in entry:
            ADX.append({
                'date': item['date'],
                'value': item['ADX']
            })
            posDI.append({
                'date': item['date'],
                'value': item['DI']['positive']
            })
            negDI.append({
                'date': item['date'],
                'value': item['DI']['negative']
            })

        lastADX = ADX[len(ADX) - 1]
        lastNegDI = negDI[len(negDI) - 1]
        lastPosDI = posDI[len(posDI) - 1]

        dataReturn = {}

        # Get the metrics peaks
        adxPeaks, peaksPosDI, peaksNegDI = self.getDMIPeaks(entry, 10)
        lastPeakADX = adxPeaks[len(adxPeaks) - 1]
        lastPeakPosDI = peaksPosDI[len(peaksPosDI) - 1]
        lastPeakNegDI = peaksNegDI[len(peaksNegDI) - 1]

        # Get the maximum of each metric
        maxNegDI = None
        maxPosDI = None
        maxADX = None

        for item in adxPeaks:
            if maxADX is None:
                maxADX = item
                continue

            if maxADX['value'] < item['value']:
                maxADX = item

        for item in peaksPosDI:
            if maxPosDI is None:
                maxPosDI = item
                continue

            if maxPosDI['value'] < item['value']:
                maxPosDI = item

        for item in peaksNegDI:
            if maxNegDI is None:
                maxNegDI = item
                continue

            if maxNegDI['value'] < item['value']:
                maxNegDI = item

        # Get the happened momentums

        momentums = self.getDMIMomentum(entry, trendDirection)
        self.momentums = momentums
        lastMomentum = momentums[len(momentums) - 1]
        lastNegMomentum = None
        lastPosMomentum = None

        for item in momentums:
            if bool(item['DI']['type']):
                lastPosMomentum = item
            elif not bool(item['DI']['type']):
                lastNegMomentum = item

        consolidate = False

        # Start the analysis of the pattern

        # If the max +DI has a value major to 30 and be in course a bear trend
        # * >30 : It means that it is strong trend, or a high volume candle has just closed
        if maxNegDI['value'] > 30 and not bool(trendDirection):

            # Get the ADX from +DIs day
            adxDay = ADX[negDI.index({'date': maxNegDI['date'], 'value': maxNegDI['value']})]

            # If the last momentum is bull, and happened after the bear momentum, and the last +DI is major to last -DI
            if bool(lastMomentum['DI']['type']) and lastNegMomentum['DI']['date'] < lastMomentum['DI']['date'] > lastNegMomentum['ADX']['date'] and lastNegDI['value'] < lastPosDI['value'] and (lastADX['value'] > lastPosDI['value'] or lastPosDI['value'] >= 28):
                dataReturn['status'] = '012'

            # If maxNegDI is major than current ADX
            elif adxDay['value'] < lastNegMomentum['DI']['value'] and lastNegMomentum['ADX'] is None:

                # Trend doesn't consolidation
                dataReturn['status'] = '011'

            elif not (lastNegMomentum['ADX'] is None) and lastNegMomentum['DI']['date'] < lastNegMomentum['ADX']['date']:
                #TODO
                consolidate = True

                index = ADX.index({
                    'date': lastNegMomentum['ADX']['date'],
                    'value': lastNegMomentum['ADX']['value']
                })
                if len(ADX) - 1 == index:
                    dataReturn['status'] = '013'
                else:

                    # If the last -DI is less to 40 and major to 28, and the last ADX is less to last -DI value, and the last peak -DI is bull
                    if 40 > lastNegDI['value'] > 28 and 15 < lastADX['value'] < lastNegDI['value'] and bool(
                            lastPeakNegDI['type']):

                        isRegression = None
                        peaksPosDI.reverse()
                        for item in peaksPosDI:

                            if bool(item['type']) and lastNegMomentum['ADX']['date'] < item['date'] < lastNegDI['date']:

                                if 40 > item['value'] >= 25:

                                    d_nD = None
                                    negDI.reverse()
                                    for i in negDI:
                                        if i['date'] == item['date']:
                                            d_nD = i
                                            break
                                    negDI.reverse()

                                    d_adx = None
                                    ADX.reverse()
                                    for i in ADX:
                                        if i['date'] == item['date']:
                                            d_adx = i
                                            break
                                    ADX.reverse()

                                    if d_nD['value'] < item['value'] and not bool(
                                            peaksPosDI[peaksPosDI.index(item) - 1]['type']):
                                        isRegression = True
                                        break
                                    else:
                                        isRegression = False
                                        break

                                elif item['value'] < 25:

                                    d_nD = None
                                    negDI.reverse()
                                    for i in negDI:
                                        if i['date'] == item['date']:
                                            d_nD = i
                                            break
                                    negDI.reverse()

                                    d_adx = None
                                    ADX.reverse()
                                    for i in ADX:
                                        if i['date'] == item['date']:
                                            d_adx = i
                                            break
                                    ADX.reverse()

                                    if d_adx['value'] < item['value'] > d_nD['value']:
                                        isRegression = True
                                        break
                                    else:
                                        isRegression = False
                                        break

                                else:
                                    isRegression = False
                                    break

                            else:
                                isRegression = False
                        peaksPosDI.reverse()

                        if not isRegression is None:

                            if isRegression:

                                dataReturn['status'] = '041'

                            else:
                                dataReturn['status'] = '031'

                    # If the last -DI value is less to 40 points and major to 28 points, and the last ADX value is less to maximum value
                    # from ADX and major to last -DI value
                    elif 40 > lastNegDI['value'] >= 28 and lastNegMomentum['ADX']['value'] >= lastADX['value'] > lastNegDI['value']:

                        hypotheticalItem = {
                            'date': lastNegDI['date'],
                            'type': 1,
                            'value': lastNegDI['value']
                        }

                        # If the last ADX value is major to 30 points and the reason between the last ADX value and the maximum ADX value
                        # is major or match to -2%
                        if lastADX['value'] > 28 and 1 > lastADX['value'] / lastNegMomentum['ADX']['value'] >= 0.98:

                            # Bear trend consolidate, because is exhausting the bear impulse
                            if hypotheticalItem in peaksNegDI:
                                dataReturn['status'] = '041'
                            else:
                                dataReturn['status'] = '021'

                        # If the last ADX value is major to 28 points and the reason between the last ADX value and the maximum ADX value
                        # is less to -2%
                        elif lastADX['value'] > 28 and lastADX['value'] / lastNegMomentum['ADX']['value'] < 0.98:

                            # Create from the last -DI, a hypothetical peak item
                            hypotheticalItem = {
                                'date': lastNegDI['date'],
                                'type': 1,
                                'value': lastNegDI['value']
                            }

                            # If the hypothetical item exists
                            if hypotheticalItem in peaksNegDI:

                                # It has a big volume candle, and check if hit any support
                                dataReturn['status'] = '071'

                            else:

                                # Else means continue trend, or is it over soon
                                dataReturn['status'] = '051'

                    # If the last -DI value is less to 28 points and the last ADX value is less to maximum value
                    # from ADX and major to last -DI value
                    elif lastNegDI['value'] < 28 and lastNegMomentum['ADX']['value'] >= lastADX['value'] > lastNegDI['value']:

                        if lastNegDI['value'] >= 22:

                            hypotheticalItem = {
                                'date': lastNegDI['date'],
                                'type': 1,
                                'value': lastNegDI['value']
                            }

                            if (lastPeakADX['date'] == lastNegDI['date'] or hypotheticalItem in peaksNegDI) and \
                                    lastPeakADX['value'] <= 30:
                                dataReturn['status'] = '053'
                            else:
                                dataReturn['status'] = '051'

                        else:

                            if lastNegDI['value'] < lastPosDI['value'] and lastADX['value'] < 30:

                                h_i = {
                                    'date': lastNegDI['date'],
                                    'type': 0,
                                    'value': lastNegDI['value']
                                }

                                if h_i in peaksNegDI or bool(lastPeakPosDI['type']) or bool(peaksPosDI[len(peaksPosDI) - 2]['type']):
                                    if lastPeakPosDI['value'] >= 28 or peaksPosDI[len(peaksPosDI) - 2]['value'] >= 28:
                                        dataReturn['status'] = '042'
                                    else:
                                        dataReturn['status'] = '044'
                                else:
                                    dataReturn['status'] = '044'
                            elif bool(lastPeakPosDI['type']) and round(lastPeakPosDI['value']) >= 20 and lastADX['value'] >= 25:
                                dataReturn['status'] = '044'
                            else:
                                dataReturn['status'] = '043'

                    elif 28 > lastNegDI['value'] >= lastADX['value'] <= lastNegMomentum['ADX']['value']:

                        if lastNegDI['value'] < lastPosDI['value']:
                            if bool(lastPeakPosDI['type']):
                                dataReturn['status'] = '044'
                            else:
                                dataReturn['status'] = '043'
                        else:
                            if not bool(lastPeakNegDI['type']):
                                if lastPeakPosDI['value'] <= 18:
                                    dataReturn['status'] = '043'
                                else:
                                    dataReturn['status'] = '044'
                            else:
                                dataReturn['status'] = '043'

            # Revive Trend
            elif lastNegMomentum['ADX'] is None:
                dataReturn['status'] = '061'

        if maxPosDI['value'] > 30 and bool(trendDirection):

            # Get the ADX from +DIs day
            adxDay = ADX[posDI.index({'date': maxPosDI['date'], 'value': maxPosDI['value']})]

            if not bool(lastMomentum['DI']['type']) and lastPosMomentum['DI']['date'] < lastMomentum['DI']['date'] > lastPosMomentum['ADX']['date'] and lastPosDI['value'] < lastNegDI['value'] and (lastADX['value'] > lastNegDI['value'] or lastNegDI['value'] >= 28):
                dataReturn['status'] = '011'

            # If maxNegDI is major than current ADX
            elif adxDay['value'] < lastPosMomentum['DI']['value'] and lastPosMomentum['ADX'] is None:

                # Trend doesn't consolidation
                dataReturn['status'] = '012'

            elif not (lastPosMomentum['ADX'] is None) and lastPosMomentum['DI']['date'] < lastPosMomentum['ADX']['date']:

                consolidate = True

                index = ADX.index({
                    'date': lastPosMomentum['ADX']['date'],
                    'value': lastPosMomentum['ADX']['value']
                })
                if len(ADX) - 1 == index:
                    dataReturn['status'] = '014'
                else:

                    # If the last -DI is less to 40 and major to 28, and the last ADX is less to last -DI value, and the last peak -DI is bull
                    if 40 > lastPosDI['value'] > 28 and 15 < lastADX['value'] < lastPosDI['value'] and bool(
                            lastPeakPosDI['type']):

                        isRegression = None
                        peaksNegDI.reverse()
                        for item in peaksNegDI:

                            if bool(item['type']) and lastPosMomentum['ADX']['date'] < item['date'] < lastPosDI['date']:

                                if 40 > item['value'] >= 25:

                                    d_pD = None
                                    posDI.reverse()
                                    for i in posDI:
                                        if i['date'] == item['date']:
                                            d_pD = i
                                            break
                                    posDI.reverse()

                                    d_adx = None
                                    ADX.reverse()
                                    for i in ADX:
                                        if i['date'] == item['date']:
                                            d_adx = i
                                            break
                                    ADX.reverse()

                                    if d_pD['value'] < item['value'] and not bool(
                                            peaksNegDI[peaksNegDI.index(item) - 1]['type']):
                                        isRegression = True
                                        break
                                    else:
                                        isRegression = False
                                        break

                                elif item['value'] < 25:

                                    d_pD = None
                                    posDI.reverse()
                                    for i in posDI:
                                        if i['date'] == item['date']:
                                            d_pD = i
                                            break
                                    posDI.reverse()

                                    d_adx = None
                                    ADX.reverse()
                                    for i in ADX:
                                        if i['date'] == item['date']:
                                            d_adx = i
                                            break
                                    ADX.reverse()

                                    if d_adx['value'] < item['value'] > d_pD['value']:
                                        isRegression = True
                                        break
                                    else:
                                        isRegression = False
                                        break

                                else:
                                    isRegression = False
                                    break

                            else:
                                isRegression = False
                        peaksNegDI.reverse()

                        if not (isRegression is None):

                            if isRegression:

                                dataReturn['status'] = '042'

                            else:
                                dataReturn['status'] = '032'

                    # If the last -DI value is less to 40 points and major to 28 points, and the last ADX value is less to maximum value
                    # from ADX and major to last -DI value
                    elif 40 > lastPosDI['value'] >= 28 and lastADX['value'] > \
                            lastPosDI['value']:

                        hypotheticalItem = {
                            'date': lastPosDI['date'],
                            'type': 1,
                            'value': lastPosDI['value']
                        }

                        # If the last ADX value is major to 30 points and the reason between the last ADX value and the maximum ADX value
                        # is major or match to -2%
                        if lastADX['value'] > 28 and lastADX['value'] / lastPosMomentum['ADX']['value'] >= 0.98:

                            # Bear trend consolidate, because is exhausting the bear impulse
                            if hypotheticalItem in peaksPosDI:
                                dataReturn['status'] = '042'
                            else:
                                dataReturn['status'] = '022'

                        # If the last ADX value is major to 28 points and the reason between the last ADX value and the maximum ADX value
                        # is less to -2%
                        elif lastADX['value'] > 28 and lastADX['value'] / lastPosMomentum['ADX']['value'] < 0.98:

                            # Create from the last -DI, a hypothetical peak item
                            hypotheticalItem = {
                                'date': lastPosDI['date'],
                                'type': 1,
                                'value': lastPosDI['value']
                            }

                            # If the hypothetical item exists
                            if hypotheticalItem in peaksPosDI:

                                # It has a big volume candle, and check if hit any resistance
                                dataReturn['status'] = '072'

                            else:

                                # Else means continue trend, or is it over soon
                                dataReturn['status'] = '052'

                    # If the last -DI value is less to 28 points and the last ADX value is less to maximum value
                    # from ADX and major to last -DI value
                    elif lastPosDI['value'] < 28 and lastPosMomentum['ADX']['value'] >= lastADX['value'] > lastPosDI[
                        'value']:

                        if lastPosDI['value'] >= 22:

                            hypotheticalItem = {
                                'date': lastPosDI['date'],
                                'type': 1,
                                'value': lastPosDI['value']
                            }

                            if (lastPeakADX['date'] == lastPosDI['date'] or hypotheticalItem in peaksPosDI) and \
                                    lastPeakADX['value'] <= 30:
                                dataReturn['status'] = '054'
                            else:
                                dataReturn['status'] = '052'

                        else:

                            if lastPosDI['value'] < lastNegDI['value'] and lastADX['value'] < 30:

                                h_i = {
                                    'date': lastPosDI['date'],
                                    'type': 0,
                                    'value': lastPosDI['value']
                                }

                                if h_i in peaksPosDI or bool(lastPeakNegDI['type']) or bool(
                                        peaksNegDI[len(peaksNegDI) - 2]['type']):
                                    if lastPeakNegDI['value'] >= 28 or peaksNegDI[len(peaksNegDI) - 2]['value'] >= 28:
                                        dataReturn['status'] = '041'
                                    else:
                                        dataReturn['status'] = '043'
                                else:
                                    dataReturn['status'] = '043'
                            elif bool(lastPeakNegDI['type']) and round(lastPeakNegDI['value']) >= 20 and lastADX[
                                'value'] >= 25:
                                dataReturn['status'] = '043'
                            else:
                                dataReturn['status'] = '044'

                    elif 28 > lastPosDI['value'] >= lastADX['value'] <= lastPosMomentum['ADX']['value']:

                        if lastPosDI['value'] < lastNegDI['value']:
                            if bool(lastPeakNegDI['type']):
                                dataReturn['status'] = '043'
                            else:
                                dataReturn['status'] = '044'
                        else:
                            if not bool(lastPeakPosDI['type']):
                                if lastPeakNegDI['value'] <= 18:
                                    dataReturn['status'] = '044'
                                else:
                                    dataReturn['status'] = '043'
                            else:
                                dataReturn['status'] = '044'

                # Revive Trend
            elif lastPosMomentum['ADX'] is None:
                dataReturn['status'] = '062'

        return dataReturn['status'], momentums, adxPeaks, peaksPosDI, peaksNegDI

    def get_kline_by_date(self, date: int):

        kline = None

        for item in self.klines:
            if item[0] == date or item[6] == date:
                kline = item
                break

        return kline

    def get_dmi_marker_by_date(self, d: int):
        mr = None
        five_min = 300000
        mlt = 50
        if self.interval == Client.KLINE_INTERVAL_1HOUR:
            five_min = 3600000
            mlt = 10

        self.momentums.reverse()

        for item in self.momentums:
            if 0 <= d - item['DI']['date'] <= five_min * mlt:
                mr = item
                break

        self.momentums.reverse()

        return mr

    def get_klines_between_dates(self, d_start, d_end):

        klines = []

        for item in self.klines:
            if d_start <= item[6] <= d_end:
                klines.append(item)
            elif item[6] > d_end:
                break

        return klines

    def get_ema_cross_after_by_date(self, date):
        cross = None
        self.emaCrosses.reverse()
        for i in self.emaCrosses:
            if i['data'][0]['date'] < date:
                cross = i
                break
        self.emaCrosses.reverse()
        return cross

    def getDMIMomentum(self, entry: list):

        momentum = []

        pre_DI = None
        pre_ADX = None
        t = None

        for item in entry:

            negDI = item['DI']['negative']
            posDI = item['DI']['positive']
            adx = item['ADX']

            if item['date'] == 1664247599999:
                print('hola')

            if 40 <= negDI:

                if t == 1:
                    momentum.append({
                        'DI': {
                            'value': pre_DI['value'],
                            'date': pre_DI['date'],
                            'type': t
                        },
                        'ADX': pre_ADX
                    })
                    pre_DI = None
                    pre_ADX = None
                    t = None

                if pre_DI is None:
                    pre_DI = {'date': item['date'], 'value': negDI}
                elif pre_DI['value'] < negDI:

                    if item['date'] - pre_DI['date'] > 300000 * 5:
                        momentum.append({
                            'DI': {
                                'value': pre_DI['value'],
                                'date': pre_DI['date'],
                                'type': t
                            },
                            'ADX': pre_ADX
                        })
                        pre_DI = None
                        pre_ADX = None
                        t = None

                    pre_DI = {'date': item['date'], 'value': negDI}

                t = 0

            elif 40 <= posDI:

                if t == 0:
                    momentum.append({
                        'DI': {
                            'value': pre_DI['value'],
                            'date': pre_DI['date'],
                            'type': t
                        },
                        'ADX': pre_ADX
                    })
                    pre_DI = None
                    pre_ADX = None
                    t = None

                if pre_DI is None:
                    pre_DI = {'date': item['date'], 'value': posDI}
                elif pre_DI['value'] < posDI:

                    if item['date'] - pre_DI['date'] > 300000 * 5:
                        momentum.append({
                            'DI': {
                                'value': pre_DI['value'],
                                'date': pre_DI['date'],
                                'type': t
                            },
                            'ADX': pre_ADX
                        })
                        pre_DI = None
                        pre_ADX = None
                        t = None

                    pre_DI = {'date': item['date'], 'value': posDI}

                t = 1

            if not (pre_DI is None):

                if pre_DI['value'] <= adx and posDI < adx > negDI and pre_DI['date'] < item['date']:
                    if pre_ADX is None:
                        pre_ADX = {'date': item['date'], 'value': adx}
                    elif pre_ADX['value'] < adx:
                        pre_ADX = {'date': item['date'], 'value': adx}

                elif not (pre_ADX is None):

                    momentum.append({
                        'DI': {
                            'value': pre_DI['value'],
                            'date': pre_DI['date'],
                            'type': t
                        },
                        'ADX': pre_ADX
                    })

                    pre_ADX = None
                    pre_DI = None
                    t = None

                if len(entry) - 1 == entry.index(item) and pre_ADX is None and not (pre_DI is None):
                    momentum.append({
                        'DI': {
                            'value': pre_DI['value'],
                            'date': pre_DI['date'],
                            'type': t
                        },
                        'ADX': None
                    })

                    pre_DI = None
                    t = None

                if len(entry) - 1 == entry.index(item) and not (pre_ADX is None) and not (pre_DI is None):
                    momentum.append({
                        'DI': {
                            'value': pre_DI['value'],
                            'date': pre_DI['date'],
                            'type': t
                        },
                        'ADX': pre_ADX
                    })

                    pre_ADX = None
                    pre_DI = None
                    t = None

        return momentum

    def rounded(self, number):
        res = number - 0.5
        intNum = int(number)
        if res < intNum:
            return intNum
        elif res >= intNum:
            return intNum + 1

    def getDMIPeriod(self, start: int, end: int):

        values = []

        self.dmi.reverse()

        for item in self.dmi:

            if end >= item['date'] >= start:

                values.append(item)

            elif item['date'] < start:
                break

        self.dmi.reverse()
        values.reverse()
        return values

    def getDMIPeaks(self, entry: list, percentage: float = 0):

        neg = []
        pos = []
        adx = []

        #Check percentage
        up = 1.2
        dn = 0.8
        if percentage > 0:
            up = 1 + (percentage / 100)
            dn = 1 - (percentage / 100)

        for item in entry:

            posDI, negDI, adxItem = item['DI']['positive'], item['DI']['negative'], item['ADX']
            date = item['date']
            if item['date'] > 1652140799999:
                pass

            if not bool(len(neg)) and not bool(len(pos)) and not bool(len(adx)):
                neg.append({
                    'date': date,
                    'type': 1 if negDI > posDI else 0,
                    'value': negDI
                })
                pos.append({
                    'date': date,
                    'type': 1 if negDI < posDI else 0,
                    'value': posDI
                })
                adx.append({
                    'date': date,
                    'type': 1 if adxItem >= 25 else 0,
                    'value': adxItem
                })

                continue

            lastPosItem = pos[len(pos) - 1]
            lastNegItem = neg[len(neg) - 1]
            lastAdxItem = adx[len(adx) - 1]

            posRes = posDI / lastPosItem['value']
            negRes = negDI / lastNegItem['value']
            adxRes = adxItem / lastAdxItem['value']

            if posRes > 1:

                if not bool(lastPosItem['type']) and posRes >= up:
                    pos.append({
                        'date': date,
                        'type': 1,
                        'value': posDI
                    })
                elif not bool(lastPosItem['type']):
                    pass
                else:
                    pos.remove(pos[len(pos) - 1])

                    pos.append({
                        'date': date,
                        'type': 1,
                        'value': posDI
                    })

            elif posRes < 1:

                if bool(lastPosItem['type']) and posRes <= dn:
                    pos.append({
                        'date': date,
                        'type': 0,
                        'value': posDI
                    })
                elif bool(lastPosItem['type']):
                    pass
                else:
                    pos.remove(pos[len(pos) - 1])

                    pos.append({
                        'date': date,
                        'type': 0,
                        'value': posDI
                    })

            if negRes > 1:

                if not bool(lastNegItem['type']) and negRes >= up:
                    neg.append({
                        'date': date,
                        'type': 1,
                        'value': negDI
                    })
                elif not bool(lastNegItem['type']):
                    pass
                else:
                    neg.remove(neg[len(neg) - 1])

                    neg.append({
                        'date': date,
                        'type': 1,
                        'value': negDI
                    })

            elif negRes < 1:

                if bool(lastNegItem['type']) and negRes <= dn:
                    neg.append({
                        'date': date,
                        'type': 0,
                        'value': negDI
                    })
                elif bool(lastNegItem['type']):
                    pass
                else:
                    neg.remove(neg[len(neg) - 1])

                    neg.append({
                        'date': date,
                        'type': 0,
                        'value': negDI
                    })

            if adxRes > 1:

                if not bool(lastAdxItem['type']) and adxRes >= up:
                    adx.append({
                        'date': date,
                        'type': 1,
                        'value': adxItem
                    })
                elif not bool(lastAdxItem['type']):
                    pass
                else:
                    adx.remove(adx[len(adx) - 1])

                    adx.append({
                        'date': date,
                        'type': 1,
                        'value': adxItem
                    })

            elif adxRes < 1:

                if bool(lastAdxItem['type']) and adxRes <= dn:
                    adx.append({
                        'date': date,
                        'type': 0,
                        'value': adxItem
                    })
                elif bool(lastAdxItem['type']):
                    pass
                else:
                    adx.remove(adx[len(adx) - 1])

                    adx.append({
                        'date': date,
                        'type': 0,
                        'value': adxItem
                    })

        return adx, pos, neg

    def pricePrediction(self, entry):

        lastEmaStatus = self.emaCrosses[len(self.emaCrosses) - 1]
        # Data from the last 30 days
        # Datos de los ultimos 30 dias
        periodValues = []

        # Sorted data from periodValues
        # Datos ordenados de periodValues
        sortedValues = []

        for i in range((len(entry) - 30), (len(entry))):

            if len(periodValues) == 0:
                sortedValues.append(entry[i])
                periodValues.append(entry[i])
                continue

            length = 0

            for value in sortedValues:

                if float(value[4]) < float(entry[i][4]):
                    sortedValues.insert(sortedValues.index(value), entry[i])
                    break

                length += 1

            if length - 1 == len(sortedValues) - 1:
                sortedValues.append(entry[i])

            periodValues.append(entry[i])

        # Describes the pattern drawn by the candles of the period to determine how to analyze it
        # Describimos el patron que dibujan las velas del periodo para determinar de que forma lo analizaremos
        patternData = self.candlePattern(periodValues, 1.02, 0.98)

        # Search resistors and support points
        # Busca las resistencias y puntos de soporte
        ponderate = float(sortedValues[0][4]) / float(periodValues[len(periodValues) - 1][4])

        if sortedValues[0][6] < periodValues[len(periodValues) - 1][6]:
            ponderate = float(periodValues[len(periodValues) - 1][4]) / float(sortedValues[0][4])

        # If isBroke = true, it means that the price is below the EMA
        # Si isBroke = true, significa que el precio esta por debajo de la EMA
        isBreakEma = self.checkBreakEma(periodValues, sortedValues)

        lastCandle = periodValues[len(periodValues) - 1]

        if ponderate >= 1.20:

            print('hola')

        elif ponderate <= 0.80 or (
                patternData['positive']['status'] is False and patternData['negative']['status'] is True):

            # If the minimum price cross the EMA50 and the close price cross the EMA50
            # Si el precio minimo cruza la EMA50 y el precio de cierre cruza la EMA50
            if isBreakEma['ema50']['min']['isCross'] == True and isBreakEma['ema50']['end']['isCross'] == True:

                self.analysisStatus['trendStatus'] = not bool(lastEmaStatus['type'])

                # If the last EMA's cross is bull and the trend do not beats 40 days
                # Si el ultimo cruce de la EMA es alcista y la tendencia se encuentra entre los 7 y 40 dias
                if lastEmaStatus['type'] == 1 and (86400000 * 7) < (
                        periodValues[len(periodValues) - 1][6] - lastEmaStatus['data']['date']) < (86400000 * 40):

                    # We will search any support to buy the currency
                    # Buscaremos algun soporte para comprar la moneda

                    # Si la ultima y la minima vela rompe la EMA99
                    if isBreakEma['ema99']['end']['isCross'] or isBreakEma['ema99']['min']['isCross']:

                        # Si la razon entre la ultima vela y la menor vela es mayor o igual a 5%, y si el patron negative es positivo, o falso
                        if float(lastCandle[4]) / float(sortedValues[len(sortedValues) - 1][4]) >= 1.05 and (
                                patternData['negative']['status'] is True or patternData['negative'][
                            'status'] is False):

                            self.currentPriceMark = [
                                {
                                    'value': float(sortedValues[len(sortedValues) - 1][4]),
                                    'percentage': 1,
                                    'type': 'BUY'
                                }
                            ]
                            self.analysisStatus['priceMarked'] = self.currentPriceMark

                        # Si la razon entre el siguiente precio marcado y el precio de cierre de la ultima vela es menor a un -5%
                        # La usamos como punto de soporte para comprar en la correccion
                        elif float(lastCandle[4]) / float(sortedValues[len(sortedValues) - 1][4]) < 1.05 and 1.03 >= (
                                float(lastCandle[4]) / self.ema99[len(self.ema99) - 1]['value']) >= 0.97:

                            nmp = self.getNextMarkerPrice(float(sortedValues[len(sortedValues) - 1][4]), '<', 0.96)

                            self.currentPriceMark = [
                                {
                                    'value': nmp['value'][0],
                                    'percentage': 1,
                                    'type': 'BUY'
                                }
                            ]
                            self.analysisStatus['priceMarked'] = self.currentPriceMark

                        # Si el periodo de la anterior tendencia fue mayor a 40 dias, colocaremos como punto de compra, una resistencia
                        # marcada por la EMA99 una vez la cruce o toque, en señal de nueva fuerza alcista tras la pequeña correccion
                        elif lastEmaStatus['data']['date'] - self.emaCrosses[len(self.emaCrosses) - 2]['data'][
                            'date'] > (
                                86400000 * 40):

                            # Si la razon entre
                            if float(lastCandle[4]) / self.ema99[len(self.ema99) - 1]['value'] <= 0.95:

                                nmp = self.getNextMarkerPrice(float(lastCandle[4]), '>', 1.05, False)

                                self.currentPriceMark = [
                                    {
                                        'value': float(lastCandle[4]),
                                        'percentage': 1,
                                        'type': 'BUY'
                                    },
                                    {
                                        'value': nmp['value'][0],
                                        'percentage': 1,
                                        'type': 'SELL'
                                    }
                                ]
                                self.analysisStatus['priceMarked'] = self.currentPriceMark

                            else:
                                nmp = self.getNextMarkerPrice(float(lastCandle[4]), '<')

                                self.currentPriceMark = [
                                    {
                                        'value': nmp['value'][0],
                                        'percentage': 1,
                                        'type': 'BUY'
                                    }
                                ]
                                self.analysisStatus['priceMarked'] = self.currentPriceMark

                    # En el caso de que solo rompe la EMA50 solamente, usamos de soporte algun precio cerca de la EMA99
                    else:

                        lastEmaValue = self.ema99[len(self.ema99) - 1]['value']

                        priceMarked = None

                        for item in self.markersClose:

                            if 0.95 < item['value'][0] / lastEmaValue < 1.05:

                                if priceMarked is None:
                                    priceMarked = item

                                    continue

                                if float(priceMarked['volume'][0]) < float(item['volume'][0]):
                                    priceMarked = item

                        self.currentPriceMark = [
                            {
                                'value': priceMarked['value'][0],
                                'percentage': 1,
                                'type': 'BUY'
                            }
                        ]
                        self.analysisStatus['priceMarked'] = self.currentPriceMark

                    # Identificaremos los soportes y resistencias del periodo despues del cruce de la EMA


                # If the last EMA's cross is bull and the trend beats 40 days
                # Si el ultimo cruce de la EMA es alcista y la tendencia supera los 40 dias
                elif lastEmaStatus['type'] == 1 and (
                        periodValues[len(periodValues) - 1][6] - lastEmaStatus['data']['date']) > (86400000 * 40):

                    largerCandle = self.getLargerCandle(periodValues, not bool(lastEmaStatus['type']))
                    largerVolumeCandle = self.getLargerVolumeCandle(periodValues)

                    if isBreakEma['ema99']['min']['isCross'] and isBreakEma['ema99']['end']['isCross']:

                        # Si la vela mas grande es igual a la vela de mayor volumen, y, si la razon entre la diferencia
                        # del precio minimo y el precio de cierre, y la diferencia del precio de apertura y precio de cierre,
                        # es mayor o igual a 0.4 = 40%, lo colocamos como un punto interesantisimo de soporte
                        if largerCandle == largerVolumeCandle and (
                                (float(largerCandle[4]) - float(largerCandle[3])) / (
                                float(largerCandle[1]) - float(largerCandle[4])) >= 0.4
                        ) and sortedValues[len(sortedValues) - 1] == largerCandle:

                            self.analysisStatus['largerPriceVolume'] = largerCandle

                            consolidation = self.checkPriceConsolidation(periodValues, largerCandle,
                                                                         not bool(lastEmaStatus['type']))
                            self.analysisStatus['consolidation'] = consolidation

                            if consolidation:
                                nmp = self.getNextMarkerPrice(float(periodValues[len(periodValues) - 1][4]), '>')

                                if float(lastCandle[4]) / nmp['value'][0] <= 0.95:

                                    self.currentPriceMark = [nmp['value'][0]]
                                    self.analysisStatus['priceMarked'] = self.currentPriceMark

                                elif float(lastCandle[4]) / float(largerCandle[4]) <= 1.05:

                                    value1 = [(float(largerCandle[4]) + float(largerCandle[3])) / 2]

                                    if value1[0] / lastCandle[4] >= 1.05:
                                        self.currentPriceMark = value1
                                        self.analysisStatus['priceMarked'] = self.currentPriceMark

                                else:

                                    preliminaryData = [self.getNextMarkerPrice(float(largerCandle[4]), '<')['value'][0]]

                                    for value in preliminaryData:

                                        if value < float(largerCandle[3]):
                                            preliminaryData.insert(preliminaryData.index(value), float(largerCandle[3]))
                                            break

                                        preliminaryData.append(float(largerCandle[3]))
                                        break

                                    self.currentPriceMark = preliminaryData
                                    self.analysisStatus['priceMarked'] = self.currentPriceMark

                        # Si la vela mas grande es igual a la vela de mayor volumen, y si la vela de menor precio cotiza
                        # despues de la vela de mayor volumen
                        elif largerCandle == largerVolumeCandle and (
                                (float(largerCandle[4]) - float(largerCandle[3])) / (
                                float(largerCandle[1]) - float(largerCandle[4])) >= 0.4
                        ) and largerVolumeCandle[6] < sortedValues[len(sortedValues) - 1][6]:

                            # Esto significa que la fuerza bajista esta cesando

                            self.analysisStatus['largerPriceVolume'] = largerCandle
                            self.analysisStatus['minPrice'] = sortedValues[len(sortedValues) - 1]

                            consolidation = self.checkPriceConsolidation(periodValues,
                                                                         sortedValues[len(sortedValues) - 1],
                                                                         not bool(lastEmaStatus['type']))
                            self.analysisStatus['consolidation'] = consolidation

                            if consolidation:

                                nmp = self.getNextMarkerPrice(float(lastCandle[4]), '>')

                                if float(lastCandle[4]) / nmp['value'][0] <= 0.95 and float(lastCandle[4]) / float(
                                        sortedValues[len(sortedValues) - 1][4]) <= 1.05:

                                    self.currentPriceMark = nmp['value'][0]
                                    self.analysisStatus['priceMarked'] = nmp['value'][0]

                                elif float(lastCandle[4]) / float(largerCandle[4]) <= 1.05:

                                    value1 = (float(largerCandle[4]) + float(largerCandle[3])) / 2

                                    if value1 < float(sortedValues[len(sortedValues) - 1][4]) and value1 / float(
                                            lastCandle[4]) >= 1.05:
                                        self.currentPriceMark = value1
                                        self.analysisStatus['priceMarked'] = self.currentPriceMark

                                else:

                                    self.currentPriceMark = float(sortedValues[len(sortedValues) - 1][4])
                                    self.analysisStatus['priceMarked'] = float(sortedValues[len(sortedValues) - 1][4])

        elif (patternData['positive']['status'] is True and patternData['negative']['status'] is False) and \
                lastEmaStatus['type'] == 1:

            # Obtendremos los datos de la anterior tendencia para ver cuanto subio desde la minima hasta
            # la ultima actual

            previousTrendData = self.getPreviousTrendData(lastEmaStatus)

        print(self.analysisStatus)

    def getPreviousTrendData(self, guide: dict):

        previous = self.emaCrosses[self.emaCrosses.index(guide) - 1]

        period = self.getTrendData(previous['data']['date'], guide['data']['date'])

    def getPeriodData(self, start: int, end: int):

        values = []

        self.klines.reverse()
        for item in self.klines:

            if start <= item[6] <= end:
                values.append(item)

        self.klines.reverse()
        values.reverse()

        return values

    def getTrendData(self, bfEmaCross: int, currentEmaCross: int, end: int, trendDirection: int):

        periodValues = []

        bfPeriodData = self.getPeriodData(bfEmaCross, currentEmaCross)
        minCandle = self.getHistoricalMinClosePrice(bfPeriodData)
        maxCandle = self.getHistoricalMaxClosePrice(bfPeriodData)

        self.klines.reverse()
        for item in self.klines:

            if currentEmaCross <= item[6] <= end:

                periodValues.append(item)

            elif bfEmaCross <= item[6] < currentEmaCross:

                periodValues.append(item)

                if item == minCandle and bool(trendDirection):
                    break

                elif item == maxCandle and not bool(trendDirection):
                    break

        self.klines.reverse()
        periodValues.reverse()
        return periodValues

    def getAnEmaValue(self, date: int, index: int = 0):

        dif = 49
        value = []
        _index = 0

        if bool(index):

            value99 = self.ema99[index]
            value50 = self.ema50[index + dif]

            if value99['date'] == date and value50['date'] == date:
                value.append(value50)
                value.append(value99)
                _index = index

        else:
            for item in self.ema99:

                if item['date'] == date:

                    value50 = self.ema50[self.ema99.index(item) + dif]

                    if value50['date'] == date:
                        value.append(value50)
                        value.append(item)
                        _index = self.ema99.index(item)

                    break

        return {
            'emaValues': value,
            'index': _index
        }

    def candlePattern(self, entry: list, higherPercentage: float = 1.05, minorPercentage: float = 0.95):

        data = self.calculateSupportsAndResistors(entry, 'CLOSE', True)

        positiveData = []
        negativeData = []
        positiveStatus = None
        negativeStatus = None

        for item in data:

            item['status'] = None

            # Si el precio marcado con respecto al anterior es positivo
            if item['type'] == 'positive':

                if len(positiveData) >= 1:

                    value1 = positiveData[len(positiveData) - 1]['value'][0]

                    value2 = item['value'][0]

                    # Si la razon entre el anterior precio positivo y el actual es mayor o igual a 5%
                    # -- Si el precio anterior es mas grande en un 5%, que el actual --

                    # O si la razon entre los anteriores es menor o igual a -5%
                    # -- Si el precio anterior es mas chico en un 5%, que el actual --

                    if value1 / value2 >= higherPercentage:

                        item['status'] = False

                    elif value1 / value2 <= minorPercentage:

                        item['status'] = True

                positiveData.append(item)

            elif item['type'] == 'negative':

                if len(negativeData) >= 1:

                    value1 = negativeData[len(negativeData) - 1]['value'][0]

                    value2 = item['value'][0]

                    # Si la razon entre el anterior precio negativo y el actual es mayor o igual a 5%
                    # -- Si el precio anterior es mas grande en un 5%, que el actual --

                    # O si la razon entre los anteriores es menor o igual a -5%
                    # -- Si el precio anterior es mas chico en un 5%, que el actual --

                    if value1 / value2 >= higherPercentage:

                        item['status'] = True

                    elif value1 / value2 <= minorPercentage:

                        item['status'] = False

                negativeData.append(item)

        for item in positiveData:

            if item['status'] is None:

                if positiveStatus == False:

                    continue

                else:
                    positiveStatus = None

            elif item['status']:

                if positiveStatus == False:

                    positiveStatus = None

                elif positiveStatus == True:

                    continue

                else:
                    positiveStatus = True

            elif not item['status']:

                if positiveStatus == True:

                    positiveStatus = None

                elif positiveStatus == False:

                    continue

                else:
                    positiveStatus = False

        for item in negativeData:

            if item['status'] is None:

                if negativeStatus == False:

                    continue

                else:
                    negativeStatus = None

            elif item['status']:

                if negativeStatus == True:
                    continue

                elif negativeStatus == False:

                    negativeStatus = None

                else:
                    negativeStatus = True

            elif not item['status']:

                if negativeStatus == True:

                    negativeStatus = None

                elif negativeStatus == False:
                    continue

                else:
                    negativeStatus = False

        return {
            'positive': {
                'status': positiveStatus,
                'data': positiveData
            },
            'negative': {
                'status': negativeStatus,
                'data': negativeData
            }
        }

    def checkPriceConsolidation(self, entry: list, primaryCandle: list, trend: bool):

        # Primary candle allows to identify the opposite candles after it
        # La vela principal permite identificar las velas opuestas despues de esta

        if entry.index(primaryCandle) < len(entry) - 3:

            if not trend:

                if float(primaryCandle[4]) / float(entry[entry.index(primaryCandle) + 1][4]) < 1 and float(
                        primaryCandle[4]) / float(entry[entry.index(primaryCandle) + 1][4]) < 1:

                    return True

                else:

                    return False
            elif trend:

                if float(primaryCandle[4]) / float(entry[len(entry) - 1][4]) > 1 and (len(entry) - 1) - entry.index(
                        primaryCandle) >= 2:

                    return True

                else:

                    return False

    @staticmethod
    def printQuotedPrice(data):

        print(data)

    @staticmethod
    def getEmaCrosses(periods, entries):
        values = []
        index = 0
        for item in entries[0]:

            value = entries[1][index]

            if value['date'] > item['date']:

                continue

            elif value['date'] < item['date']:

                for i in entries[1]:

                    if i['date'] == item['date']:
                        value = i
                        break

            if len(entries[1]) == index:
                continue

            if value['value'] > item['value']:

                if len(values) < 1:
                    values.append({
                        'data': [item, value],
                        'type': 0
                    })
                    index += 1
                    continue

                elif values[len(values) - 1]['type'] == 1:
                    values.append({
                        'data': [item, value],
                        'type': 0
                    })
            elif value['value'] < item['value']:

                if len(values) < 1:
                    values.append({
                        'data': [item, value],
                        'type': 1
                    })
                    index += 1
                    continue

                elif values[len(values) - 1]['type'] == 0:
                    values.append({
                        'data': [item, value],
                        'type': 1
                    })

            index += 1

        return values

    def getNextMaxQuotedPrice(self, entry, condition):

        nmqp = []
        res = None
        value = None

        if condition == '>':

            for item in self.volumeProfile:

                if item['value'][0] > entry:
                    nmqp.append(item)

        elif condition == '<':

            for item in self.volumeProfile:

                if item['value'][0] < entry:
                    nmqp.append(item)

        for item in nmqp:

            if value is None:
                value = item

                res = entry - item['value'][0]

                continue

            a = entry - item['value'][0]

            if a < res and a >= 0:
                value = item
                res = a

        return value

    def getNextQuotedPrice(self, entry, condition):

        nqp = None
        res = None

        if condition == '>':

            for item in self.volumeProfile:

                if nqp is None:

                    nqp = item

                    res = nqp['value'][0] - entry

                    if res < 0:
                        res = res * -1

                    continue

                a = item['value'][0] - entry

                if a < res and a >= 0:
                    nqp = item
                    res = a

        elif condition == '<':

            for item in self.volumeProfile:

                if nqp is None:

                    nqp = item

                    res = entry - nqp['value'][0]

                    if res < 0:
                        res = res * -1

                    continue

                a = entry - item['value'][0]

                if a < res and a >= 0:
                    nqp = item
                    res = a

        return nqp

    def getNextMarkerPrice(self, entry, condition, upPercentage: float = 0.0, downPercentage: float = 0.0, isVolume: bool = True):

        nmp = None
        res = None

        if condition == '>':

            for item in self.markersClose:

                if nmp is None:

                    nmp = item

                    res = nmp['value'][0] - entry

                    continue

                a = item['value'][0] - entry

                if res < a >= 0 and downPercentage != 0 and upPercentage != 0:

                    if isVolume and float(item['volume'][0]) <= self.averageVolume:
                        continue

                    if upPercentage >= item['value'][0] / entry >= downPercentage:
                            nmp = item
                            res = a

                elif (res * -1 if res < 0 else res) > a >= 0 and downPercentage != 0:

                    if item['value'][0] / entry >= downPercentage:
                        nmp = item
                        res = a

        elif condition == '<':

            for item in self.markersClose:

                if nmp is None:

                    nmp = item

                    res = entry - nmp['value'][0]

                    continue

                a = entry - item['value'][0]

                if res < a >= 0 and downPercentage != 0 and upPercentage != 0:

                    if isVolume and float(item['volume'][0]) <= self.averageVolume:
                        continue

                    if downPercentage <= item['value'][0] / entry <= upPercentage:
                        nmp = item
                        res = a

                elif (res * -1 if res < 0 else res) > a >= 0 and upPercentage != 0:

                    if item['value'][0] / entry <= upPercentage:
                        nmp = item
                        res = a

        return nmp

    def checkBreakEma(self, entry: list, sortedValues: list):

        values = {
            "ema50": {
                "start": {
                    "isCross": False
                },
                "end": {
                    "isCross": False
                },
                "max": {
                    "isCross": False
                },
                "min": {
                    "isCross": False
                }
            },
            "ema99": {
                "start": {
                    "isCross": False
                },
                "end": {
                    "isCross": False
                },
                "max": {
                    "isCross": False
                },
                "min": {
                    "isCross": False
                }
            }
        }

        # If result is negative because the price is below the Ema50
        # Si el resultado es negtivo es porque el precio esta por debajo de la EMA50
        startRes = float(entry[0][4]) - self.ema50[len(self.ema50) - 1]['value']
        endRes = float(entry[len(entry) - 1][4]) - self.ema50[len(self.ema50) - 1]['value']
        maxRes = float(sortedValues[0][4]) - self.ema50[len(self.ema50) - 1]['value']
        minRes = float(sortedValues[len(sortedValues) - 1][4]) - self.ema50[len(self.ema50) - 1]['value']

        # Is true when it's below the EMA, and false when it's above the EMA
        # Es true cuando esta por debajo de la EMA, y false cuando esta por encima de la EMA
        values["ema50"]["start"]["isCross"] = True if startRes < 0 else False
        values['ema50']['end']['isCross'] = True if endRes < 0 else False
        values['ema50']['max']['isCross'] = True if maxRes < 0 else False
        values['ema50']['min']['isCross'] = True if minRes < 0 else False

        startRes = float(entry[0][4]) - self.ema99[len(self.ema99) - 1]['value']
        endRes = float(entry[len(entry) - 1][4]) - self.ema99[len(self.ema99) - 1]['value']
        maxRes = float(sortedValues[0][4]) - self.ema99[len(self.ema99) - 1]['value']
        minRes = float(sortedValues[len(sortedValues) - 1][4]) - self.ema99[len(self.ema99) - 1]['value']

        values['ema99']['start']['isCross'] = True if startRes < 0 else False
        values['ema99']['end']['isCross'] = True if endRes < 0 else False
        values['ema99']['max']['isCross'] = True if maxRes < 0 else False
        values['ema99']['min']['isCross'] = True if minRes < 0 else False

        return values

    def getLargerCandle(self, entry: list, trend: bool):
        # Entry (binance klines); trend (True = bull, False = bear)

        afterValue = None

        for item in entry:

            if trend:

                print('hola')

            elif not trend:

                if afterValue is None:
                    afterValue = item

                    continue

                gap = float(item[1]) - float(item[3])

                if gap > (float(afterValue[1]) - float(afterValue[3])):
                    afterValue = item

        return afterValue

    def getLargerVolumeCandle(self, entry: list, startDate: int, endDate: int = 0):

        afterValue = None

        for item in entry:

            if afterValue is None:
                if (endDate if bool(endDate) else item[6]) >= item[6] >= startDate:
                    afterValue = item

                continue

            if float(afterValue[5]) < float(item[5]) and (endDate if bool(endDate) else item[6]) >= item[6] >= startDate:
                afterValue = item
            elif not (endDate if bool(endDate) else item[6]) >= item[6]:
                break

        return afterValue

    def getDMI(self, entry: list, n: int):

        dm = self.getDM(entry)
        tr = self.getTrueRange(entry)
        DIs, ADX = self.calculateDMIValues(dm, tr, n)

        values = []
        adxIndex = None

        for item in DIs:

            if item['date'] == ADX[0]['date']:

                values.append({
                    'date': item['date'],
                    'DI': {
                        'positive': item['value']['positive'],
                        'negative': item['value']['negative']
                    },
                    'ADX': ADX[0]['value']
                })

                adxIndex = 1

            elif not (adxIndex is None) and ADX[adxIndex if not (adxIndex is None) else 0]['date'] == item['date']:

                values.append({
                    'date': item['date'],
                    'DI': {
                        'positive': item['value']['positive'],
                        'negative': item['value']['negative']
                    },
                    'ADX': ADX[adxIndex]['value']
                })

                adxIndex += 1

        return values

    def getDM(self, entry: list):

        values = []

        for item in entry:

            if not bool(entry.index(item)):
                continue

            lastItem = entry[entry.index(item) - 1]

            PDM, NDM = self.calculateDM(float(item[2]), float(lastItem[2]), float(item[3]), float(lastItem[3]))

            values.append({
                'data': item,
                'type': self.classifyDM(PDM, NDM),
                'date': item[6],
                'value': {
                    'positive': PDM,
                    'negative': NDM
                }
            })

        return values

    def classifyDM(self, moveUp: float, moveDown: float):

        if 0 < moveUp > moveDown:
            return 1

        elif 0 < moveDown > moveUp:
            return 0

        else:
            return None

    def calculateDM(self, h, yh, l, yl):

        moveUp = h - yh
        moveDown = yl - l

        if moveUp > moveDown:
            if moveUp < 0:
                moveUp = 0.00
            moveDown = 0.00

        if moveUp < moveDown:
            if moveDown < 0:
                moveDown = 0.00
            moveUp = 0.00

        return moveUp, moveDown

    def getTrueRange(self, entry):

        values = []

        for item in entry:

            if not bool(entry.index(item)):
                continue

            lastItem = entry[entry.index(item) - 1]

            x = float(item[2]) - float(item[3])
            y = abs(float(item[2]) - float(lastItem[4]))
            z = abs(float(item[3]) - float(lastItem[4]))

            var = [x, y, z]

            values.append({
                'value': max(var),
                'date': item[6]
            })

        return values

    def calculateDMIValues(self, DMs: list, TRs: list, n: int):

        # First it calculated with Wilder's Smoothing technique

        trIndex = None
        xDMs = []
        TrueRanges = []
        DIs = []
        DXs = []
        ADX = []

        for item in DMs:

            trItem = TRs[DMs.index(item) if trIndex is None else trIndex]

            if trItem['date'] > item['date']:
                if trIndex is None:
                    trIndex = DMs.index(item)
                continue

            elif trItem['date'] < item['date']:

                for tr in TRs:

                    if tr['date'] == item['date']:
                        trItem = tr
                        break

            if DMs.index(item) + 1 == n:

                trValue = self.firstAverageDMI(TRs, TRs.index(trItem), n, 'TR')
                TrueRanges.append({
                    'date': trItem['date'],
                    'value': trValue
                })

                posDMValue = self.firstAverageDMI(DMs, DMs.index(item), n, '+DM')
                negDMValue = self.firstAverageDMI(DMs, DMs.index(item), n, '-DM')

                xDMs.append({
                    'date': item['date'],
                    'value': {
                        'positive': posDMValue,
                        'negative': negDMValue
                    }
                })

            elif DMs.index(item) + 1 >= n:

                trValue = round(self.calcSubsequentDMI(TrueRanges, trItem['value'], n, 'TR'), 2)
                TrueRanges.append({
                    'date': trItem['date'],
                    'value': trValue
                })

                posDMValue = round(self.calcSubsequentDMI(xDMs, item['value']['positive'], n, '+DM'), 2)
                negDMValue = round(self.calcSubsequentDMI(xDMs, item['value']['negative'], n, '-DM'), 2)

                xDMs.append({
                    'date': item['date'],
                    'type': 1 if posDMValue > 0 else 0,
                    'value': {
                        'positive': posDMValue,
                        'negative': negDMValue
                    }
                })

                posDIValue = round((posDMValue / trValue) * 100, 2)
                negDIValue = round((negDMValue / trValue) * 100, 2)

                DIs.append({
                    'date': item['date'],
                    'value': {
                        'positive': posDIValue,
                        'negative': negDIValue
                    }
                })

                a = abs(posDIValue - negDIValue)
                b = abs(posDIValue + negDIValue)
                DXValue = None

                if b != 0:
                    DXValue = (a / b) * 100

                else:
                    DXValue = 0 * 100

                DXs.append({
                    'date': item['date'],
                    'value': DXValue
                })

                if len(DXs) == n:

                    ADXValue = self.calcFirstADX(DXs, n, len(DXs) - 1)
                    ADX.append({
                        'date': item['date'],
                        'value': ADXValue
                    })
                elif len(DXs) >= n:

                    ADXValue = self.calcADX(ADX, DXValue, n)
                    ADX.append({
                        'date': item['date'],
                        'value': ADXValue
                    })

        return DIs, ADX

    def firstAverageDMI(self, entry: list, index: int, n: int, t: str):

        result = 0

        for i in range(index - (n - 1), index + 1):

            item = entry[i]
            value = item['value']

            if t == 'TR':

                result += value

            elif t == '+DM':

                result += value['positive']

            elif t == '-DM':

                result += value['negative']

        return result

    def calcSubsequentDMI(self, entry: list, currentValue: float, n: int, t: str):

        res = None

        if t == 'TR':

            res = entry[len(entry) - 1]['value'] - (entry[len(entry) - 1]['value'] / n) + currentValue

        elif t == '+DM':

            res = entry[len(entry) - 1]['value']['positive'] - (
                    entry[len(entry) - 1]['value']['positive'] / n) + currentValue

        elif t == '-DM':

            res = entry[len(entry) - 1]['value']['negative'] - (
                    entry[len(entry) - 1]['value']['negative'] / n) + currentValue

        return res

    def calcFirstADX(self, DXs: list, n: int, index: int):

        result = 0

        for i in range(index - (n - 1), index + 1):
            result += DXs[i]['value']

        return result / n

    def calcADX(self, ADX: list, currentValueDX: float, n: int):

        return round(((ADX[len(ADX) - 1]['value'] * (n - 1)) + currentValueDX) / n, 2)

    def expMovingAverage(self, values, n):
        weights = np.exp(np.linspace(-1., 0., n))
        weights /= weights.sum()
        a = np.convolve(values, weights, mode='full')[:len(values)]
        a[:n] = a[n]
        return a

if __name__ == '__main__':
    date = datetime.datetime.now()
    ts = date.timestamp()
    ts = ts * 1000
    date = datetime.datetime.fromtimestamp((ts - 86400000) / 1000)
    # f'{date.strftime("%d")} {date.strftime("%b")}, {date.strftime("%Y")}'
    bot = ModelTools('BTCUSDT', "16 Aug, 2016", "07 Mar, 2022")

    twm = ThreadedWebsocketManager()
    twm.start


    def handle_socket_message(msg):
        print(f"message type: {msg['e']}")
        print(msg)


    twm.start_options_kline_socket(callback=handle_socket_message, symbol='BTCUSD')
    twm.join()


    async def runTrade():
        async with websockets.connect("wss://stream.binance.com:9443/ws/btcbusd@trade", ) as websocket:
            while True:
                time.sleep(1)
                data = await websocket.recv()
                bot.printQuotedPrice(data)


    asyncio.run(runTrade())
