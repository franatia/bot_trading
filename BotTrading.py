import json
import urllib.parse

import numpy
import datetime
from binance import Client
from binance import AsyncClient, BinanceSocketManager
import pandas as pd
import mplfinance as mplf
from BotData import BotData
from pymongo import MongoClient
from MongoDB import MongoDB
import time

MONGO_STRING = 'mongodb+srv://admin_1:aa74b6474add49868a695bcc3155e426@cluster0.umgwskd.mongodb.net/test?authSource=admin&replicaSet=atlas-qw1msu-shard-0&readPreference=primary&appname=MongoDB%20Compass&ssl=true'
mongo_db = MongoDB(MONGO_STRING)

class BotTrading(BotData):
    def __init__(self, currency: str, start_day: str or int, end_day: str or int, interval, strategy: int,
                 usd_test: float, leverage: int, user_key: str, secret_key: str, first_period_ema, second_period_ema):
        super().__init__(currency, start_day, end_day, interval, user_key, secret_key, first_period_ema,
                         second_period_ema)
        self.strategy = strategy

        self.usd_test = usd_test
        self.leverage = leverage

        self.patrimony = usd_test

        self.client_socket: AsyncClient = None
        self.bm: BinanceSocketManager = None

        self.trade_in_ex = False
        self.trade_data = None

        self.trades_history = []
        self.losses = 0
        self.won = 0
        self.total_trades = 0

        self.first = True

        self.rsi_type = None
        self.rsi_item_guide = None
        self.dmi_item_guide = None
        self.adx_trade = False

        self.symbol_n_precision = 0
        self.price = 0

        self.get_n_precision()

    def get_n_precision(self):
        info = self.binance_client.futures_exchange_info()

        for item in info['symbols']:
            if item['symbol'] != self.currency:
                continue

            self.symbol_n_precision = item['quantityPrecision']


    def run_strategy_test(self):
        if self.strategy == 3:
            self.run_strategy_three_test()

    def run_strategy_three_test(self):

        self.rsi_type = None
        self.rsi_item_guide = None
        self.dmi_item_guide = None
        self.adx_trade = False

        for i in range(int(len(self.klines) * .2), len(self.klines)):
            kline = self.klines[i]
            rsi_ = self.rsi[i - 14] if i >= 14 else None
            dmi_ = self.dmi[i - 28] if i >= 28 else None

            if rsi_ is None or dmi_ is None:
                continue
            if rsi_['ma'] == 'nan':
                continue

            if self.trade_in_ex:
                self.calc_trade(kline)
                if self.trade_in_ex:
                    continue
                self.rsi_type = None

            if kline[6] == 1671507299999:
                print('date-call')

            if rsi_['rsi'] >= 70 and 60 <= rsi_['ma'] and (
                    self.rsi_type is None or self.rsi_type == 0 or self.rsi_type == 2 or self.rsi_type == 3):
                self.rsi_type = 1
                self.rsi_item_guide = rsi_
                self.dmi_item_guide = dmi_
                continue
            elif rsi_['rsi'] <= 30 and 40 >= rsi_['ma'] and (
                    self.rsi_type is None or self.rsi_type == 1 or self.rsi_type == 3 or self.rsi_type == 2):
                self.rsi_type = 0
                self.rsi_item_guide = rsi_
                self.dmi_item_guide = dmi_
                continue

            if self.rsi_type == 1:
                if self.rsi[self.rsi.index(rsi_) - 1] == self.rsi_item_guide or self.adx_trade:
                    if rsi_['rsi'] < self.rsi_item_guide['rsi'] or self.adx_trade:
                        marker_dmi = self.model_tools.get_dmi_marker_by_date(kline[6])
                        ema_cross = self.model_tools.get_ema_cross_after_by_date(kline[6])

                        if marker_dmi is None or ema_cross is None:
                            continue

                        after_marker_dmi = self.dmi_markers[
                            self.dmi_markers.index(marker_dmi) - 1 if marker_dmi is not None and self.dmi_markers.index(
                                marker_dmi) - 1 is not None else 0]

                        if marker_dmi is not None and after_marker_dmi is not None and marker_dmi['DI']['date'] - \
                                after_marker_dmi['DI']['date'] <= 300000 * 50:

                            kline_m = self.get_kline_liquidate_marker(marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                    self.dmi_markers.index(
                                                                                                        marker_dmi) - 1][
                                                                                                    'DI'][
                                                                                                    'date'] or 300000 * 10 if
                            marker_dmi['ADX'] is None else marker_dmi['ADX']['date'], marker_dmi['DI']['type'])
                            kline_am = self.get_kline_liquidate_marker(after_marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                           self.dmi_markers.index(
                                                                                                               marker_dmi) - 1][
                                                                                                           'DI'][
                                                                                                           'date'] or 300000 * 10 if
                            after_marker_dmi['ADX'] is None else after_marker_dmi['ADX']['date'],
                                                                       after_marker_dmi['DI']['type'])

                            if self.check_dmi_params(40, i - 29, 'positive') and self.verify_distance_between_ema(1.002,
                                                                                                                  0.998,
                                                                                                                  kline[
                                                                                                                      6],
                                                                                                                  1) and (
                            False if marker_dmi['DI']['value'] >= 55 else (
                                    marker_dmi['DI']['value'] < after_marker_dmi['DI']['value'] and float(
                                    kline_m[4]) > float(kline_am[4]))) and marker_dmi['DI']['type'] == \
                                    after_marker_dmi['DI']['type']:
                                r_ = self.get_next_resistance(kline, [1.030, 1.025])

                                sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                                tp = (1 - abs((1 - (sl / float(kline[4]))) * 1.5)) * float(kline[4])
                                tp = round(tp, 2)

                                self.set_trade_data(float(kline[4]), tp, sl, 'SHORT', self.usd_test, self.leverage,
                                                    kline[6], 'DMI')
                            elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                                self.dmi_item_guide = dmi_
                                self.adx_trade = True
                            elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                                'positive'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross['type'] == 1:
                                s_ = self.get_next_support(kline, [0.970, 0.975])

                                sl = round(s_ if s_ is not None else float(kline[4]) * 0.970, 2)
                                tp = (1 + ((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                                tp = round(tp, 2)

                                self.set_trade_data(float(kline[4]), tp, sl, 'LONG', self.usd_test, self.leverage,
                                                    kline[6])
                                self.adx_trade = False
                            else:
                                self.rsi_type = None
                                self.rsi_item_guide = None
                                self.adx_trade = False
                        elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                            self.dmi_item_guide = dmi_
                            self.adx_trade = True
                        elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                            'positive'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross['type'] == 1:
                            s_ = self.get_next_support(kline, [0.970, 0.975])

                            sl = round(s_ if s_ is not None else float(kline[4]) * 0.970, 2)
                            tp = (1 + ((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                            tp = round(tp, 2)

                            self.set_trade_data(float(kline[4]), tp, sl, 'LONG', self.usd_test, self.leverage, kline[6])
                            self.adx_trade = False
                        else:
                            self.rsi_type = None
                            self.rsi_item_guide = None
                            self.adx_trade = False
                    else:
                        self.rsi_item_guide = rsi_
                        continue
            elif self.rsi_type == 0:
                if self.rsi[self.rsi.index(rsi_) - 1] == self.rsi_item_guide or self.adx_trade:
                    if rsi_['rsi'] > self.rsi_item_guide['rsi'] or self.adx_trade:
                        marker_dmi = self.model_tools.get_dmi_marker_by_date(kline[6])
                        ema_cross = self.model_tools.get_ema_cross_after_by_date(kline[6])

                        if marker_dmi is None or ema_cross is None:
                            continue

                        after_marker_dmi = self.dmi_markers[
                            self.dmi_markers.index(marker_dmi) - 1 if marker_dmi is not None and self.dmi_markers.index(
                                marker_dmi) - 1 is not None else 0]

                        if marker_dmi is not None and after_marker_dmi is not None and marker_dmi['DI']['date'] - \
                                after_marker_dmi['DI']['date'] <= 300000 * 50:

                            kline_m = self.get_kline_liquidate_marker(marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                    self.dmi_markers.index(
                                                                                                        marker_dmi) - 1][
                                                                                                    'DI'][
                                                                                                    'date'] or 300000 * 10 if
                            marker_dmi['ADX'] is None else marker_dmi['ADX']['date'], marker_dmi['DI']['type'])
                            kline_am = self.get_kline_liquidate_marker(after_marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                           self.dmi_markers.index(
                                                                                                               marker_dmi) - 1][
                                                                                                           'DI'][
                                                                                                           'date'] or 300000 * 10 if
                            after_marker_dmi['ADX'] is None else after_marker_dmi['ADX']['date'],
                                                                       after_marker_dmi['DI']['type'])

                            if self.check_dmi_params(40, i - 29, 'negative') and self.verify_distance_between_ema(1.002,
                                                                                                                  0.998,
                                                                                                                  kline[
                                                                                                                      6],
                                                                                                                  0) and self.verify_distance_between_ema(
                                    1.002, 0.998, kline[6], 1) and (False if marker_dmi['DI']['value'] >= 55 else (
                                    marker_dmi['DI']['value'] < after_marker_dmi['DI']['value'] and float(
                                    kline_m[4]) > float(kline_am[4]))) and marker_dmi['DI']['type'] == \
                                    after_marker_dmi['DI']['type']:
                                s_ = self.get_next_support(kline, [0.970, 0.975])

                                sl = round(s_ if s_ is not None else float(kline[4]) * 0.975, 2)
                                tp = (1 + ((1 - (sl / float(kline[4]))) * 1.5)) * float(kline[4])
                                tp = round(tp, 2)

                                self.set_trade_data(float(kline[4]), tp, sl, 'LONG', self.usd_test, self.leverage,
                                                    kline[6], 'DMI')
                            elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                                self.dmi_item_guide = dmi_
                                self.adx_trade = True
                            elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                                'negative'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross['type'] == 0:
                                r_ = self.get_next_resistance(kline, [1.030, 1.025])

                                sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                                tp = (1 - abs((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                                tp = round(tp, 2)

                                self.set_trade_data(float(kline[4]), tp, sl, 'SHORT', self.usd_test, self.leverage,
                                                    kline[6])

                                self.adx_trade = False
                            else:
                                self.rsi_type = None
                                self.rsi_item_guide = None
                                self.adx_trade = False
                        elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                            self.dmi_item_guide = dmi_
                            self.adx_trade = True
                        elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                            'negative'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross['type'] == 0:
                            r_ = self.get_next_resistance(kline, [1.030, 1.025])

                            sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                            tp = (1 - abs((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                            tp = round(tp, 2)

                            self.set_trade_data(float(kline[4]), tp, sl, 'SHORT', self.usd_test, self.leverage,
                                                kline[6])

                            self.adx_trade = False
                        else:
                            self.rsi_type = None
                            self.rsi_item_guide = None
                            self.adx_trade = False
                    else:
                        self.rsi_item_guide = rsi_
                        continue

    def verify_distance_between_ema(self, bull_percentage, bear_percentage, d: int, t: int):

        self.first_ema.reverse()
        self.second_ema.reverse()

        bl = False

        for i in range(0, len(self.second_ema)):

            f_item = self.first_ema[i]
            s_item = self.second_ema[i]

            if f_item['date'] < d or s_item['date'] < d:
                break

            if f_item['date'] != d or s_item['date'] != d:
                break

            if t == 0 and round(f_item['value'] / s_item['value'], 3) <= bear_percentage:

                bl = True

            elif t == 1 and bull_percentage <= round(f_item['value'] / s_item['value'], 3):

                bl = True

        self.first_ema.reverse()
        self.second_ema.reverse()

        return bl

    def get_kline_liquidate_marker(self, d_start: int, d_end: int, t: int):

        kline_ = None

        for i in self.klines:

            if d_start <= i[6] <= d_end or i[6] == d_end or i[0] == d_start:
                if kline_ is None:
                    kline_ = i
                    return

                if t == 0:

                    kline_ = i if float(i[4]) / float(kline_[4]) < 1 else kline_

                elif t == 1:

                    kline_ = i if float(i[4]) / float(kline_[4]) > 1 else kline_

            elif i[6] > d_end:
                break

        return kline_

    def check_if_zone_liquidated(self, kline_guide, kline_end, t):

        klines = self.model_tools.get_klines_between_dates(kline_guide[6], kline_end[6] - (300000 * 5))

        liquidated = False

        for item in klines:

            if item == kline_guide or item[6] - kline_guide[6] < 300000 * 4:
                return

            if float(item[4]) / float(kline_guide[4]) >= 0.9990 and t == 1:
                liquidated = True
                break
            elif float(item[4]) / float(kline_guide[4]) <= 1.001 and t == 0:
                liquidated = True
                break

        return liquidated

    def if_in_liquidate_zone(self, d: int):

        five_min = 300000

        marker = self.model_tools.get_dmi_marker_by_date(d)

        divergence = False

        self.dmi_markers.reverse()

        if not (marker is None):

            for item in self.dmi_markers:
                if five_min < d - item['DI']['date'] <= five_min * 250 and 50 <= item['DI']['value'] and \
                        item['DI']['type'] == marker['DI']['type']:

                    kline_date = self.model_tools.get_kline_by_date(marker['DI']['date'])
                    kline_dmi = self.get_kline_liquidate_marker(item['DI']['date'],
                                                                self.dmi_markers[self.dmi_markers.index(item) - 1][
                                                                    'DI']['date'] or five_min * 10 if item[
                                                                                                          'ADX'] is None else
                                                                item['ADX']['date'], item['DI']['type'])

                    if not (self.check_if_zone_liquidated(kline_dmi, kline_date, marker['DI']['type'])) and (
                            1.004 >= float(kline_date[4]) / float(kline_dmi[4]) >= 0.996 or (
                    1.004 >= float(kline_date[4]) / float(kline_dmi[2]) >= 0.996 if item['DI'][
                                                                                        'type'] == 1 else 1.004 >= float(
                            kline_date[4]) / float(kline_dmi[3]) >= 0.996)):
                        divergence = True

                elif five_min < d - item['DI']['date'] <= five_min * 250 and 50 <= item['DI']['value'] and \
                        item['DI']['type'] != marker['DI']['type']:

                    kline_date = self.model_tools.get_kline_by_date(marker['DI']['date'])
                    kline_dmi = self.get_kline_liquidate_marker(item['DI']['date'],
                                                                self.dmi_markers[self.dmi_markers.index(item) - 1][
                                                                    'DI']['date'] or five_min * 10 if item[
                                                                                                          'ADX'] is None else
                                                                item['ADX']['date'], item['DI']['type'])

                    if kline_date is None or kline_dmi is None:
                        break

                    if 1.004 >= float(kline_date[4]) / float(kline_dmi[4]) >= 0.996 or (
                    1.004 >= float(kline_date[4]) / float(kline_dmi[2]) >= 0.996 if item['DI'][
                                                                                        'type'] == 1 else 1.004 >= float(
                            kline_date[4]) / float(kline_dmi[3]) >= 0.996):
                        divergence = True

                elif 0 < d - item['DI']['date'] > five_min * 200:
                    break

        self.dmi_markers.reverse()

        return divergence

    def if_di_in_other_trend(self, d: int):

        five_min = 300000

        marker = self.model_tools.get_dmi_marker_by_date(d)

        divergence = False

        self.dmi_markers.reverse()

        if not (marker is None):

            for item in self.dmi_markers:

                if five_min < d - item['DI']['date'] <= five_min * 250 and 55 <= item['DI']['value'] > marker['DI'][
                    'value'] and \
                        item['DI']['type'] != marker['DI']['type']:
                    kline_date = self.model_tools.get_kline_by_date(marker['DI']['date'])
                    kline_dmi = self.get_kline_liquidate_marker(item['DI']['date'],
                                                                self.dmi_markers[self.dmi_markers.index(item) - 1][
                                                                    'DI']['date'] or five_min * 10 if item[
                                                                                                          'ADX'] is None else
                                                                item['ADX']['date'], item['DI']['type'])

                    if not (self.check_if_zone_liquidated(kline_dmi, kline_date, item['DI']['type'])):
                        divergence = True

                elif 0 < d - item['DI']['date'] > five_min * 250:
                    break

        self.dmi_markers.reverse()

        return divergence

    def has_marker_dmi(self, d):

        mr = self.model_tools.get_dmi_marker_by_date(d)

        if mr:
            return True
        else:
            return False

    def check_dmi_divergence(self, d: int, t: str, intra: bool = False):

        five_min = 300000

        marker = self.model_tools.get_dmi_marker_by_date(d)

        divergence = False

        self.dmi_markers.reverse()

        if not (marker is None):

            for item in self.dmi_markers:
                if five_min < d - item['DI']['date'] <= five_min * 250 and item['DI']['value'] > marker['DI'][
                    'value'] and item['DI']['type'] == marker['DI']['type']:
                    kline_date = self.model_tools.get_kline_by_date(d)
                    kline_dmi = self.model_tools.get_kline_by_date(item['DI']['date'])

                    if (float(kline_date[4]) > float(kline_dmi[4]) and t == 'positive') or (
                            float(kline_date[4]) < float(kline_dmi[4]) and t == 'negative'):
                        divergence = True

                elif five_min < d - item['DI']['date'] > five_min * 250:

                    if not divergence and self.intra_divergence_dmi(marker['DI']['date'], d,
                                                                    marker['DI']['type']) and intra:

                        kline_date = self.model_tools.get_kline_by_date(d)
                        kline_date = self.model_tools.get_kline_by_date(d - (kline_date[6] - kline_date[0]))

                        kline_dmi = self.model_tools.get_kline_by_date(marker['DI']['date'])

                        if (float(kline_date[4]) > float(kline_dmi[4]) and t == 'positive') or (
                                float(kline_date[4]) < float(kline_dmi[4]) and t == 'negative'):
                            divergence = True

                    break

        self.dmi_markers.reverse()

        return divergence

    def intra_divergence_dmi(self, d_start: int, d_end: int, t: int):

        dmi_items = []

        self.dmi.reverse()

        for i in self.dmi:
            if d_end >= i['date'] >= d_start:
                dmi_items.append(i)
            elif i['date'] < d_start:
                break

        self.dmi.reverse()

        dmi_items.reverse()

        if len(dmi_items) < 3:
            return

        prc = []

        for i in dmi_items:

            if i == dmi_items[0]:
                return

            prc.append(i['DI']['negative'] / dmi_items[0]['DI']['negative'] if t == 0 else i['DI']['positive'] /
                                                                                           dmi_items[0]['DI'][
                                                                                               'positive'])

            if dmi_items.index(i) == len(dmi_items) - 1:

                prm = 0

                for pr in prc:

                    prm += pr

                    if prc.index(pr) == len(prc) - 1:
                        prm = prm / len(prc)

                        prc = prm

        if prc > 1:

            return False

        elif prc < 1:

            return True

    def run_strategy(self):
        if self.strategy == 1:
            self.run_strategy_one()

    def check_active_trade(self):

        _t_k = list(self.trade_data.keys())

        _ema_cross = self.model_tools.get_ema_cross_after_by_date(self.klines[len(self.klines) - 1][6])

        _t = self.trade_data[_t_k[0]]

        _k = self.klines[len(self.klines) - 1]

        if _t['positionSide'] == 'LONG':

            if _t['sl_price'] >= float(_k[2]) or _t['sl_price'] >= float(_k[4]) or _t['tp_price'] <= float(_k[3]) or _t['tp_price'] <= float(_k[4]):
                for _i in self.trade_data:
                    self.trade_data[_i]['pnl'] = f'-{round((1-1+1-(self.trade_data[_i]["sl_price"] / self.trade_data[_i]["entry"])) * 100, 3)}%' if (_t['sl_price'] >= float(_k[2]) or _t['sl_price'] >= float(_k[4])) else f'+{round(((self.trade_data[_i]["tp_price"] / self.trade_data[_i]["entry"]) - 1) * 100, 3)}%'
                    self.trade_data[_i]['finish_date'] = _k[6]
                mongo_db.put_trades(self.trade_data)
                self.trade_data = None
                self.trade_in_ex = False
            elif _ema_cross['type'] == 0 if _t['type'] == 'ADX' else False:
                for _i in self.trade_data:
                    _tr = self.trade_data[_i]
                    _q = round((self.price / _tr['entry']) * _tr['amount'], self.symbol_n_precision)
                    _tr['client'].futures_create_order(symbol=self.currency, side='SELL', positionSide=_tr['positionSide'], type='MARKET', quantity=_q)
                    self.trade_data[_i]['pnl'] = f'-{round((1 - 1 + 1 - (self.trade_data[_i]["sl_price"] / self.trade_data[_i]["entry"])) * 100, 3)}%' if (_t['sl_price'] >= float(_k[2]) or _t['sl_price'] >= float(_k[4])) else f'+{round(((self.trade_data[_i]["tp_price"] / self.trade_data[_i]["entry"]) - 1) * 100, 3)}%'
                    self.trade_data[_i]['finish_date'] = _k[6]
                mongo_db.put_trades(self.trade_data)
                self.trade_data = None
                self.trade_in_ex = False

        elif _t['positionSide'] == 'SHORT':
            if _t['sl_price'] <= float(_k[3]) or _t['sl_price'] <= float(_k[4]) or _t['tp_price'] >= float(_k[2]) or _t['tp_price'] >= float(_k[4]):
                for _i in self.trade_data:
                    self.trade_data[_i]['pnl'] = f'-{round(((self.trade_data[_i]["sl_price"] / self.trade_data[_i]["entry"]) - 1) * 100, 3)}%' if (_t['sl_price'] <= float(_k[3]) or _t['sl_price'] <= float(_k[4])) else f'+{round((1-1+1-(self.trade_data[_i]["tp_price"] / self.trade_data[_i]["entry"])) * 100, 3)}%'
                    self.trade_data[_i]['finish_date'] = _k[6]
                mongo_db.put_trades(self.trade_data)
                self.trade_data = None
                self.trade_in_ex = False
            elif _ema_cross['type'] == 1 if _t['type'] == 'ADX' else False:
                for _i in self.trade_data:
                    _tr = self.trade_data[_i]
                    _q = round((1+1-(self.price / _tr['entry'])) * _tr['amount'], self.symbol_n_precision)
                    _tr['client'].futures_create_order(symbol=self.currency, side='BUY',
                                                       positionSide=_tr['positionSide'], type='MARKET', quantity=_q)
                    self.trade_data[_i]['pnl'] = f'-{round(((self.trade_data[_i]["sl_price"] / self.trade_data[_i]["entry"]) - 1) * 100, 3)}%' if (_t['sl_price'] <= float(_k[3]) or _t['sl_price'] <= float(_k[4])) else f'+{round((1 - 1 + 1 - (self.trade_data[_i]["tp_price"] / self.trade_data[_i]["entry"])) * 100, 3)}%'
                    self.trade_data[_i]['finish_date'] = _k[6]
                mongo_db.put_trades(self.trade_data)
                self.trade_data = None
                self.trade_in_ex = False


    def run_strategy_one(self):

        kline = self.klines[len(self.klines) - 1]
        rsi_ = self.rsi[len(self.rsi) - 1]
        dmi_ = self.dmi[len(self.dmi) - 1]

        if rsi_ is None or dmi_ is None:
            return
        if rsi_['ma'] == 'nan':
            return

        if self.trade_in_ex:
            self.check_active_trade()
            if self.trade_in_ex:
                return
            self.rsi_type = None

        if rsi_['rsi'] >= 70 and 60 <= rsi_['ma'] and (
                self.rsi_type is None or self.rsi_type == 0 or self.rsi_type == 2 or self.rsi_type == 3):
            self.rsi_type = 1
            self.rsi_item_guide = rsi_
            self.dmi_item_guide = dmi_
            return
        elif rsi_['rsi'] <= 30 and 40 >= rsi_['ma'] and (
                self.rsi_type is None or self.rsi_type == 1 or self.rsi_type == 3 or self.rsi_type == 2):
            self.rsi_type = 0
            self.rsi_item_guide = rsi_
            self.dmi_item_guide = dmi_
            return

        if self.rsi_type == 1:
            if self.rsi[self.rsi.index(rsi_) - 1] == self.rsi_item_guide or self.adx_trade:
                if rsi_['rsi'] < self.rsi_item_guide['rsi'] or self.adx_trade:
                    marker_dmi = self.model_tools.get_dmi_marker_by_date(kline[6])
                    ema_cross = self.model_tools.get_ema_cross_after_by_date(kline[6])

                    if marker_dmi is None or ema_cross is None:
                        return

                    after_marker_dmi = self.dmi_markers[
                        self.dmi_markers.index(marker_dmi) - 1 if marker_dmi is not None and self.dmi_markers.index(
                            marker_dmi) - 1 is not None else 0]

                    if marker_dmi is not None and after_marker_dmi is not None and marker_dmi['DI']['date'] - \
                            after_marker_dmi['DI']['date'] <= 300000 * 50:

                        kline_m = self.get_kline_liquidate_marker(marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                self.dmi_markers.index(
                                                                                                    marker_dmi) - 1][
                                                                                                'DI'][
                                                                                                'date'] or 300000 * 10 if
                        marker_dmi['ADX'] is None else marker_dmi['ADX']['date'], marker_dmi['DI']['type'])
                        kline_am = self.get_kline_liquidate_marker(after_marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                       self.dmi_markers.index(
                                                                                                           marker_dmi) - 1][
                                                                                                       'DI'][
                                                                                                       'date'] or 300000 * 10 if
                        after_marker_dmi['ADX'] is None else after_marker_dmi['ADX']['date'],
                                                                   after_marker_dmi['DI']['type'])

                        if self.check_dmi_params(40, self.klines.index(kline) - 29, 'positive') and self.verify_distance_between_ema(1.002,
                                                                                                              0.998,
                                                                                                              kline[
                                                                                                                  6],
                                                                                                              1) and (
                                False if marker_dmi['DI']['value'] >= 55 else (
                                        marker_dmi['DI']['value'] < after_marker_dmi['DI']['value'] and float(
                                    kline_m[4]) > float(kline_am[4]))) and marker_dmi['DI']['type'] == \
                                after_marker_dmi['DI']['type']:
                            r_ = self.get_next_resistance(kline, [1.030, 1.025])

                            sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                            tp = (1 - abs((1 - (sl / float(kline[4]))) * 1.5)) * float(kline[4])
                            tp = round(tp, 2)

                            self.ex_trade(float(kline[4]), tp, sl, 'SELL', 'SHORT', self.usd_test,
                                                kline[6])
                        elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                            self.dmi_item_guide = dmi_
                            self.adx_trade = True
                        elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                            'positive'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross[
                            'type'] == 1:
                            s_ = self.get_next_support(kline, [0.970, 0.975])

                            sl = round(s_ if s_ is not None else float(kline[4]) * 0.970, 2)
                            tp = (1 + ((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                            tp = round(tp, 2)

                            self.ex_trade(float(kline[4]), tp, sl, 'BUY', 'LONG', self.usd_test,
                                          kline[6], 'ADX')
                            self.adx_trade = False
                        else:
                            self.rsi_type = None
                            self.rsi_item_guide = None
                            self.adx_trade = False
                    elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                        self.dmi_item_guide = dmi_
                        self.adx_trade = True
                    elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                        'positive'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross[
                        'type'] == 1:
                        s_ = self.get_next_support(kline, [0.970, 0.975])

                        sl = round(s_ if s_ is not None else float(kline[4]) * 0.970, 2)
                        tp = (1 + ((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                        tp = round(tp, 2)

                        self.ex_trade(float(kline[4]), tp, sl, 'BUY', 'LONG', self.usd_test,
                                      kline[6], 'ADX')
                        self.adx_trade = False
                    else:
                        self.rsi_type = None
                        self.rsi_item_guide = None
                        self.adx_trade = False
                else:
                    self.rsi_item_guide = rsi_
                    return
        elif self.rsi_type == 0:
            if self.rsi[self.rsi.index(rsi_) - 1] == self.rsi_item_guide or self.adx_trade:
                if rsi_['rsi'] > self.rsi_item_guide['rsi'] or self.adx_trade:
                    marker_dmi = self.model_tools.get_dmi_marker_by_date(kline[6])
                    ema_cross = self.model_tools.get_ema_cross_after_by_date(kline[6])

                    if marker_dmi is None or ema_cross is None:
                        return

                    after_marker_dmi = self.dmi_markers[
                        self.dmi_markers.index(marker_dmi) - 1 if marker_dmi is not None and self.dmi_markers.index(
                            marker_dmi) - 1 is not None else 0]

                    if marker_dmi is not None and after_marker_dmi is not None and marker_dmi['DI']['date'] - \
                            after_marker_dmi['DI']['date'] <= 300000 * 50:

                        kline_m = self.get_kline_liquidate_marker(marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                self.dmi_markers.index(
                                                                                                    marker_dmi) - 1][
                                                                                                'DI'][
                                                                                                'date'] or 300000 * 10 if
                        marker_dmi['ADX'] is None else marker_dmi['ADX']['date'], marker_dmi['DI']['type'])
                        kline_am = self.get_kline_liquidate_marker(after_marker_dmi['DI']['date'], self.dmi_markers[
                                                                                                       self.dmi_markers.index(
                                                                                                           marker_dmi) - 1][
                                                                                                       'DI'][
                                                                                                       'date'] or 300000 * 10 if
                        after_marker_dmi['ADX'] is None else after_marker_dmi['ADX']['date'],
                                                                   after_marker_dmi['DI']['type'])

                        if self.check_dmi_params(40, self.klines.index(kline) - 29, 'negative') and self.verify_distance_between_ema(1.002,
                                                                                                              0.998,
                                                                                                              kline[
                                                                                                                  6],
                                                                                                              0) and self.verify_distance_between_ema(
                            1.002, 0.998, kline[6], 1) and (False if marker_dmi['DI']['value'] >= 55 else (
                                marker_dmi['DI']['value'] < after_marker_dmi['DI']['value'] and float(
                            kline_m[4]) > float(kline_am[4]))) and marker_dmi['DI']['type'] == \
                                after_marker_dmi['DI']['type']:
                            s_ = self.get_next_support(kline, [0.970, 0.975])

                            sl = round(s_ if s_ is not None else float(kline[4]) * 0.975, 2)
                            tp = (1 + ((1 - (sl / float(kline[4]))) * 1.5)) * float(kline[4])
                            tp = round(tp, 2)

                            self.ex_trade(float(kline[4]), tp, sl, 'BUY', 'LONG', self.usd_test,
                                          kline[6])
                        elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                            self.dmi_item_guide = dmi_
                            self.adx_trade = True
                        elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                            'negative'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross[
                            'type'] == 0:
                            r_ = self.get_next_resistance(kline, [1.030, 1.025])

                            sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                            tp = (1 - abs((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                            tp = round(tp, 2)

                            self.ex_trade(float(kline[4]), tp, sl, 'SELL', 'SHORT', self.usd_test,
                                          kline[6], 'ADX')

                            self.adx_trade = False
                        else:
                            self.rsi_type = None
                            self.rsi_item_guide = None
                            self.adx_trade = False
                    elif dmi_['ADX'] > self.dmi_item_guide['ADX']:
                        self.dmi_item_guide = dmi_
                        self.adx_trade = True
                    elif self.dmi_item_guide['ADX'] >= 55.00 and marker_dmi['DI']['value'] >= 50 and dmi_['DI'][
                        'negative'] < 45 and kline[6] - ema_cross['data'][0]['date'] >= 300000 * 100 and ema_cross[
                        'type'] == 0:
                        r_ = self.get_next_resistance(kline, [1.030, 1.025])

                        sl = round(r_ if r_ is not None else float(kline[4]) * 1.025, 2)
                        tp = (1 - abs((1 - (sl / float(kline[4]))) * 1)) * float(kline[4])
                        tp = round(tp, 2)

                        self.ex_trade(float(kline[4]), tp, sl, 'SELL', 'SHORT', self.usd_test,
                                      kline[6], 'ADX')
                        self.adx_trade = False
                    else:
                        self.rsi_type = None
                        self.rsi_item_guide = None
                        self.adx_trade = False
                else:
                    self.rsi_item_guide = rsi_
                    return

    def check_dmi_params(self, points: float or int, index: int, di: str):

        return True if self.dmi[index]['DI'][di] >= points else False

    def set_trade_data(self, entry, tp, sl, t, amount, leverage, _d, tt='ADX'):

        self.trade_in_ex = True

        self.trade_data = {
            'type': t,
            'entry': entry,
            'tp': tp,
            'sl': sl,
            'amount': amount,
            'lv': leverage,
            'al': amount * leverage,
            'date': _d,
            'init_patrimony': self.patrimony,
            'tt': tt
        }

    def calc_trade(self, kline):

        _tr = self.trade_data

        close = float(kline[4])
        low = float(kline[3])
        high = float(kline[2])

        _ema_cross = self.model_tools.get_ema_cross_after_by_date(kline[6])

        if _tr['type'] == 'LONG':
            if high >= _tr['tp'] or _tr['tp'] <= close:
                pnl = _tr['tp'] / _tr['entry']

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.won += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None
            elif close <= _tr['sl'] or low <= _tr['sl']:
                pnl = float(kline[4]) / _tr['entry']

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.losses += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None
            elif _ema_cross['type'] == 0 if _tr['tt'] == 'ADX' else close <= _tr['sl'] or low <= _tr['sl']:
                pnl = float(kline[4]) / _tr['entry']

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.losses += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None

            else:

                pnl_close = close / _tr['entry']
                pnl_low = low / _tr['entry']

                diff_close = (_tr['al'] * pnl_close - _tr['al']) * -1
                diff_low = (_tr['al'] * pnl_low - _tr['al']) * -1

                ###################################################

                diff_tp_high = round(high / _tr['tp'], 3)

                if diff_close / _tr['amount'] >= 0.99000:

                    self.patrimony += diff_close * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.losses += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

                elif diff_low / _tr['amount'] >= 0.99000:

                    self.patrimony += diff_low * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.losses += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

                elif diff_tp_high >= 0.994:

                    diff_tp_high = high / _tr['entry']

                    self.patrimony += ((_tr['al'] * diff_tp_high - _tr['al']) * -1) * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.won += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

        elif _tr['type'] == 'SHORT':
            if low <= _tr['tp'] or _tr['tp'] >= close:
                pnl = 1 + (1 - (_tr['tp'] / _tr['entry']))

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.won += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None
            elif close >= _tr['sl'] or low >= _tr['sl']:
                pnl = 1 + (1 - (float(kline[4]) / _tr['entry']))

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.losses += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None
            elif _ema_cross['type'] == 1 if _tr['tt'] == 'ADX' else close >= _tr['sl'] or low >= _tr['sl']:
                pnl = 1 + (1 - (float(kline[4]) / _tr['entry']))

                self.patrimony += (_tr['al'] * pnl - _tr['al'])

                pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                _tr['pnl'] = pnl
                _tr['final_patrimony'] = self.patrimony
                _tr['finish_date'] = kline[6]
                self.losses += 1
                self.trades_history.append(_tr)
                self.trade_in_ex = False
                self.trade_data = None

            else:

                pnl_close = 1 + (1 - (close / _tr['entry']))
                pnl_high = 1 + (1 - (high / _tr['entry']))

                diff_close = (_tr['al'] * pnl_close - _tr['al']) * -1
                diff_high = (_tr['al'] * pnl_high - _tr['al']) * -1

                ####################################################

                diff_tp_low = round(low / _tr['tp'], 3)

                if diff_close / _tr['amount'] >= 0.99000:

                    self.patrimony += diff_close * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.losses += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

                elif diff_high / _tr['amount'] >= 0.99000:

                    self.patrimony += diff_high * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.losses += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

                elif diff_tp_low <= 1.006:

                    diff_tp_low = 1 + (1 - (low / _tr['entry']))

                    self.patrimony += ((_tr['al'] * diff_tp_low - _tr['al']) * -1) * -1
                    pnl = (1 - (self.patrimony / _tr['init_patrimony'])) * -1

                    _tr['pnl'] = pnl
                    _tr['final_patrimony'] = self.patrimony
                    _tr['finish_date'] = kline[6]
                    self.won += 1
                    self.trades_history.append(_tr)
                    self.trade_in_ex = False
                    self.trade_data = None

    def check_ema_type(self, item1, item2):
        value1, value2 = item1['value'], item2['value']

        if value1 / value2 >= 1.002:
            return 1
        elif value1 / value2 <= 0.998:
            return 0

    def get_next_support(self, kline, percentages: list = None):
        self.markers.reverse()

        value = float(kline[4])
        date = kline[6]

        support = None

        for item in self.markers:

            v = item['value'][0]

            if (0.994 <= round(v / value, 3) <= 0.997) if percentages is None else (percentages[0] <= v / value <=
                                                                                    percentages[1]) and date > item[
                                                                                       'date'] and item[
                                                                                       'type'] != 'null':
                support = item['value'][0]
                break

        self.markers.reverse()

        return support

    def get_next_resistance(self, kline, percentages: list = None):
        self.markers.reverse()

        value = float(kline[4])
        date = kline[6]

        resistance = None

        for item in self.markers:

            v = item['value'][0]

            if (1.0055 >= round(v / value, 3) >= 1.005) if percentages is None else (percentages[1] >= v / value >=
                                                                                     percentages[0]) and date > item[
                                                                                        'date'] and item[
                                                                                        'type'] != 'null':
                resistance = item['value'][0]
                break

        self.markers.reverse()

        return resistance

    def get_users_(self):
        db_ = mongo_db.users

        res = db_.find({'active': True})

        clients = []

        for i in res:
            _uk = i['user_key']
            _sk = i['secret_key']
            _cantity = i['cantity']
            _leverage = i['leverage']

            if len(_uk) == 0 and len(_sk) == 0 and not('BTCUSDT' in i['pairs'] or 'btcusdt' in i['pairs']):
                continue

            _uk, _sk = mongo_db.decrypt_api_keys(_uk, _sk)

            clients.append([str(i['_id']), Client(_uk, _sk), _cantity, _leverage])

        return clients

    def ex_trade(self, entry, tp, sl, side, positionSide, quantity, date_, t='DMI'):

        clients = self.get_users_()

        trades = {}

        for i in clients:

            i[1].futures_change_leverage(symbol=self.currency, leverage=i[3])

            order_amount = round((i[2] * i[3] / self.price), self.symbol_n_precision)

            order = i[1].futures_create_order(
                symbol=self.currency,
                side=side,
                positionSide=positionSide,
                type='MARKET',
                dualSidePosition=False,
                quantity=order_amount
            )

            if positionSide == 'LONG':
                side = 'SELL'
            else:
                side = 'BUY'

            take_profit_amount = round((tp / self.price) * order_amount, self.symbol_n_precision) if positionSide == 'LONG' else round((1+1-(tp / self.price)) * order_amount, self.symbol_n_precision)
            stop_loss_amount = round((sl / self.price) * order_amount, self.symbol_n_precision) if positionSide == 'LONG' else round((1+1-(sl / self.price)) * order_amount, self.symbol_n_precision)
            take_profit = i[1].futures_create_order(
                symbol=self.currency,
                side=side,
                type='TAKE_PROFIT_MARKET',
                positionSide=positionSide,
                stopPrice=tp,
                timestamp=int(time.time() * 1000),
                quantity=take_profit_amount,
                closePosition=True,
                workingType='MARK_PRICE',
                timeInForce='GTE_GTC',
                priceProtect=True
            )

            stop_loss = i[1].futures_create_order(
                symbol=self.currency,
                side=side,
                type='STOP_MARKET',
                positionSide=positionSide,
                stopPrice=sl,
                timestamp=int(time.time() * 1000),
                workingType='MARK_PRICE',
                timeInForce='GTE_GTC',
                quantity=stop_loss_amount,
                closePosition=True,
                priceProtect=True
            )

            trades[i[0]] = {
                'entry': self.price,
                'order': order,
                'tp': take_profit,
                'tp_price': tp,
                'sl': stop_loss,
                'sl_price': sl,
                'date': date_,
                'type': t,
                'positionSide': positionSide,
                'client': i[1],
                'amount': order_amount
            }

        self.trade_data = trades

        mongo_db.add_trades(trades)

        self.trade_in_ex = True

    async def config_BM(self):
        self.client_socket = await AsyncClient.create()
        self.bm = BinanceSocketManager(self.client_socket)
        # start any sockets here, i.e a trade socket
        ts = self.bm.kline_futures_socket(symbol=self.currency, interval=self.interval)
        # then start receiving messages
        async with ts as tscm:
            while True:
                res = await tscm.recv()
                self.price = float(res['k']['c'])
                print(res)
                if res['k']['x']:
                    self.add_kline(res['k']['T'])
                    print('add_kline')
                    self.run_strategy()

    async def close_BM(self):
        await self.client_socket.close_connection()

    def add_kline(self, date_end: int):
        self.put_end_day(date_end)

    def view_chart(self, trade_index, c_a, c_b):

        klines_dr = {
            'Date': [],
            'Open': [],
            'High': [],
            'Low': [],
            'Close': [],
            'Adj Close': [],
            'Volume': [],
            'RSI': [],
            'RSI MA': [],
            'DI+': [],
            'DI-': [],
            'ADX': [],
            'Signal': [],
            'First EMA': [],
            'Second EMA': []
        }

        trade_date = self.trades_history[trade_index]['date']
        trade_finish_date = self.trades_history[trade_index]['finish_date']

        five_min = 300000

        for item in self.klines:

            i = self.klines.index(item)

            rsi_ = self.rsi[i - 14] if i >= 14 else None
            dmi_ = self.dmi[i - 28] if i >= 28 else None
            ema_f = self.first_ema[i - self.first_period_ema] if i >= self.first_period_ema else None
            ema_s = self.second_ema[i - self.second_period_ema] if i >= self.second_period_ema else None

            if rsi_ is None or dmi_ is None:
                continue

            if five_min * c_a >= trade_date - item[6] >= (five_min * c_b) * -1:

                klines_dr['Date'].append(item[0])
                klines_dr['Open'].append(float(item[1]))
                klines_dr['High'].append(float(item[2]))
                klines_dr['Low'].append(float(item[3]))
                klines_dr['Close'].append(float(item[4]))
                klines_dr['Adj Close'].append(float(item[4]))
                klines_dr['Volume'].append(float(item[5]))
                klines_dr['RSI'].append(rsi_['rsi'])
                klines_dr['RSI MA'].append(rsi_['ma'])
                klines_dr['DI+'].append(dmi_['DI']['positive'])
                klines_dr['DI-'].append(dmi_['DI']['negative'])
                klines_dr['ADX'].append(dmi_['ADX'])
                klines_dr['First EMA'].append(ema_f['value'] if ema_f is not None else numpy.nan)
                klines_dr['Second EMA'].append(ema_s['value'] if ema_s is not None else numpy.nam)

                if trade_date == item[6] or trade_finish_date == item[6]:
                    klines_dr['Signal'].append(float(item[4]) * 1.003)
                else:
                    klines_dr['Signal'].append(numpy.nan)

        klines_dr = pd.DataFrame(data=klines_dr)

        klines_dr.Date = pd.to_datetime(klines_dr.Date)

        klines_dr = klines_dr.set_index('Date')

        apds = [
            mplf.make_addplot((klines_dr['RSI']), panel=1),
            mplf.make_addplot((klines_dr['RSI MA']), panel=1),
            mplf.make_addplot((klines_dr['DI+']), panel=2, color='g'),
            mplf.make_addplot((klines_dr['DI-']), panel=2),
            mplf.make_addplot((klines_dr['ADX']), panel=2),
            mplf.make_addplot((klines_dr['Signal']), type='scatter', markersize=200, marker='v'),
            mplf.make_addplot((klines_dr['First EMA']), color='orange'),
            mplf.make_addplot((klines_dr['Second EMA']), color='blue')
        ]
        mplf.plot(klines_dr, type='candle', style='yahoo', figscale=1.2, addplot=apds)

    def reset_vars(self):
        self.klines = self.model_tools.klines
        self.ema25, self.ema40 = self.model_tools.ema25, self.model_tools.ema40
        self.rsi = self.model_tools.rsi
        self.dmi = self.model_tools.dmi
        self.markers = self.model_tools.calculateSupportsAndResistors(self.model_tools.klines, 'CLOSE',
                                                                      downPercentage=.998, climbPercentage=1.002)

    def run_console(self):

        bl = True

        while bl:
            x = input("Select option: \n 1. View Chart\n 2. View trade history\n 3. Close\n=")

            x = int(x)

            if x == 1:
                index = input("Set index:")
                candles_after = input("Set the number of candles after the trade:")
                candles_before = input("Set the number of candles before the trade:")

                index = int(index)
                candles_after = int(candles_after)
                candles_before = int(candles_before)

                try:
                    self.view_chart(index, candles_after, candles_before)
                except:
                    print("The numbers of candles do not compatible")
            elif x == 2:
                print(bot.trades_history)
            elif x == 3:
                bl = False


if __name__ == '__main__':
    data = []

    r = 12

    for i in range(r):
        date = datetime.datetime.now()
        end_day = (date.timestamp() * 1000) - (86400000 * (i * 30))
        start_day = end_day - (86400000 * 30)

        user_key = 'dIXuGb6b1CFjGb6nqn7Vyav7cKm0JwVSv3al62rBruM82Xmsjq4t4tMcNbFoYFsr'
        secret_key = 'aNPDlOhEzk9WLKaLxnkFOTQT6BQ4p7ttXDzSlWK25drrMFY2pWHXszNLtQmwvHSq'

        bot = BotTrading('BTCBUSD', int(start_day), int(end_day), Client.KLINE_INTERVAL_5MINUTE, 3, 1000, 10, user_key,
                         secret_key, 99, 200)
        bot.run_strategy_test()

        d = {
            'init_inv': bot.usd_test,
            'final_capital': bot.patrimony,
            'won_trades': bot.won,
            'losses_trades': bot.losses,
            'trades': bot.trades_history
        }

        data.append(d)

        print(f"{i+1}/{r}")

    print(data)

    won_trades_total = 0
    losses_trades_total = 0
    trades_ratio = 0
    balance_ratio = 0
    final_patrimony = 0
    init_inv = 1000

    for i in data:

        won_trades_total += i['won_trades']
        losses_trades_total += i['losses_trades']
        final_patrimony += (i['final_capital'] - i['init_inv'])

        if data.index(i) == len(data) - 1:
            trades_ratio = won_trades_total / (won_trades_total + losses_trades_total)
            balance_ratio = final_patrimony / init_inv
            final_patrimony += 1000

    print(
        f"======STATICS======\nWon trades: {won_trades_total}\nLosses trades: {losses_trades_total}\nTrades ratio: {round(trades_ratio * 100, 2)}%\nInitial investment: ${init_inv}\nFinal balance: ${round(final_patrimony, 2)}\nBalance ratio: {round(balance_ratio * 100, 2)}%")