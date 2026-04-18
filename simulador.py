import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Configuração da página para ficar com visual de painel
st.set_page_config(page_title="Simulador de Compras", page_icon="🛍️", layout="centered")

st.title("🛍️ À Vista ou Parcelado?")
st.markdown("Descubra a decisão matematicamente mais inteligente para o seu bolso.")
st.divider()

# --- BARRA LATERAL: INPUTS DO USUÁRIO ---
with st.sidebar:
    st.header("Parâmetros da Compra")

    valor_produto = st.number_input("Valor do Produto (R$)", min_value=100.0, value=2000.0, step=100.0)
    desconto_perc = st.slider("Desconto à Vista (%)", min_value=0.0, max_value=30.0, value=10.0, step=0.5)
    parcelas = st.slider("Número de Parcelas (Sem Juros)", min_value=2, max_value=24, value=12)
    taxa_mensal = st.slider("Rendimento do Investimento (% ao mês)", min_value=0.1, max_value=2.0, value=0.8, step=0.1)

    st.info("💡 **Regra de Ouro:** Assumimos que você já tem o dinheiro total em mãos hoje.")

# --- LÓGICA FINANCEIRA ---
taxa = taxa_mensal / 100
desconto_reais = valor_produto * (desconto_perc / 100)
valor_parcela = valor_produto / parcelas

meses = list(range(parcelas + 1))
saldo_a_vista = []
saldo_parcelado = []

saldo_atual_a_vista = desconto_reais
saldo_atual_parcelado = valor_produto

for mes in meses:
    # Cenário A: Dinheiro do desconto rendendo
    saldo_a_vista.append(saldo_atual_a_vista)
    saldo_atual_a_vista *= (1 + taxa)

    # Cenário B: Dinheiro total rendendo, subtraindo a parcela todo mês
    saldo_parcelado.append(saldo_atual_parcelado)
    if mes < parcelas: # Só desconta a parcela até quitar
        saldo_atual_parcelado = (saldo_atual_parcelado * (1 + taxa)) - valor_parcela

# Valores finais no último mês
resultado_a_vista = saldo_a_vista[-1]
resultado_parcelado = saldo_parcelado[-1]

# --- UI: RESULTADOS (SUPER BONITO) ---
if resultado_a_vista > resultado_parcelado:
    vencedor = "Pagar à Vista!"
    cor_vencedor = "#22c55e" # Verde
    motivo = f"O desconto superou o rendimento. Você termina com **R$ {resultado_a_vista - resultado_parcelado:.2f}** a mais no bolso."
else:
    vencedor = "Pagar Parcelado!"
    cor_vencedor = "#3ecfcf" # Azul claro
    motivo = f"O dinheiro rendendo rendeu mais que o desconto. Você termina com **R$ {resultado_parcelado - resultado_a_vista:.2f}** a mais no bolso."

st.markdown(f"<h3 style='text-align: center; color: {cor_vencedor};'>🏆 Melhor Opção: {vencedor}</h3>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: #888;'>{motivo}</p>", unsafe_allow_html=True)
st.write("")

# Cards de Métrica
col1, col2 = st.columns(2)
with col1:
    st.metric(label="Saldo Final (Se Pagar à Vista)", value=f"R$ {resultado_a_vista:,.2f}",
              help="Esse é o valor do desconto rendendo juros até o fim das parcelas.")
with col2:
    st.metric(label="Saldo Final (Se Parcelar)", value=f"R$ {resultado_parcelado:,.2f}",
              help="Esse é o que sobra na sua conta após o dinheiro render e você pagar todas as parcelas.")

st.divider()

# --- UI: GRÁFICO INTERATIVO ---
st.subheader("📊 Evolução do seu Dinheiro")

fig = go.Figure()

# Linha do cenário À Vista
fig.add_trace(go.Scatter(
    x=meses, y=saldo_a_vista,
    mode='lines+markers',
    name='Cenário: À Vista',
    line=dict(color='#22c55e', width=3),
    hovertemplate="Mês %{x}<br>Saldo: R$ %{y:,.2f}<extra></extra>"
))

# Linha do cenário Parcelado
fig.add_trace(go.Scatter(
    x=meses, y=saldo_parcelado,
    mode='lines+markers',
    name='Cenário: Parcelado',
    line=dict(color='#3ecfcf', width=3),
    hovertemplate="Mês %{x}<br>Saldo: R$ %{y:,.2f}<extra></extra>"
))

fig.update_layout(
    xaxis_title="Meses (Tempo da Dívida)",
    yaxis_title="Dinheiro Restante (R$)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=30, b=0),
    height=400
)

st.plotly_chart(fig, use_container_width=True)