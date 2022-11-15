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
    """CPV策略"""

    author = "VeighNa Elite"

    price_add = 5           # 委托超价
    fixed_size = 1          # 委托数量

    pv = 0                  # 修正持仓量和收盘价的相关系数

    parameters = [
        "window",
        "price_add",
        "fixed_size"
    ]

    variables = [
        "pv"
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

        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(500)     # 起码容纳一天以上的分钟数据

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
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 新的一天
        if not self.last_bar or self.last_bar.datetime.day != bar.datetime.day:
            self.last_bar = bar
            self.count = 1  # 当天第一根K线
            return
        # 收盘执行计算
        elif bar.datetime.minute == 59 and bar.datetime.hour == 14:
            self.count += 1

            # 使用DataFrame作为统计数据容器
            df = pd.DataFrame()

            # 读取成交量数据
            df['vt'] = am.volume_array[-self.count:]

            # 检查异常的成交量数据
            if 0 in np.array(df['vt']):
                return

            # 计算成交量变化
            df['pre_vt'] = am.volume_array[-self.count-1:-1]
            df['vt_change'] = df['vt'] - df['pre_vt']

            # 计算持仓量变化
            df['oi'] = am.open_interest_array[-self.count:]
            df['pre_oi'] = am.open_interest_array[-self.count-1:-1]
            df['oi_change'] = df['oi'] - df['pre_oi']

            # 当天持仓量变化
            delta_oi = df['oi'].iloc[-1] - df['oi'].iloc[0]

            # 当天成交量变化的累积
            delta_vt = df['vt_change'][1:].sum()  

            # T+1交易者的贡献
            df['oi_t1'] = df['vt_change'] * delta_oi / delta_vt

            # T+0交易者的贡献
            df['oi_t0'] = -1 * (df['oi_change'] - df['oi_t1'])

            # 计算修正持仓量
            df['mod_delta_oi'] = df['oi_t0'] + df['oi_t1']
            df['mod_delta_oi'][0] = df['oi'][0]
            df['mod_oi'] = df['mod_delta_oi'].cumsum()

            # 修正持仓量和收盘价的相关系数
            df['close_price'] = am.close_array[-self.count:]
            self.pv = df['close_price'].corr(df['mod_oi'])

            # 执行交易
            if self.pv > 0:
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
        # 其他日内时间等待
        else:
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
