import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from forecasting import forecast_balance
from notion_etl import load_all

# Configurações de Página
st.set_page_config(page_title="Finance Oracle", layout="wide")

# CSS Avançado para Destaque de Saldos e UI
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Syne', sans-serif; }

:root {
    --bg: #0d0f14; --surface: #151820; --border: #232735;
    --accent: #f5a623; --accent2: #3ecfcf; --text: #e8eaf0;
    --muted: #6b7280; --danger: #ef4444; --success: #22c55e;
}

.stApp { background: var(--bg); color: var(--text); }

/* Card de Saldo Master */
.balance-card {
    background: #1a1c24;
    border-radius: 16px;
    padding: 25px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.balance-label {
    color: var(--muted);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    font-weight: 700;
    margin-bottom: 10px;
}
.balance-value {
    font-size: 3rem;
    font-weight: 800;
    margin: 0;
}
.balance-sub {
    color: #4b5563;
    font-size: 0.8rem;
    margin-top: 8px;
}

[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
[data-testid="stForm"] { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

EUR = lambda v: f"€ {v:,.2f}"
PLOTLY_LAYOUT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Syne", color="#e8eaf0"), margin=dict(l=0, r=0, t=30, b=0))

@st.cache_data(ttl=300)
def fetch_all(token, db_tx, db_acc, db_bud, db_trv):
    return load_all(token, db_tx, db_acc, db_bud, db_trv)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## ◈ Finance Oracle")
    notion_token = st.text_input("Notion Token", value=st.secrets.get("NOTION_TOKEN", ""), type="password")
    db_tx = st.text_input("Transações ID", value=st.secrets.get("NOTION_DB_TRANSACTIONS", ""))
    db_acc = st.text_input("Contas ID", value=st.secrets.get("NOTION_DB_ACCOUNTS", ""))
    db_bud = st.text_input("Orçamentos ID", value=st.secrets.get("NOTION_DB_BUDGETS", ""))
    db_trv = st.text_input("Viagens ID", value=st.secrets.get("NOTION_DB_TRAVEL", ""))

    st.divider()
    splitwise_receivable = st.number_input("Splitwise a Receber (€)", value=109.18, step=10.0)
    horizon = st.slider("Horizonte de Previsão", 15, 90, 30)
    if st.button("🔄 Limpar Cache"):
        st.cache_data.clear()
        st.rerun()

if not (notion_token and db_tx):
    st.warning("Configure as IDs na lateral.")
    st.stop()

# --- DATA LOAD ---
data = fetch_all(notion_token, db_tx, db_acc, db_bud, db_trv)
df_tx, df_acc, df_bud, df_trv = data["transactions"], data["accounts"], data["budgets"], data["travel"]

# Isola Caixas
is_eurotrip = df_acc["account"].str.contains("Eurotrip", case=False, na=False)
is_viagens = df_acc["account"].str.contains("Viagens", case=False, na=False)

df_acc_geral = df_acc[~is_eurotrip & ~is_viagens]
df_acc_viagens = df_acc[is_viagens & ~is_eurotrip]
df_acc_eurotrip = df_acc[is_eurotrip]

df_tx_geral = df_tx[~df_tx["context"].str.contains("Eurotrip", case=False, na=False)]

# Cálculo de Saldos
saldo_geral = df_acc_geral[df_acc_geral["currency"] == "EUR"]["balance"].sum()
caixa_sobrevivencia = saldo_geral + splitwise_receivable
caixa_viagens = df_acc_viagens["balance"].sum()

if "extra_expenses" not in st.session_state: st.session_state.extra_expenses = []

# --- TABS ---
tab_oracle, tab_budget, tab_travel, tab_eurotrip, tab_accounts, tab_db = st.tabs([
    "📈 Oracle (Dia a Dia)", "📊 Categorias", "✈️ Viagens", "🌍 Eurotrip", "🏦 Contas", "🗃️ Base"
])

# --- TAB 1: ORACLE ---
with tab_oracle:
    # DESTAQUE NOS SALDOS
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class="balance-card" style="border: 2px solid var(--accent2);">
            <p class="balance-label">Caixa Sobrevivência (Reims)</p>
            <h1 class="balance-value" style="color: var(--accent2);">{EUR(caixa_sobrevivencia)}</h1>
            <p class="balance-sub">Líquido (Geral + {EUR(splitwise_receivable)} do Splitwise)</p>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="balance-card" style="border: 2px solid var(--accent);">
            <p class="balance-label">Caixa Reservado (Viagens)</p>
            <h1 class="balance-value" style="color: var(--accent);">{EUR(caixa_viagens)}</h1>
            <p class="balance-sub">Travado para Barcelona e Próximas Trips</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # CONTROLES CFO
    cfo_col1, cfo_col2 = st.columns([1, 2])
    with cfo_col1:
        cfo_override = st.toggle("🎯 Modo CFO (Gasto Fixo)", key="cfo_on")
    with cfo_col2:
        manual_burn = st.slider("Ajustar Gasto Diário (€)", -100.0, 0.0, -15.0, 1.0) if cfo_override else None

    # Filtra os gastos simulados para abater apenas do caixa correto
    sim_sobrevivencia = [e for e in st.session_state.extra_expenses if e.get("conta", "Sobrevivência") == "Sobrevivência"]
    result = forecast_balance(df_tx_geral, caixa_sobrevivencia, horizon, burn_override=manual_burn, extra_expenses=sim_sobrevivencia)

    # KPIs Rápidos
    k1, k2, k3 = st.columns(3)
    k1.metric("Burn Rate Diário", EUR(result.burn_rate_daily))
    k2.metric(f"Projeção ({horizon}d)", EUR(result.projection["balance"].iloc[-1]))
    k3.metric("Fôlego de Caixa", f"{int(result.days_until_zero)} dias" if result.days_until_zero else "Seguro ✓")

    # Gráfico Oracle
   # Injetando as linhas pontilhadas (agora à prova de bugs matemáticos do Plotly)
    if not df_trv.empty and "start_date" in df_trv.columns:
        df_plot_trv = df_trv.dropna(subset=["start_date"])
        for _, row in df_plot_trv.iterrows():
            # Transforma a data em texto puro (YYYY-MM-DD) para evitar o erro do Plotly
            dt_string = row["start_date"].strftime("%Y-%m-%d")
            
            fig.add_vline(
                x=dt_string, 
                line_width=2, 
                line_dash="dash", 
                line_color="#ec4899",
                annotation_text=row["trip_name"], 
                annotation_position="top left", 
                annotation_font=dict(size=13, color="#ec4899")
            )

    fig.update_layout(**PLOTLY_LAYOUT, height=450, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("➕ Simular Gasto Extra (Não recorrente)"):
        with st.form("sim_form", clear_on_submit=True):
            f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 1])
            desc = f1.text_input("O que é?")
            conta_sim = f2.selectbox("De qual Caixa?", ["Sobrevivência", "Viagens", "Eurotrip"])
            dt = f3.date_input("Quando?")
            val = f4.number_input("Quanto (€)?", min_value=1.0, value=50.0)
            if f5.form_submit_button("Adicionar"):
                st.session_state.extra_expenses.append({"date": dt.isoformat(), "amount": -val, "label": desc, "conta": conta_sim})
                st.rerun()

# --- TAB 2: CATEGORIAS ---
with tab_budget:
    st.subheader("Análise de Orçamento")
    tipo = st.radio("Filtro:", ["Despesas", "Receitas"], horizontal=True)
    is_rec = df_bud["type"].str.lower().str.contains("receita", na=False)
    df_p = df_bud[~is_rec & ~df_bud["category"].str.contains("Eurotrip", case=False)] if tipo == "Despesas" else df_bud[is_rec]

    if not df_p.empty:
        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(y=df_p["category"], x=df_p["budget"], orientation="h", name="Meta", marker_color="rgba(55,65,81,0.5)"))
        colors = ["#ef4444" if p >= 100 else "#f5a623" if p >= 80 else "#3ecfcf" for p in df_p["pct_used"]]
        fig_b.add_trace(go.Bar(y=df_p["category"], x=df_p["spent_period"], orientation="h", name="Real", marker_color=colors, text=[f"{p:.0f}%" for p in df_p["pct_used"]], textposition="outside"))
        fig_b.update_layout(**PLOTLY_LAYOUT, barmode="overlay", yaxis=dict(autorange="reversed"), height=max(400, len(df_p)*45))
        st.plotly_chart(fig_b, use_container_width=True)

# --- TAB 3: VIAGENS ---
with tab_travel:
    st.subheader("Custo de Todas as Viagens")
    if not df_trv.empty:
        travel_palette = ["#3ecfcf", "#f5a623", "#a855f7", "#ec4899", "#22c55e", "#3b82f6"]
        color_array = [travel_palette[i % len(travel_palette)] for i in range(len(df_trv))]

        fig_t = go.Figure()
        fig_t.add_trace(go.Bar(y=df_trv["trip_name"], x=df_trv["budget_ceiling"], orientation="h", name="Teto", marker_color="rgba(55,65,81,0.5)"))
        fig_t.add_trace(go.Bar(y=df_trv["trip_name"], x=df_trv["actual_spent"], orientation="h", name="Gasto", marker_color=color_array, text=[EUR(a) for a in df_trv["actual_spent"]], textposition="outside", textfont=dict(size=15)))
        fig_t.update_layout(**PLOTLY_LAYOUT, barmode="overlay", yaxis=dict(autorange="reversed"), height=max(350, len(df_trv)*70))
        st.plotly_chart(fig_t, use_container_width=True)

# --- TAB 4: EUROTRIP ---
with tab_eurotrip:
    st.markdown("### 🌍 Dashboard Financeiro: Eurotrip")

    saldo_eurotrip = df_acc_eurotrip["balance"].sum()
    sim_eurotrip = [e for e in st.session_state.extra_expenses if e.get("conta") == "Eurotrip"]
    impacto_simulado = sum(e["amount"] for e in sim_eurotrip) # amount já entra negativo

    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo Atual em Conta", EUR(saldo_eurotrip))
    c2.metric("Gasto Simulado (Pendente)", EUR(abs(impacto_simulado)))
    c3.metric("Saldo Pós-Simulação", EUR(saldo_eurotrip + impacto_simulado))

    st.markdown("**Saldos em Moeda (Contas Eurotrip)**")
    st.dataframe(df_acc_eurotrip[["account", "balance", "currency"]], hide_index=True, use_container_width=True)

# --- TAB 5: CONTAS ---
with tab_accounts:
    st.subheader("Visão Geral de Todas as Contas")
    if not df_acc.empty:
        fig_a = go.Figure(go.Bar(x=df_acc["account"], y=df_acc["balance"], text=[EUR(b) for b in df_acc["balance"]], textposition="outside", marker_color="#f5a623"))
        fig_a.update_layout(**PLOTLY_LAYOUT, height=450)
        st.plotly_chart(fig_a, use_container_width=True)

# --- TAB 6: BASE ---
with tab_db:
    st.subheader("Histórico de Transações")
    st.dataframe(
        df_tx[["date", "description", "amount", "type", "context"]].sort_values("date", ascending=False),
        hide_index=True, use_container_width=True, height=600
    )
