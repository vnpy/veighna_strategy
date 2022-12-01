from typing import List, Dict
# from datetime import datetime
import os
import pandas as pd
from pandas import DataFrame
import numpy as np
from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine
from vnpy_portfoliostrategy.utility import PortfolioBarGenerator
# from vnpy.trader.utility import BarGenerator, extract_vt_symbol
from vnpy.trader.object import TickData, BarData


class OiConcentrationStrategy(StrategyTemplate):
    """"""

    author = "VeighNa Elite"

    R = 5  # 时间窗口
    price_add = 5
    fixed_size = 1

    parameters = [
        "R",
        "price_add",
        "fixed_size"
    ]

    variables = []

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: List[str],
        setting: dict
    ):
        """"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        self.pbg = PortfolioBarGenerator(self.on_bars)
        self.targets: Dict[str, int] = {}

        # 相对强弱
        self.lrsr: Dict[str, List] = {}
        self.weightedls: Dict[str, List] = {}
        #  先初始化
        for vt_symbol in self.vt_symbols:
            self.lrsr[vt_symbol] = []
            self.weightedls[vt_symbol] = []

        # 相对强弱的异常度
        self.lrsrdev1: Dict[str, float] = {}
        self.lrsrdev2: Dict[str, float] = {}
        self.lrsrdev3: Dict[str, float] = {}
        self.weightedlsdev1: Dict[str, float] = {}
        self.weightedlsdev2: Dict[str, float] = {}
        self.weightedlsdev3: Dict[str, float] = {}

        cwd = os.getcwd()
        self.weighted_oi_long: Dict[str, DataFrame] = {}  # 加权的前20大会员多头持仓
        self.weighted_oi_short: Dict[str, DataFrame] = {}  # 加权的前20大会员空头持仓
        self.oi_long: Dict[str, DataFrame] = {}  # 原始的前20大会员多头持仓
        self.oi_short: Dict[str, DataFrame] = {}  # 原始的前20大会员空头持仓
        self.total_oi: Dict[str, DataFrame] = {}  # 总持仓量
        # 上期所，大商所，郑商所共42个品种
        symbols: List = [
            'I888.DCE', 'J888.DCE', 'JM888.DCE', 'EG888.DCE',
            'L888.DCE', 'PP888.DCE', 'V888.DCE', 'A888.DCE', 'B888.DCE',
            'C888.DCE', 'CS888.DCE', 'JD888.DCE', 'M888.DCE', 'P888.DCE',
            'Y888.DCE', 'SF888.CZCE', 'SM888.CZCE', 'ZC888.CZCE', 'FG888.CZCE',
            'MA888.CZCE', 'TA888.CZCE', 'AP888.CZCE', 'CF888.CZCE',
            'CY888.CZCE', 'OI888.CZCE', 'RM888.CZCE', 'RS888.CZCE',
            'SR888.CZCE', 'AG888.SHFE', 'AU888.SHFE', 'HC888.SHFE',
            'RB888.SHFE', 'BU888.SHFE', 'FU888.SHFE', 'RU888.SHFE',
            'SP888.SHFE', 'AL888.SHFE', 'CU888.SHFE', 'NI888.SHFE',
            'PB888.SHFE', 'SN888.SHFE', 'ZN888.SHFE']
        for symbol in symbols:
            self.weighted_oi_long[symbol] = pd.read_csv(cwd + '\\processed_data' + '\\' + symbol.split('888')[0] + '_weighted_processed_long.csv')
            self.weighted_oi_long[symbol].index = self.weighted_oi_long[symbol]['trading_date']
        for symbol in symbols:
            self.weighted_oi_short[symbol] = pd.read_csv(cwd + '\\processed_data' + '\\' + symbol.split('888')[0] + '_weighted_processed_short.csv')
            self.weighted_oi_short[symbol].index = self.weighted_oi_short[symbol]['trading_date']
        for symbol in symbols:
            self.oi_long[symbol] = pd.read_csv(cwd + '\\processed_data' + '\\' + symbol.split('888')[0] + '_processed_long.csv')
            self.oi_long[symbol].index = self.oi_long[symbol]['trading_date']
        for symbol in symbols:
            self.oi_short[symbol] = pd.read_csv(cwd + '\\processed_data' + '\\' + symbol.split('888')[0] + '_processed_short.csv')
            self.oi_short[symbol].index = self.oi_short[symbol]['trading_date']
        for symbol in symbols:
            self.total_oi[symbol] = pd.read_csv(cwd + '\\processed_data' + '\\' + symbol.split('888')[0] + '_total_oi.csv')
            self.total_oi[symbol].index = self.total_oi[symbol]['trading_date']

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.load_bars(1)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.pbg.update_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]):
        """"""
        self.cancel_all()
        #  清空之前的信号，确保字典里面装的都是今天的
        self.lrsrdev1.clear()
        self.lrsrdev2.clear()
        self.weightedlsdev1.clear()
        self.weightedlsdev2.clear()

        #  计算指标，找到排名前20%和后20%的品种
        # 先计算LRSR指标
        for vt_symbol in bars.keys():
            try:
                # total_oi: float = bars[vt_symbol].open_interest用主力持仓排名取代全部合约
                dt = bars[vt_symbol].datetime
                total_oi: float = self.total_oi[vt_symbol][vt_symbol.split('888')[0] + '_total_oi'][dt.strftime('%Y-%m-%d')]
                oi_long: float = self.oi_long[vt_symbol]['volume'][dt.strftime('%Y-%m-%d')]  # 该品种当天前20大会员多头持仓
                oi_short: float = self.oi_short[vt_symbol]['volume'][dt.strftime('%Y-%m-%d')]  # 该品种当天前20大会员空头持仓
                lrsr: float = (oi_long - oi_short) / total_oi
                self.lrsr[vt_symbol].append(lrsr)
            except:
                print('持仓排名数据缺失')

        # 再计算WeightedLS指标
        for vt_symbol in bars.keys():
            try:
                # total_oi: float = bars[vt_symbol].open_interest
                dt = bars[vt_symbol].datetime
                total_oi: float = self.total_oi[vt_symbol][vt_symbol.split('888')[0] + '_total_oi'][dt.strftime('%Y-%m-%d')]
                oi_long: float = self.weighted_oi_long[vt_symbol]['volume'][dt.strftime('%Y-%m-%d')]  # 该品种当天前20大会员多头持仓
                oi_short: float = self.weighted_oi_short[vt_symbol]['volume'][dt.strftime('%Y-%m-%d')]  # 该品种当天前20大会员空头持仓
                weightedls: float = (oi_long - oi_short) / total_oi
                self.weightedls[vt_symbol].append(weightedls)
            except:
                print('持仓排名数据缺失')

        #  计算异常度指标，只计算dev1和dev2,共4个
        for vt_symbol in bars.keys():
            if len(self.lrsr[vt_symbol]) >= self.R:
                mean = np.mean(self.lrsr[vt_symbol][-self.R: -1])
                std = np.std(self.lrsr[vt_symbol][-self.R: -1])
                self.lrsrdev1[vt_symbol] = (self.lrsr[vt_symbol][-1] - mean) / mean
                self.lrsrdev2[vt_symbol] = (self.lrsr[vt_symbol][-1] - mean) / std
                mean = np.mean(self.weightedls[vt_symbol][-self.R: -1])
                std = np.std(self.weightedls[vt_symbol][-self.R: -1])
                self.weightedlsdev1[vt_symbol] = (self.weightedls[vt_symbol][-1] - mean) / mean
                self.weightedlsdev2[vt_symbol] = (self.weightedls[vt_symbol][-1] - mean) / std

        #  尝试使用weightedlsdev2指标来搞

        ascending_sort = sorted(self.weightedlsdev2.items(),  key=lambda d: d[1], reverse=False)
        trading_num = round(len(ascending_sort) * 0.2)  # 买卖数量，前后20%
        long_symbols: List = []
        short_symbols: List = []
        for item in ascending_sort[:trading_num]:  # 值最小的20%应该做空
            short_symbols.append(item[0])
        for item in ascending_sort[-trading_num:]:  # 值最大的20%要买入
            long_symbols.append(item[0])

        #  先全部清仓
        for vt_symbol in self.vt_symbols:
            current_pos = self.get_pos(vt_symbol)
            if current_pos > 0:
                price = bars[vt_symbol].close_price - self.price_add
                self.sell(vt_symbol, price, current_pos)
            elif current_pos < 0:
                price = bars[vt_symbol].close_price + self.price_add
                self.cover(vt_symbol, price, abs(current_pos))

        # 再重新等权重分配目标仓位
        for vt_symbol in bars.keys():
            if vt_symbol in long_symbols:  # 在买入的列表里，花10000块钱去买
                target_pos = 10000 / bars[vt_symbol].close_price
            elif vt_symbol in short_symbols:  # 在卖出的列表里，10000块钱去卖
                target_pos = -10000 / bars[vt_symbol].close_price
            else:
                target_pos = 0
            self.targets[vt_symbol] = round(target_pos)

        # 下单交易
        for vt_symbol in bars.keys():
            trading_volume = self.targets[vt_symbol]
            if trading_volume > 0:
                price = bars[vt_symbol].close_price + self.price_add
                self.buy(vt_symbol, price, trading_volume)
            elif trading_volume < 0:
                price = bars[vt_symbol].close_price - self.price_add
                self.short(vt_symbol, price, abs(trading_volume))

        self.put_event()
