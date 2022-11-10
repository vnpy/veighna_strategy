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


class ExtremeValueFollowStrategy(CtaTemplate):
    """极值跟随策略"""

    author = "VeighNa Elite"

    extreme_window = 9         # 数据量偏移参数
    min_count = 6        # 信号截断阈值
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 5              # 日内窗口频率的K线，默认为5分钟，可修改

    parameters = [
        "extreme_window",
        "min_count",
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

        self.bg = BarGenerator(self.on_bar, self.window, self.on_window_bar)
        self.am = ArrayManager()

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

    def on_window_bar(self, bar: BarData) -> None:
        """N分钟K线推送"""
        # 更新到ArrayManager
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 新的一天做个初始化，count设置为1
        if not self.last_bar or self.last_bar.datetime.day != bar.datetime.day:
            self.bar_count = 1
        # 不是新的一天。那么先检验是否到了计算信号的要求
        else:
            # 更新今日K线数量统计
            self.bar_count += 1

            # 当天开盘已经经过了一定数量的K线，满足计算信号的要求
            if self.bar_count > self.min_count:
                # 计算时序数组切片索引
                start: int = -self.bar_count
                end: int = -self.bar_count + max(self.bar_count - self.extreme_window, 1)

                # 计算极大值和极小值
                high_extreme: float = am.high_array[start:end].max()
                low_extreme: float = am.low_array[start:end].min()

                if bar.close_price > high_extreme:  # 买
                    price: float = bar.close_price + self.price_add
                    if not self.pos:
                        self.buy(price, self.fixed_size)
                    elif self.pos < 0:
                        self.cover(price, abs(self.pos))
                        self.buy(price, self.fixed_size)
                elif bar.close_price < low_extreme:  # 卖
                    price: float = bar.close_price - self.price_add
                    if not self.pos:
                        self.short(price, self.fixed_size)
                    elif self.pos > 0:
                        self.sell(price, abs(self.pos))
                        self.short(price, self.fixed_size)

        # 记录当前K线
        self.last_bar = bar

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
