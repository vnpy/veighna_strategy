from numpy import ndarray

from vnpy.trader.constant import Interval

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


class RumiStrategy(CtaTemplate):
    """RUMI策略"""

    author = "VeighNa Elite"

    fast_window = 3         # 快速均线窗口
    slow_window = 50        # 慢速均线窗口
    diff_window = 30        # 均线偏差窗口
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量

    atr_window = 10
    trading_size = 1
    risk_level = 5000

    ma_diff = 0.0           # 均线偏差值

    parameters = [
        "fast_window",
        "slow_window",
        "diff_window",
        "price_add",
        "fixed_size"
    ]
    variables = ["ma_diff"]

    def __init__(
        self,
        cta_engine: CtaEngine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict
    ):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(
            self.on_bar,
            window=30,
            on_window_bar=self.on_window_bar,
            # interval=Interval.HOUR
        )

        self.am = ArrayManager(200)

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
        """K线推送"""
        self.bg.update_bar(bar)

    def on_window_bar(self, bar: BarData) -> None:
        """周期K线推送"""
        self.cancel_all()

        # 更新到ArrayManager
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 计算均线数组
        fast_array: ndarray = am.sma(self.fast_window, array=True)
        slow_array: ndarray = am.wma(self.slow_window, array=True)

        # 计算均线差值
        diff_array: ndarray = fast_array - slow_array
        diff_mean_0 = diff_array[-self.diff_window:].mean()
        diff_mean_1 = diff_array[-self.diff_window-1:-1].mean()

        # 判断上下穿
        cross_over = diff_mean_0 > 0 and diff_mean_1 <= 0
        cross_below = diff_mean_0 < 0 and diff_mean_1 >= 0

        # 计算交易数量
        self.atr_value = am.atr(self.atr_window)
        self.fixed_size = max(int(self.risk_level / self.atr_value), 1)
        # print(self.fixed_size)
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

    def on_order(self, order: OrderData) -> None:
        """委托推送"""
        pass

    def on_trade(self, trade: TradeData) -> None:
        """成交推送"""
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        """停止单推送"""
        pass
