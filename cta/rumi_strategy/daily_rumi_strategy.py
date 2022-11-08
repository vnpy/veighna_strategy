from numpy import ndarray

from vnpy_ctastrategy import (
    CtaTemplate,
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


class DailyRumiStrategy(CtaTemplate):

    """Rumi策略"""

    author = "VeighNa Elite"

    fast_window = 3         # 快速均线窗口
    slow_window = 50        # 慢速均线窗口
    diff_window = 30        # 均线偏差窗口
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量

    ma_diff = 0.0           # 均线偏差值

    parameters = [
        "fast_window",
        "slow_window",
        "diff_window",
        "price_add",
        "fixed_size"
    ]
    variables = ["ma_diff"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = DailyBarGenerator(self.on_bar, 1, self.on_daily_bar)
        self.am = ArrayManager()

    def on_init(self):
        """初始化"""
        self.write_log("策略初始化")
        self.load_bar(30)

    def on_start(self):
        """启动"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self):
        """停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData):
        """Tick数据推送"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """分钟K线推送"""
        self.bg.update_bar(bar)

    def on_daily_bar(self, bar: BarData):
        """日线推送"""
        # 更新到ArrayManager
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 计算均线数组
        fast_array: ndarray = am.sma(self.fast_window, array=True)
        slow_array: ndarray = am.ema(self.slow_window, array=True)

        # 计算均线差值
        diff_array: ndarray = fast_array - slow_array
        diff_mean_0 = diff_array[-self.diff_window:].mean()
        diff_mean_1 = diff_array[-self.diff_window-1:-1].mean()

        # 判断上下穿
        cross_over = diff_mean_0 > 0 and diff_mean_1 <= 0
        cross_below = diff_mean_0 < 0 and diff_mean_1 >= 0

        # 执行交易信号
        if cross_over:
            # 计算委托限价（超价）
            price: float = bar.close_price + self.price_add

            # 无仓位，直接开仓
            if not self.pos:
                self.buy(price, self.fixed_size)
            # 反向仓位，先平后开
            elif self.pos < 0:
                self.cover(price, abs(self.pos))
                self.buy(price, self.fixed_size)
        elif cross_below:
            # 计算委托限价（超价）
            price: float = bar.close_price - self.price_add

            # 无仓位，直接开仓
            if not self.pos:
                self.short(price, self.fixed_size)
            # 反向仓位，先平后开
            elif self.pos > 0:
                self.sell(price, abs(self.pos))
                self.short(price, self.fixed_size)

        self.put_event()

    def on_order(self, order: OrderData):
        """委托推送"""
        pass

    def on_trade(self, trade: TradeData):
        """成交推送"""
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
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
