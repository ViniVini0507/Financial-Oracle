from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

@dataclass
class ForecastResult:
    burn_rate_daily: float
    current_balance: float
    days_until_zero: float | None
    projection: pd.DataFrame
    historical: pd.DataFrame

def forecast_balance(transactions_df: pd.DataFrame, current_balance: float, horizon_days: int = 30, method: str = "ema", ema_span: int = 14, extra_expenses: list = None, burn_override: float = None) -> ForecastResult:
    extra_expenses = extra_expenses or []

    df = transactions_df[~transactions_df["is_internal"]].copy()
    if df.empty: df = pd.DataFrame({"date": [pd.Timestamp.today().normalize()], "amount": [0.0]})

    daily = df.groupby(df["date"].dt.normalize())["amount"].sum().rename("net_flow").reset_index()
    full_range = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    daily = daily.set_index("date").reindex(full_range, fill_value=0.0)
    daily.index.name = "date"
    daily = daily.reset_index()

    if burn_override is not None:
        burn_rate = burn_override
    else:
        burn_rate = float(daily["net_flow"].ewm(span=ema_span, adjust=False).mean().iloc[-1]) if method == "ema" else float(LinearRegression().fit(np.arange(len(daily)).reshape(-1, 1), daily["net_flow"].values).coef_[0])

    last_date = daily["date"].iloc[-1]
    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")
    proj_df = pd.DataFrame({"date": future_dates, "balance": current_balance + burn_rate * np.arange(1, horizon_days + 1)})

    for exp in extra_expenses:
        proj_df.loc[proj_df["date"] >= pd.Timestamp(exp["date"]), "balance"] += float(exp["amount"])

    zero_mask = proj_df["balance"] <= 0
    days_until_zero = float((proj_df.loc[zero_mask.idxmax(), "date"] - pd.Timestamp.today().normalize()).days) if zero_mask.any() else None

    daily["balance"] = daily["net_flow"].cumsum() + (current_balance - float(daily["net_flow"].cumsum().iloc[-1]))

    return ForecastResult(burn_rate, current_balance, days_until_zero, proj_df, daily)