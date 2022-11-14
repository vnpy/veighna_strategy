import numpy as np
import pandas as pd

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


class CpvStrategy(CtaTemplate):
    """Cpv策略"""

    author = "VeighNa Elite"

    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 1              # 日内窗口频率的K线，研报默认为1分钟，可修改

    parameters = [
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
            df['Vt'] = am.volume_array[-self.count:]  # 成交量
            if 0 in np.array(df['Vt']):  # 错误数据
                return

            df['pre_Vt'] = am.volume_array[-self.count - 1: -1]
            df['Vt_change'] = df['Vt'] - df['pre_Vt']
            df['Oi'] = am.open_interest_array[-self.count:]  # 持仓量
            df['pre_Oi'] = am.open_interest_array[-self.count - 1: -1]
            df['Oi_change'] = df['Oi'] - df['pre_Oi']
            delta_oi = df['Oi'].iloc[-1] - df['Oi'].iloc[0]  # 当天持仓量变化
            delta_Vt = df['Vt_change'][1:].sum()  # 当天成交量变化的累积
            df['oi_t1'] = df['Vt_change'] * delta_oi / delta_Vt  # T+1交易者的贡献
            df['oi_t0'] = -1 * (df['Oi_change'] - df['oi_t1'])   # T+0交易者的贡献
            df['mod_delta_oi'] = df['oi_t0'] + df['oi_t1']
            df['mod_delta_oi'][0] = df['Oi'][0]
            df['mod_oi'] = df['mod_delta_oi'].cumsum()  # 修正持仓量
            df['close_price'] = am.close_array[-self.count:]
            pv = df['close_price'].corr(df['mod_oi'])  # 修正持仓量和收盘价的相关系数

            if pv > 0:
                price: float = bar.close_price + self.price_add
                if not self.pos:
                    self.buy(price, self.fixed_size)
                elif self.pos < 0:
                    self.cover(price, abs(self.pos))
                    self.buy(price, self.fixed_size)
            else:
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
