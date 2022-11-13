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
from vnpy.trader.constant import Interval
from datetime import datetime
from typing import Callable


class MAOBVStrategy(CtaTemplate):
    """基于相对成交量的MA策略"""

    author = "VeighNa Elite"

    fast_window = 5        # 短周期MA窗口
    slow_window = 65       # 长周期MA窗口
    price_add = 1           # 委托超价
    fixed_size = 1          # 委托数量
    window = 1              # 窗口频率的K线，研报默认为1天，可修改
    obv_window = 70         # obv指标的窗口长度
    obv_up = 0.5            # 相对成交量的上阈值
    obv_low = 0.2           # 相对成交量的下阈值

    fast_ma0 = 0.0
    fast_ma1 = 0.0

    slow_ma0 = 0.0
    slow_ma1 = 0.0

    parameters = [
        "obv_window",
        "obv_up",
        "obv_low",
        "fast_window",
        "slow_window",
        "window",
        "price_add",
        "fixed_size"
    ]

    variables = [
        "fast_ma0",
        "fast_ma1",
        "slow_ma0",
        "slow_ma1"
    ]

    def __init__(
        self,
        cta_engine: CtaEngine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict
    ):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = DailyBarGenerator(self.on_bar, self.window, self.on_daily_bar)
        self.am = ArrayManager(100)

    def on_init(self) -> None:
        """初始化"""
        self.write_log("策略初始化")
        self.load_bar(120)

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

    def on_daily_bar(self, bar: BarData):
        """日线推送"""
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        fast_ma = am.sma(self.fast_window, array=True)
        self.fast_ma0 = fast_ma[-1]
        self.fast_ma1 = fast_ma[-2]

        slow_ma = am.sma(self.slow_window, array=True)
        self.slow_ma0 = slow_ma[-1]
        self.slow_ma1 = slow_ma[-2]

        # 计算相对成交量指标
        df = pd.DataFrame()
        df['Vt'] = am.volume_array[-self.obv_window:]
        df['close_price'] = am.close_array[-self.obv_window:]
        df['pre_close'] = am.close_array[-self.obv_window - 1: -1]
        df['status'] = np.where(df['close_price'] >= df['pre_close'], 1, -1)
        df['Vt'] = df['Vt'] * df['status']
        df['obv'] = df['Vt'].cumsum()

        obv = (df["obv"].iloc[-1] - df['obv'].min()) / (df['obv'].max() - df['obv'].min())

        cross_over = self.fast_ma0 > self.slow_ma0 and self.fast_ma1 < self.slow_ma1 and obv > self.obv_up
        cross_below = self.fast_ma0 < self.slow_ma0 and self.fast_ma1 > self.slow_ma1 and obv < self.obv_low

        if cross_over:
            price: float = bar.close_price + self.price_add
            if self.pos == 0:
                self.buy(price, self.fixed_size)
            elif self.pos < 0:
                self.cover(price, abs(self.pos))
                self.buy(price, self.fixed_size)

        elif cross_below:
            price: float = bar.close_price - self.price_add
            if self.pos == 0:
                self.short(price, self.fixed_size)
            elif self.pos > 0:
                self.sell(price, abs(self.pos))
                self.short(price, self.fixed_size)

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


class DailyBarGenerator(BarGenerator):
    """生成日K线"""

    def __init__(
        self,
        on_bar: Callable,
        window: int = 0,
        on_window_bar: Callable = None,
        interval: Interval = Interval.MINUTE
    ) -> None:
        """生成器"""
        self.bar: BarData = None
        self.on_bar: Callable = on_bar

        self.interval: Interval = interval
        self.interval_count: int = 0

        self.hour_bar: BarData = None
        self.daily_bar: BarData = None

        self.window: int = window
        self.window_bar: BarData = None
        self.on_window_bar: Callable = on_window_bar

        self.last_tick: TickData = None

    def update_bar(self, bar: BarData) -> None:
        """分钟K线推送"""
        self.update_bar_daily_window(bar)

    def update_bar_daily_window(self, bar: BarData) -> None:
        """日线构造"""
        # If not inited, create window bar object
        if not self.daily_bar:
            dt: datetime = bar.datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            self.daily_bar = BarData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=dt,
                gateway_name=bar.gateway_name,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
                open_interest=bar.open_interest
            )
            return

        finished_bar: BarData = None

        # If minute bar of new day, then push existing window bar
        if bar.datetime.day != self.daily_bar.datetime.day:
            finished_bar = self.daily_bar
            dt: datetime = bar.datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            self.daily_bar = BarData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=dt,
                gateway_name=bar.gateway_name,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
                open_interest=bar.open_interest
            )
        # Otherwise only update minute bar
        else:
            self.daily_bar.high_price = max(
                self.daily_bar.high_price,
                bar.high_price
            )
            self.daily_bar.low_price = min(
                self.daily_bar.low_price,
                bar.low_price
            )

            self.daily_bar.close_price = bar.close_price
            self.daily_bar.volume += bar.volume
            self.daily_bar.turnover += bar.turnover
            self.daily_bar.open_interest = bar.open_interest

        # Push finished window bar
        if finished_bar:
            self.on_daily_bar(finished_bar)

    def on_daily_bar(self, bar: BarData) -> None:
        """合成N天K线"""
        if self.window == 1:  # 一天K线
            self.on_window_bar(bar)
        else:  # 合成self.window天K线
            if not self.window_bar:
                self.window_bar = BarData(
                    symbol=bar.symbol,
                    exchange=bar.exchange,
                    datetime=bar.datetime,
                    gateway_name=bar.gateway_name,
                    open_price=bar.open_price,
                    high_price=bar.high_price,
                    low_price=bar.low_price
                )
            else:
                self.window_bar.high_price = max(
                    self.window_bar.high_price,
                    bar.high_price
                )
                self.window_bar.low_price = min(
                    self.window_bar.low_price,
                    bar.low_price
                )

            self.window_bar.close_price = bar.close_price
            self.window_bar.volume += bar.volume
            self.window_bar.turnover += bar.turnover
            self.window_bar.open_interest = bar.open_interest

            self.interval_count += 1
            if not self.interval_count % self.window:
                self.interval_count = 0
                self.on_window_bar(self.window_bar)
                self.window_bar = None
