import os
import time
import logging
from typing import Any
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s │ %(message)s")
logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
BASE_URL       = "https://api.notion.com/v1"
PAGE_SIZE      = 100

class NotionClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })

    def query_database(self, database_id: str, sorts: list | None = None) -> list[dict]:
        url  = f"{BASE_URL}/databases/{database_id}/query"
        body = {"page_size": PAGE_SIZE}
        if sorts: body["sorts"] = sorts
        results = []
        cursor = None
        while True:
            if cursor: body["start_cursor"] = cursor
            resp = self.session.post(url, json=body).json()
            if "results" in resp: results.extend(resp["results"])
            if not resp.get("has_more"): break
            cursor = resp.get("next_cursor")
        return results

def _extract_number(prop: dict) -> float | None:
    if not prop: return None
    ptype = prop.get("type")
    if ptype == "number": return prop.get("number")
    if ptype == "formula" and prop.get("formula", {}).get("type") == "number": return prop.get("formula", {}).get("number")
    if ptype == "rollup":
        r = prop.get("rollup", {})
        if r.get("type") == "number": return r.get("number")
        if r.get("type") == "array":
            nums = [item.get("number", 0) for item in r.get("array", []) if item.get("type") == "number"]
            return sum(nums) if nums else 0.0
    return None

def _prop(props: dict, key: str) -> Any:
    prop = props.get(key)
    if not prop: return None
    ptype = prop.get("type")
    if ptype == "select": return prop.get("select")["name"] if prop.get("select") else None
    if ptype in ["title", "rich_text"]: return "".join(t.get("plain_text", "") for t in prop.get(ptype, []))
    if ptype == "date": return prop.get("date")["start"] if prop.get("date") else None
    return _extract_number(prop)

def _fuzzy_num(props: dict, keywords: list) -> float:
    for k in props.keys():
        if any(kw in k.lower() for kw in keywords):
            val = _extract_number(props[k])
            if val is not None: return float(val)
    return 0.0

def load_transactions(client: NotionClient, db_id: str) -> pd.DataFrame:
    pages = client.query_database(db_id, sorts=[{"property": "Data", "direction": "ascending"}])
    records = []
    for page in pages:
        p = page.get("properties", {})
        tipo_str = str(_prop(p, "Tipo de Transação") or "").lower()

        # Força bruta no sinal matemático
        raw_val = float(_prop(p, "Valor Ajustado") or _prop(p, "Valor") or 0.0)
        if "despesa" in tipo_str:
            amount = -abs(raw_val)
        elif "receita" in tipo_str:
            amount = abs(raw_val)
        else:
            amount = raw_val # Transferências

        records.append({
            "date": _prop(p, "Data") or page.get("created_time", "")[:10],
            "description": _prop(p, "Descrição"),
            "amount": amount,
            "type": _prop(p, "Tipo de Transação"),
            "context": _prop(p, "Contexto"),
        })
    df = pd.DataFrame(records)
    if df.empty: return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["is_internal"] = (df["description"].str.contains(r"→", na=False, regex=True) | df["type"].str.lower().str.contains("transfer", na=False))
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

def load_accounts(client: NotionClient, db_id: str) -> pd.DataFrame:
    pages = client.query_database(db_id)
    records = []
    for page in pages:
        p = page.get("properties", {})

        # Leitura exata e travada (sem adivinhação para não puxar o Inicial)
        bal = _prop(p, "Saldo Atual")
        if bal is None: bal = _prop(p, "Saldo")
        if bal is None: bal = 0.0

        records.append({
            "account": _prop(p, "Conta"),
            "balance": float(bal),
            "currency": _prop(p, "Moeda Principal")
        })
    df = pd.DataFrame(records)
    return df.dropna(subset=["account"]).reset_index(drop=True) if not df.empty else df

def load_budgets(client: NotionClient, db_id: str) -> pd.DataFrame:
    pages = client.query_database(db_id)
    records = []
    for page in pages:
        p = page.get("properties", {})
        records.append({
            "category": _prop(p, "Categoria"),
            "type": _prop(p, "Tipo"),
            "budget": _fuzzy_num(p, ["orçament", "teto"]),
            "spent_period": _fuzzy_num(p, ["gasto"]),
        })
    df = pd.DataFrame(records)
    if df.empty: return df
    df["pct_used"] = df.apply(lambda r: min(r["spent_period"] / r["budget"] * 100, 999.0) if r["budget"] > 0 else 0.0, axis=1)
    return df.dropna(subset=["category"]).sort_values("spent_period", ascending=False).reset_index(drop=True)

def load_travel(client: NotionClient, db_id: str) -> pd.DataFrame:
    pages = client.query_database(db_id)
    records = []
    for page in pages:
        p = page.get("properties", {})
        
        # Caçador de datas: varre todas as colunas e pega a primeira que for do tipo "date"
        dt_val = None
        for k, v in p.items():
            if v and isinstance(v, dict) and v.get("type") == "date" and v.get("date"):
                dt_val = v["date"].get("start")
                break
                
        records.append({
            "trip_name": _prop(p, "Nome da Viagem"),
            "budget_ceiling": _fuzzy_num(p, ["teto", "orçament"]),
            "actual_spent": _fuzzy_num(p, ["gasto", "real"]),
            "start_date": dt_val
        })
    df = pd.DataFrame(records)
    if not df.empty:
        # Força o formato de data e arranca o fuso horário para o Plotly não bugar
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.tz_localize(None)
    return df.dropna(subset=["trip_name"]).sort_values("actual_spent", ascending=False).reset_index(drop=True)

def load_all(token: str, db_transactions: str, db_accounts: str, db_budgets: str, db_travel: str) -> dict:
    client = NotionClient(token)
    return {
        "transactions": load_transactions(client, db_transactions),
        "accounts": load_accounts(client, db_accounts) if db_accounts else pd.DataFrame(),
        "budgets": load_budgets(client, db_budgets) if db_budgets else pd.DataFrame(),
        "travel": load_travel(client, db_travel) if db_travel else pd.DataFrame(),
    }
