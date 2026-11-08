"""Market data: validation, synthetic demo panel, and point-in-time state.

The lab uses a long-format CSV as its public data contract::

    date,ticker,open,high,low,close,volume[,spread_bps]

``spread_bps`` is optional. When it is absent the spread proxy is the
Corwin-Schultz (2012) high-low estimator, computed only from data at or before
the as-of date. When it is present, it is treated as an observed quoted spread
and is still bounded by the configured floor and cap.

Nothing in this module reaches the network. A user with a licensed vendor
snapshot converts it to this schema outside the repository; the synthetic panel
is what makes the demo reproducible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .config import MarketConfig

#: Required long-format columns.
REQUIRED_COLUMNS = ("date", "ticker", "open", "high", "low", "close", "volume")

#: Optional columns.
OPTIONAL_COLUMNS = ("spread_bps",)


class DataError(ValueError):
    """Raised when a panel violates the data contract."""


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #


@dataclass
class Panel:
    """Daily OHLCV panel, wide by field.

    All frames share the same DatetimeIndex and ticker columns. NaN values are
    allowed (a ticker may not have started trading yet), but a column that is
    entirely NaN is rejected.
    """

    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    open: pd.DataFrame
    volume: pd.DataFrame
    spread_bps: pd.DataFrame | None = None
    source: str = "unknown"

    def __post_init__(self) -> None:
        fields = {
            "close": self.close,
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "volume": self.volume,
        }
        for name, frame in fields.items():
            if not isinstance(frame, pd.DataFrame):
                raise DataError(f"{name} must be a DataFrame")
            frame = frame.copy()
            frame.index = pd.to_datetime(frame.index)
            frame = frame.sort_index()
            frame.columns = [str(c) for c in frame.columns]
            fields[name] = frame

        reference = fields["close"]
        if reference.empty:
            raise DataError("close panel is empty")
        for name, frame in fields.items():
            if not frame.index.equals(reference.index):
                raise DataError(f"{name} index does not match close")
            if list(frame.columns) != list(reference.columns):
                raise DataError(f"{name} columns do not match close")

        self.close = fields["close"].astype(float)
        self.high = fields["high"].astype(float)
        self.low = fields["low"].astype(float)
        self.open = fields["open"].astype(float)
        self.volume = fields["volume"].astype(float)

        if self.spread_bps is not None:
            spread = self.spread_bps.copy()
            spread.index = pd.to_datetime(spread.index)
            spread = spread.sort_index()
            spread.columns = [str(c) for c in spread.columns]
            if not spread.index.equals(reference.index):
                raise DataError("spread_bps index does not match close")
            if list(spread.columns) != list(reference.columns):
                raise DataError("spread_bps columns do not match close")
            self.spread_bps = spread.astype(float)

        validate_panel(self)

    @property
    def tickers(self) -> list[str]:
        return list(self.close.columns)

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.close.index)

    def slice_until(self, asof: str | pd.Timestamp) -> "Panel":
        """Return a copy containing rows dated at or before ``asof``."""
        asof = pd.Timestamp(asof)
        mask = self.close.index <= asof
        if not mask.any():
            raise DataError(f"no data at or before {asof.date()}")
        return Panel(
            close=self.close.loc[mask],
            high=self.high.loc[mask],
            low=self.low.loc[mask],
            open=self.open.loc[mask],
            volume=self.volume.loc[mask],
            spread_bps=None if self.spread_bps is None else self.spread_bps.loc[mask],
            source=self.source,
        )

    def to_long(self) -> pd.DataFrame:
        """Return the long-format frame used by :func:`save_panel_csv`."""
        frames = []
        for field in ("open", "high", "low", "close", "volume", "spread_bps"):
            frame = getattr(self, field)
            if frame is None:
                continue
            # ``future_stack=True`` is the pandas 2.1+ implementation. Missing
            # values are dropped per field and re-aligned by the concat below;
            # a fully missing (date, ticker) row disappears, which is equivalent
            # to a NaN under the pivot loader.
            stacked = frame.stack(future_stack=True).rename(field)
            frames.append(stacked)
        long = pd.concat(frames, axis=1)
        long.index.names = ["date", "ticker"]
        long = long.reset_index()
        return long

    def content_hash(self) -> str:
        """Stable hash of the numeric content, used in run manifests."""
        long = self.to_long().sort_values(["date", "ticker"]).reset_index(drop=True)
        payload = long.to_csv(index=False, float_format="%.12g").encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


def validate_panel(panel: Panel) -> None:
    """Check the data contract and raise :class:`DataError` on violation."""
    close, high, low, open_, volume = (
        panel.close,
        panel.high,
        panel.low,
        panel.open,
        panel.volume,
    )

    for name, frame in {
        "close": close,
        "high": high,
        "low": low,
        "open": open_,
        "volume": volume,
    }.items():
        if not frame.index.is_monotonic_increasing:
            raise DataError(f"{name} index is not sorted")
        if frame.index.has_duplicates:
            raise DataError(f"{name} index has duplicate dates")
        if frame.columns.has_duplicates:
            raise DataError(f"{name} has duplicate tickers")
        if (frame < 0).any().any():
            raise DataError(f"{name} contains negative values")
        if np.isinf(frame.to_numpy(dtype=float)).any():
            raise DataError(f"{name} contains infinite values")
        if frame.isna().all(axis=0).any():
            bad = frame.columns[frame.isna().all(axis=0)].tolist()
            raise DataError(f"{name} is entirely NaN for {bad}")

    prices = {"close": close, "high": high, "low": low, "open": open_}
    for name, frame in prices.items():
        if (frame.dropna() <= 0).any().any():
            raise DataError(f"{name} contains non-positive prices")

    valid = high.notna() & low.notna()
    if (high < low).where(valid, False).any().any():
        raise DataError("high < low on at least one row")

    tol = 1e-8
    for name, frame in (("open", open_), ("close", close)):
        pair = high.notna() & frame.notna()
        if (high + tol < frame).where(pair, False).any().any():
            raise DataError(f"high < {name} on at least one row")
        pair = low.notna() & frame.notna()
        if (low - tol > frame).where(pair, False).any().any():
            raise DataError(f"low > {name} on at least one row")

    if panel.spread_bps is not None:
        spread = panel.spread_bps
        if (spread.dropna() < 0).any().any():
            raise DataError("spread_bps contains negative values")
        if np.isinf(spread.to_numpy(dtype=float)).any():
            raise DataError("spread_bps contains infinite values")


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #


def load_panel_csv(path: str | Path) -> Panel:
    """Load a long-format CSV into a :class:`Panel`."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    raw = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise DataError(f"missing columns: {missing}")
    raw["date"] = pd.to_datetime(raw["date"])
    raw["ticker"] = raw["ticker"].astype(str)
    if raw.duplicated(["date", "ticker"]).any():
        raise DataError("duplicate (date, ticker) rows")

    # Preserve the first-appearance order. Strategy definitions such as the
    # 60/40 demo depend on column order, and a silent alphabetical re-sort would
    # change the strategy rather than the data.
    tickers = list(dict.fromkeys(raw["ticker"]))

    def wide(field: str) -> pd.DataFrame:
        return (
            raw.pivot(index="date", columns="ticker", values=field)
            .sort_index()
            .reindex(columns=tickers)
        )

    spread = wide("spread_bps") if "spread_bps" in raw.columns else None
    return Panel(
        close=wide("close"),
        high=wide("high"),
        low=wide("low"),
        open=wide("open"),
        volume=wide("volume"),
        spread_bps=spread,
        source=str(path),
    )


