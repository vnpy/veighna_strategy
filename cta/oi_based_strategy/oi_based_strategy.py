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


class OiBasedStrategy(CtaTemplate):
    """持仓量策略"""

    author = "VeighNa Elite"

    ma_P_length = 19         # 激进交易的态度窗口长度，研报默认为4
    ma_Q_length = 17        # 激进交易的分歧度窗口长度，研报默认为5
    K = 0.1                # 当天总成交量的比率，研报默认是10%
    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量
    window = 1              # 日内窗口频率的K线，研报默认为1分钟，可修改

    parameters = [
        "ma_P_length",
        "ma_Q_length",
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
        self.old_bar: BarData = None
        self.P_array: np.ndarray = np.zeros(self.ma_P_length)
        self.Q_array: np.ndarray = np.zeros(self.ma_Q_length)
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

        if not self.old_bar or self.old_bar.datetime.day != bar.datetime.day:
            self.old_bar = bar
            self.count = 1  # 当天第一根K线
            return

        elif bar.datetime.minute == 59 and bar.datetime.hour == 14:
            # 当前已经收盘，开始计算
            self.count += 1
            # 先计算Rt再计算Vt
            Rt_array = (am.close_array[-self.count:] - am.close_array[-self.count - 1: -1]) / am.close_array[-self.count - 1: -1]
            Vt_array = am.volume_array[-self.count:]

            if 0 in Vt_array:  # 错误数据
                return

            Oi_array = am.open_interest_array[-self.count:] - am.open_interest_array[-self.count - 1: -1]
            St_P_array = abs(Rt_array)/np.sqrt(Vt_array)  # 激进交易的态度
            St_Q_array = abs(Oi_array)/np.sqrt(Vt_array)  # 激进交易的分歧
            V_total = sum(Vt_array)
            V = V_total * self.K
            cum_v = 0
            P = 0
            Q = 0
            while 1:  # 计算P
                index = np.where(St_P_array == np.max(St_P_array))  # 最大值所在的索引
                index = index[-1]
                index = index[-1]  # 必须要有，否则index不唯一会报错
                cum_v = cum_v + Vt_array[index]  # 成交量累积
                P = P + Rt_array[index]  # 更新P
                Vt_array = np.delete(Vt_array, index)  # 把当前最大值剔除掉，方便下次索引最大值
                Rt_array = np.delete(Rt_array, index)
                St_P_array = np.delete(St_P_array, index)

                if cum_v >= V:  # 超过了当天总成交量的特定比例
                    cum_v = 0
                    Vt_array = am.volume_array[-self.count:]
                    # 先重新弄一下这个，因为上面已经delete了

                    break

            while 1:  # 计算Q
                index = np.where(St_Q_array == np.max(St_Q_array))
                index = index[-1]
                index = index[-1]
                cum_v = cum_v + Vt_array[index]
                Q = Q + Oi_array[index]  # 更新Q

                Vt_array = np.delete(Vt_array, index)  # 把当前最大值剔除掉，方便下次索引最大值
                Oi_array = np.delete(Oi_array, index)
                St_Q_array = np.delete(St_Q_array, index)

                if cum_v >= V:
                    cum_v = 0
                    break

            # 此时P和Q都已经算完了，检查P和Q的序列是否到了窗口数量，因为要算MA
            if self.P_count < self.ma_P_length or self.Q_count < self.ma_Q_length:  # 不够数量
                self.P_count += 1
                self.Q_count += 1
                self.P_array[:-1] = self.P_array[1:]
                self.Q_array[:-1] = self.Q_array[1:]
                self.P_array[-1] = P  # 更新直到数据量够再进行下面的交易
                self.Q_array[-1] = Q
                return

            else:  # 可以交易了，也要先更新P和Q的序列
                self.P_array[:-1] = self.P_array[1:]
                self.Q_array[:-1] = self.Q_array[1:]
                self.P_array[-1] = P
                self.Q_array[-1] = Q
                P = P - self.P_array.mean()
                Q = Q - self.Q_array.mean()

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
                print("仓位是:", self.pos)

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
