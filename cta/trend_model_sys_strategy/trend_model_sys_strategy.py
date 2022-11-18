import talib

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


class TrendModelSysStrategy(CtaTemplate):
    """长短MACD震荡反程序化策略"""

    author = "VeighNa Elite"

    fast_window = 5        # 短周期MA窗口
    slow_window = 21       # 长周期MA窗口
    macd_window = 4
    ncos = 4  # 交叉的次数
    n_bars = 75  # 在多少根K线内进行统计
    trailbar = 5  # 离场信号所用的K线数目
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 5              # 窗口频率的K线，研报默认为1天，可修改

    mval = 0
    mavg = 0
    mdif = 0
    count = 0
    total_bar = 0
    highest = 0
    lowest = 0

    parameters = [
        "macd_window",
        "ncos",
        "n_bars",
        "fast_window",
        "slow_window",
        "trailbar",
        "window",
        "price_add",
        "fixed_size"
    ]

    variables = [
        "mval",
        "mavg",
        "mdif",
        "count",
        "total_bar",
        "highest",
        "lowest"
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

        self.bg = BarGenerator(self.on_bar, self.window, self.on_5min_bar)
        self.am = ArrayManager(100)
        self.high_price = []
        self.low_price = []
        self.bar_number = []

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

    def on_5min_bar(self, bar: BarData):
        """日线推送"""
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.count += 1  # 第几根K线
        self.mval = am.ema(self.fast_window, array=True) - am.ema(self.slow_window, array=True)
        self.mavg = talib.EMA(self.mval, self.macd_window)
        self.mdif = self.mval - self.mavg

        cross_over = self.mdif[-1] > 0 and self.mdif[-2] < 0
        cross_below = self.mdif[-1] < 0 and self.mdif[-2] > 0

        if self.pos > 0:
            self.cancel_all()
            if bar.close_price < am.low_array[-self.trailbar - 1:-1].min():
                price: float = bar.close_price - self.price_add
                self.sell(price, abs(self.pos))
        elif self.pos < 0:
            self.cancel_all()
            if bar.close_price > am.high_array[-self.trailbar - 1:-1].max():
                price: float = bar.close_price + self.price_add
                self.cover(price, abs(self.pos))

        if cross_over or cross_below:
            self.bar_number.append(self.count)  # 记录已经来了多少根K线
            self.high_price.append(bar.high_price)
            self.low_price.append(bar.low_price)

            if len(self.bar_number) < self.ncos:  # 不到指定交叉次数，退出
                return

            # 到了指定交叉次数，开始统计最近ncos次交叉是否在n_bars根K线内发生
            if self.bar_number[-1] - self.bar_number[-self.ncos] > self.n_bars:
                return

            # 满足条件开始挂单
            if self.pos == 0:
                self.highest = max(self.high_price[-self.ncos:])
                self.lowest = min(self.low_price[-self.ncos:])
                buy_price: float = self.highest + self.price_add
                short_price: float = self.lowest - self.price_add
                self.buy(buy_price, self.fixed_size, stop=True)
                self.short(short_price, self.fixed_size, stop=True)

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