def save_panel_csv(panel: Panel, path: str | Path) -> Path:
    """Write a panel in the long-format contract; return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_long().to_csv(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# Spread proxy
# --------------------------------------------------------------------------- #


def corwin_schultz_spread_bps(panel: Panel) -> pd.DataFrame:
    """Corwin-Schultz (2012) high-low spread estimator, in basis points.

    The estimator uses two consecutive daily high-low ranges to separate the
    bid-ask spread from volatility. Negative estimates are set to NaN rather
    than zero: a negative value is evidence that the estimator is outside its
    assumptions, not evidence of a zero spread. The caller takes a rolling
    median and applies the floor.

    Reference: Corwin, S. A., & Schultz, P. (2012). A simple way to estimate
    bid-ask spreads from daily high and low prices. *Journal of Finance*, 67(2),
    719-760.
    """
    high = panel.high
    low = panel.low
    hl = np.log(high / low)
    beta = hl**2 + hl.shift(-1) ** 2
    high2 = np.maximum(high, high.shift(-1))
    low2 = np.minimum(low, low.shift(-1))
    gamma = np.log(high2 / low2) ** 2
    denom = 3.0 - 2.0 * np.sqrt(2.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / denom
        alpha = alpha - np.sqrt(gamma / denom)
    alpha = alpha.clip(-10.0, 10.0)
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    spread = spread.where(spread > 0)
    return spread * 1e4


# --------------------------------------------------------------------------- #
# Market state
# --------------------------------------------------------------------------- #


@dataclass
class MarketState:
    """Point-in-time inputs to the cost model, one value per ticker."""

    asof: pd.Timestamp
    price: pd.Series
    adv_shares: pd.Series
    sigma_daily: pd.Series
    spread_bps: pd.Series

    def __post_init__(self) -> None:
        self.asof = pd.Timestamp(self.asof)
        tickers = list(self.price.index)
        for name in ("adv_shares", "sigma_daily", "spread_bps"):
            series = getattr(self, name)
            if not series.index.equals(self.price.index):
                raise DataError(f"{name} index does not match price")
            if (series.dropna() < 0).any():
                raise DataError(f"{name} contains negative values")
            setattr(self, name, series.astype(float))
        self.price = self.price.astype(float)
        if (self.price.dropna() <= 0).any():
            raise DataError("price contains non-positive values")
        if len(tickers) == 0:
            raise DataError("market state is empty")

    @property
    def tickers(self) -> list[str]:
        return list(self.price.index)

    def require_finite(self, tickers: Iterable[str] | None = None) -> None:
        """Raise if any required input is missing or non-positive."""
        selected = list(tickers) if tickers is not None else self.tickers
        for ticker in selected:
            values = {
                "price": self.price.get(ticker),
                "adv_shares": self.adv_shares.get(ticker),
                "sigma_daily": self.sigma_daily.get(ticker),
                "spread_bps": self.spread_bps.get(ticker),
            }
            for name, value in values.items():
                if value is None or not np.isfinite(value):
                    raise DataError(f"{name} is not finite for {ticker}")
            if values["price"] <= 0 or values["adv_shares"] <= 0:
                raise DataError(f"price/ADV must be positive for {ticker}")
            if values["sigma_daily"] <= 0:
                raise DataError(f"sigma_daily must be positive for {ticker}")


def compute_market_state(
    panel: Panel,
    asof: str | pd.Timestamp,
    config: MarketConfig | None = None,
) -> MarketState:
    """Estimate price, ADV, daily volatility, and spread using data <= ``asof``.

    This function is point-in-time by construction: it slices first, then
    computes. A test asserts that calling it on the full panel and on a
    truncated panel gives the same answer.
    """
    config = config or MarketConfig()
    asof = pd.Timestamp(asof)
    hist = panel.slice_until(asof)
    actual_asof = pd.Timestamp(hist.close.index[-1])

    price = hist.close.iloc[-1]
    adv = hist.volume.tail(config.adv_window).mean()
    returns = hist.close.pct_change(fill_method=None)
    sigma = returns.tail(config.vol_window).std(ddof=1)

    if hist.spread_bps is not None:
        spread = hist.spread_bps.tail(config.spread_window).median()
    else:
        spread = corwin_schultz_spread_bps(hist).tail(config.spread_window).median()

    # The multiplier is a robustness knob, not a calibration. It lets the
    # analysis ask whether a conclusion survives a different spread proxy.
    spread = spread * config.spread_multiplier
    spread = spread.clip(config.spread_floor_bps, config.spread_cap_bps)
    spread = spread.fillna(config.spread_floor_bps)

    return MarketState(
        asof=actual_asof,
        price=price,
        adv_shares=adv,
        sigma_daily=sigma,
        spread_bps=spread,
    )


# --------------------------------------------------------------------------- #
# Synthetic demo panel
# --------------------------------------------------------------------------- #

#: Six liquid-ETF archetypes. These are *stylised*, not calibrated estimates.
#: (ticker, market beta, idiosyncratic daily vol, initial price, base ADV shares,
#: base quoted spread in bps)
_DEFAULT_ASSETS: tuple[tuple[str, float, float, float, float, float], ...] = (
    ("SPY", 1.00, 0.0060, 300.0, 20_000_000, 1.5),
    ("TLT", -0.15, 0.0080, 120.0, 10_000_000, 2.5),
    ("GLD", 0.05, 0.0090, 180.0, 3_000_000, 3.0),
    ("EEM", 0.90, 0.0110, 45.0, 15_000_000, 4.0),
    ("HYG", 0.55, 0.0050, 80.0, 8_000_000, 5.0),
    ("VNQ", 0.70, 0.0100, 90.0, 2_000_000, 6.0),
)


def make_synthetic_panel(
    seed: int = 20261108,
    start: str = "2018-01-02",
    periods: int = 1825,
    assets: Iterable[tuple[str, float, float, float, float, float]] | None = None,
) -> Panel:
    """Generate a deterministic synthetic ETF panel.

    The generator is a stylised factor model, not a market simulator:

    * a common market factor with AR(1) log-volatility and a 2020-like shock;
    * asset returns with beta, fat-tailed idiosyncratic noise, and a small drift;
    * intraday high/low ranges that are wide enough to be plausible but are not
      calibrated to a real order book;
    * volume with weekday seasonality, volatility linkage, and log-normal noise;
    * time-varying quoted spreads.

    The same seed always produces the same panel. The checked-in demo CSV is
    generated by this function; see ``scripts/make_demo_data.py``.
    """
    assets = tuple(assets) if assets is not None else _DEFAULT_ASSETS
    if periods < 60:
        raise ValueError("periods must be at least 60")
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start=start, periods=periods, name="date")

    # Market factor: AR(1) log-vol plus a Gaussian shock around 30% of the sample.
    log_vol = np.empty(periods)
    log_vol[0] = np.log(0.008)
    for t in range(1, periods):
        log_vol[t] = 0.97 * log_vol[t - 1] + 0.03 * np.log(0.008)
        log_vol[t] += 0.08 * rng.normal()
    vol = np.exp(log_vol)
    shock_center = int(0.30 * periods)
    vol *= 1.0 + 2.5 * np.exp(-0.5 * ((np.arange(periods) - shock_center) / 30.0) ** 2)

    market = 0.00020 + vol * rng.normal(size=periods)

    weekday = np.array([1.10, 1.00, 0.98, 1.00, 1.05])
    weekday_factor = weekday[index.dayofweek]

    close_frames: dict[str, pd.Series] = {}
    open_frames: dict[str, pd.Series] = {}
    high_frames: dict[str, pd.Series] = {}
    low_frames: dict[str, pd.Series] = {}
    volume_frames: dict[str, pd.Series] = {}
    spread_frames: dict[str, pd.Series] = {}

    for ticker, beta, idio_base, initial, base_adv, base_spread in assets:
        # Fat-tailed idiosyncratic noise, scaled to unit variance.
        idio = idio_base * (0.6 + 0.8 * vol / vol.mean())
        z = rng.standard_t(df=5, size=periods) / np.sqrt(5.0 / 3.0)
        returns = beta * market + idio * z + 0.00008
        close = initial * np.cumprod(1.0 + returns)
        close = np.maximum(close, 1.0)

        sigma = np.abs(returns)
        sigma = pd.Series(sigma).rolling(5, min_periods=1).mean().to_numpy()

        open_ = np.empty(periods)
        open_[0] = close[0]
        overnight = 0.15 * sigma[1:] * rng.normal(size=periods - 1)
        open_[1:] = close[:-1] * np.exp(overnight)

        spread_frac = base_spread / 1e4
        half_range = np.abs(rng.normal(scale=0.55 * sigma)) + 0.5 * spread_frac
        high = np.maximum(open_, close) * (1.0 + half_range)
        low = np.minimum(open_, close) * (1.0 - 0.90 * half_range)
        low = np.maximum(low, 1e-3)

        volume = (
            base_adv
            * np.exp(0.25 * rng.normal(size=periods))
            * weekday_factor
            * (1.0 + 0.8 * np.abs(returns) / np.maximum(sigma, 1e-6))
            * (1.0 + 0.03 * np.arange(periods) / 252.0)
        )
        volume = np.maximum(np.round(volume), 1_000.0)

        spread = (
            base_spread
            * (0.7 + 0.6 * vol / vol.mean())
            * np.exp(0.15 * rng.normal(size=periods))
        )
        spread = np.clip(spread, 0.5, 100.0)

        close_frames[ticker] = pd.Series(close, index=index)
        open_frames[ticker] = pd.Series(open_, index=index)
        high_frames[ticker] = pd.Series(high, index=index)
        low_frames[ticker] = pd.Series(low, index=index)
        volume_frames[ticker] = pd.Series(volume, index=index)
        spread_frames[ticker] = pd.Series(spread, index=index)

    return Panel(
        close=pd.DataFrame(close_frames),
        high=pd.DataFrame(high_frames),
        low=pd.DataFrame(low_frames),
        open=pd.DataFrame(open_frames),
        volume=pd.DataFrame(volume_frames),
        spread_bps=pd.DataFrame(spread_frames),
        source=f"synthetic(seed={seed})",
    )


def default_demo_data_path() -> Path:
    """Resolve the checked-in demo panel without depending on the CWD.

    A source checkout has the panel at ``<repo>/data/demo/etf_daily.csv``. If the
    command is run from elsewhere, the package-relative path is used. If neither
    exists, the CWD path is returned so the caller can generate it.
    """
    cwd_path = Path.cwd() / "data" / "demo" / "etf_daily.csv"
    if cwd_path.exists():
        return cwd_path
    repo_path = Path(__file__).resolve().parents[2] / "data" / "demo" / "etf_daily.csv"
    if repo_path.exists():
        return repo_path
    return cwd_path


def load_or_make_demo_panel(
    path: str | Path,
    *,
    seed: int = 20261108,
    force: bool = False,
) -> Panel:
    """Load the checked-in demo panel, or regenerate it deterministically."""
    path = Path(path)
    if force or not path.exists():
        panel = make_synthetic_panel(seed=seed)
        save_panel_csv(panel, path)
        return panel
    return load_panel_csv(path)


#: A small helper for callers that want a plain dict rather than a Panel.
def panel_shapes(panel: Panel) -> dict[str, tuple[int, int]]:
    return {
        "close": panel.close.shape,
        "high": panel.high.shape,
        "low": panel.low.shape,
        "open": panel.open.shape,
        "volume": panel.volume.shape,
    }


def ticker_summary(panel: Panel) -> Mapping[str, dict[str, float]]:
    """Convenience summary used by the demo and tests."""
    return {
        ticker: {
            "start": panel.close[ticker].first_valid_index(),
            "end": panel.close[ticker].last_valid_index(),
            "mean_price": float(panel.close[ticker].mean()),
            "mean_adv_shares": float(panel.volume[ticker].mean()),
        }
        for ticker in panel.tickers
    }
