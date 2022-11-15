import numpy as np
import pandas as pd
from typing import List

from vnpy_ctastrategy import (
    CtaTemplate,
    CtaEngine,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class OiBasedStrategy(CtaTemplate):
    """持仓量策略"""

    author = "VeighNa Elite"

    ma_p_window = 16        # 激进交易的态度窗口长度，研报默认为4
    ma_q_window = 7         # 激进交易的分歧度窗口长度，研报默认为5
    K = 0.1                 # 当天总成交量的比率，研报默认是10%
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 1              # 日内窗口频率的K线，研报默认为1分钟，可修改

    parameters = [
        "ma_p_window",
        "ma_q_window",
        "K",
        "window",
        "price_add",
        "fixed_size"
    ]

    variables = []

    def __init__(
        self,
        cta_engine: CtaEngine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict
    ):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(self.on_bar, self.window, self.on_Nmin_window_bar)
        self.am = ArrayManager(500)  # 起码容纳一天以上的分钟数据
        self.last_bar: BarData = None
        self.P_list: List = [None]*self.ma_p_window
        self.Q_list: List = [None]*self.ma_q_window
        self.P_count = 0
        self.Q_count = 0

    def on_init(self) -> None:
        """初始化"""
        self.write_log("策略初始化")
        self.load_bar(10)

    def on_start(self) -> None:
        """启动"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick推送"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """一分钟数据推送"""
        self.bg.update_bar(bar)

    def on_Nmin_window_bar(self, bar: BarData) -> None:
        """N分钟K线推送"""
        # 更新到ArrayManager
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        if not self.last_bar or self.last_bar.datetime.day != bar.datetime.day:
            self.last_bar = bar
            self.count = 1  # 当天第一根K线
            return

        elif bar.datetime.minute == 59 and bar.datetime.hour == 14:
            # 当前已经收盘，开始计算
            self.count += 1
            df = pd.DataFrame()
            df['Vt'] = am.volume_array[-self.count:]
            if 0 in np.array(df['Vt']):  # 错误数据
                return

            V = self.K * df['Vt'].sum()
            df['close_price'] = am.close_array[-self.count:]
            df['pre_close'] = am.close_array[-self.count - 1: -1]
            df['Rt'] = (df['close_price'] - df['pre_close']) / df['pre_close']*1000
            df['Oi'] = am.open_interest_array[-self.count:]
            df['pre_Oi'] = am.open_interest_array[-self.count - 1: -1]
            df['Oi_change'] = df['Oi'] - df['pre_Oi']
            df['St_P'] = abs(df['Rt']) / np.sqrt(df['Vt'])
            df['St_Q'] = abs(df['Oi_change']) / np.sqrt(df['Vt'])

            df_P = df
            # 按照St的数值进行降序
            df_P = df_P.sort_values(by='St_P', ascending=False)
            index = np.where(df_P['Vt'].cumsum() >= V)[0][0]
            P = df_P['Rt'][:index+1].sum()

            df_Q = df
            df_Q = df_Q.sort_values(by='St_Q', ascending=False)
            index = np.where(df_Q['Vt'].cumsum() >= V)[0][0]
            Q = df_Q['Oi_change'][:index+1].sum()

            # 此时P和Q都已经算完了，检查P和Q的序列是否到了窗口数量，因为要算MA
            if self.P_count < self.ma_p_window or self.Q_count < self.ma_q_window:  # 不够数量
                self.P_count += 1
                self.Q_count += 1
                self.P_list.append(P)
                self.P_list.pop(0)
                self.Q_list.append(Q)
                self.Q_list.pop(0)
                return

            else:  # 可以交易了，也要先更新P和Q的序列
                self.P_list.append(P)
                self.P_list.pop(0)
                self.Q_list.append(Q)
                self.Q_list.pop(0)
                P = P - sum(self.P_list)/len(self.P_list)
                Q = Q - sum(self.Q_list)/len(self.Q_list)

                if (P < 0 and Q > 0) or (P > 0 and Q < 0):  # 态度趋多，分歧减少（或反）看多
                    price: float = bar.close_price + self.price_add
                    if not self.pos:
                        self.buy(price, self.fixed_size)
                    elif self.pos < 0:
                        self.cover(price, abs(self.pos))
                        self.buy(price, self.fixed_size)
                elif (P < 0 and Q < 0) or (P > 0 and Q > 0):  # 态度趋空，分歧加大（或反）看空
                    price: float = bar.close_price - self.price_add
                    if not self.pos:
                        self.short(price, self.fixed_size)
                    elif self.pos > 0:
                        self.sell(price, abs(self.pos))
                        self.short(price, self.fixed_size)

        else:  # 不是新的一天，也还没收盘啥也别干，等待记录就好
            self.count += 1

        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """委托推送"""
        pass

    def on_trade(self, trade: TradeData) -> None:
        """成交推送"""
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        """停止单推送"""
        pass
