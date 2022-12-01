import numpy as np

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


class ContiBreStrategy(CtaTemplate):
    """连续突破追踪策略"""

    author = "VeighNa Elite"

    n1 = 4        # 累积突破次数
    n2 = 4       # 最高最低价的统计时间窗口
    count = 6    # 突破次数统计时间窗口
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 5              # 窗口频率的K线，研报默认为1天，可修改

    i_count = 0  # K线标号
    highest = 0
    lowest = 0

    parameters = [
        "n1",
        "n2",
        "count",
        "window",
        "price_add",
        "fixed_size"
    ]

    variables = [
        "i_count",
        "highest",
        "lowest",
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

        self.bg = BarGenerator(self.on_bar, self.window, self.on_Nmin_bar)
        self.am = ArrayManager()
        self.bar_number = []  # 记录K线序号
        self.signal = []  # 记录信号

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

    def on_Nmin_bar(self, bar: BarData):
        """N分钟线推送"""
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.i_count += 1  # 第几根K线
        self.highest = am.close_array[-self.n2-1:-1].max()  # 一段时间的最高价
        self.lowest = am.close_array[-self.n2-1:-1].min()  # 一段时间的最低价
        if bar.close_price > self.highest:  # 突破
            self.bar_number.append(self.i_count)  # 把K线的编号记录下来
            self.signal.append(1)  # 把信号记录下来
            while self.bar_number[-1] - self.bar_number[0] > self.count:  # 超过统计周期
                self.bar_number.pop(0)  # 把前面的丢掉，继续向前动态跟踪
                self.signal.pop(0)  # 老信号丢掉

        if bar.close_price < self.lowest:  # 向下突破
            self.bar_number.append(self.i_count)
            self.signal.append(-1)  # 把信号记录下来
            while self.bar_number[-1] - self.bar_number[0] > self.count:
                self.bar_number.pop(0)
                self.signal.pop(0)  # 老信号丢掉

        if len(self.signal) == 0:
            return

        if np.cumsum(np.array(self.signal))[-1] > self.n1:  # 向上突破次数累计到一定的量
            if self.pos == 0:
                price: float = bar.close_price + self.price_add
                self.buy(price, self.fixed_size)
            elif self.pos < 0:
                price: float = bar.close_price + self.price_add
                self.cover(price, abs(self.pos))
                self.buy(price, self.fixed_size)
        elif np.cumsum(np.array(self.signal))[-1] < -self.n1:  # 向下突破次数累积到一定的量
            if self.pos == 0:
                price: float = bar.close_price - self.price_add
                self.short(price, self.fixed_size)
            elif self.pos > 0:
                price: float = bar.close_price - self.price_add
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
