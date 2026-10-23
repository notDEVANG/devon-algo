"""Cost model for NSE equity DELIVERY trades through Angel One.

Rates were checked against Angel One's and third-party fee pages in Oct 2026, but
brokers change plans. Compare one real contract note with this model and edit the
numbers below. Slippage is an ASSUMPTION, not a measurement.
"""
from dataclasses import dataclass


@dataclass
class CostModel:
    # Sources disagree on delivery brokerage: Angel's own page says Rs 0, a partner
    # page says lower of Rs 20 or 0.1% (min Rs 5). Default = the conservative one.
    brokerage_mode: str = "capped"      # "zero" or "capped"
    brokerage_cap_rupees: float = 20.0
    brokerage_pct: float = 0.001
    brokerage_min: float = 5.0
    stt_pct: float = 0.001              # 0.1% on BOTH buy and sell (delivery)
    stamp_pct: float = 0.00015          # 0.015% on buy only
    exchange_pct: float = 0.0000345     # NSE transaction charge, ~0.00345%
    sebi_pct: float = 0.000001          # Rs 10 per crore
    gst_pct: float = 0.18               # on brokerage + exchange + SEBI (and DP)
    dp_rupees: float = 20.0             # per stock sold, plus GST
    slippage_pct: float = 0.001         # 0.10% per side, adverse (assumption)

    def brokerage(self, value: float) -> float:
        if self.brokerage_mode == "zero":
            return 0.0
        return max(self.brokerage_min, min(self.brokerage_cap_rupees, self.brokerage_pct * value))

    def fees(self, side: str, value: float) -> float:
        """Rupee fees and taxes for one order of this traded value (excl. slippage)."""
        b = self.brokerage(value)
        exch = value * self.exchange_pct
        sebi = value * self.sebi_pct
        total = b + exch + sebi + self.gst_pct * (b + exch + sebi) + value * self.stt_pct
        if side == "buy":
            total += value * self.stamp_pct
        else:
            total += self.dp_rupees * (1 + self.gst_pct)
        return total

    def fill_price(self, side: str, ref: float) -> float:
        """Reference price moved against us by slippage."""
        return ref * (1 + self.slippage_pct) if side == "buy" else ref * (1 - self.slippage_pct)