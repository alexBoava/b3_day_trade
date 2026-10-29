import datetime
import os
import streamlit as st
import pandas as pd
import numpy as np

# Configuração da Página
st.set_page_config(
    page_title="B3 Swing Trade Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

from database.connection import check_db_connection, DATABASE_TYPE
from src.data_collector import (
    get_active_tickers, add_ticker, remove_ticker,
    sync_all_tickers, sync_ticker_data, load_candles_from_db,
    get_or_sync_ticker_candles, get_database_stats,
    save_candles_to_db, ensure_initial_tickers
)
from database.models import SwingSignal
from database.connection import get_db_session
from src.indicators import calculate_all_indicators
from src.strategies import analyze_swing_trade_signals
from src.chart_builder import build_swing_chart
from src.risk_manager import calculate_position_size

# Inicialização do banco e tickers padrão
ensure_initial_tickers()

# Sidebar
st.sidebar.title("📈 B3 Swing Trade")
st.sidebar.caption("Monitor & Rastreador Técnico com Banco de Dados")

# Indicador de Banco de Dados
db_ok, db_info = check_db_connection()
if db_ok:
    if "Postgres" in db_info:
        st.sidebar.success(f"🐘 Banco: {db_info} (Docker)")
    else:
        st.sidebar.info(f"💾 Banco: {db_info}")
else:
    st.sidebar.warning(f"⚠️ Banco: {db_info}")

# Métricas de Persistência no Banco
db_stats = get_database_stats()
s_col1, s_col2 = st.sidebar.columns(2)
s_col1.metric("Candles no Banco", f"{db_stats['total_candles']:,}")
s_col2.metric("Ativos Ativos", db_stats['total_tickers'])

if db_stats['latest_candle_date']:
    st.sidebar.caption(f"📅 Último candle gravado: **{db_stats['latest_candle_date'].strftime('%d/%m/%Y')}**")
else:
    st.sidebar.caption("⚠️ Nenhum candle gravado ainda.")

st.sidebar.markdown("---")

# Menu de Navegação
menu_options = [
    "🎯 Radar de Oportunidades",
    "📈 Análise Gráfica & Técnica",
    "🧮 Calculadora de Risco",
    "📋 Histórico de Sinais",
    "⚙️ Gerenciar Carteira (Ativos)"
]
selected_menu = st.sidebar.radio("Navegação:", menu_options)

st.sidebar.markdown("---")

# Opções de Sincronização
st.sidebar.markdown("### 🔄 Sincronização Inteligente")
st.sidebar.caption("O sistema usa **Cache Local**. Só baixa da B3 o que estiver desatualizado.")
force_download = st.sidebar.checkbox("Forçar download completo (1 ano)", value=False)

if st.sidebar.button("🚀 Sincronizar Mercado Agora", use_container_width=True):
    progress_bar = st.sidebar.progress(0.0)
    status_text = st.sidebar.empty()

    def update_progress(pct, text):
        progress_bar.progress(pct)
        status_text.caption(text)

    with st.spinner("Verificando banco de dados e sincronizando se necessário..."):
        results = sync_all_tickers(force_download=force_download, progress_callback=update_progress)
        st.session_state["market_data"] = results
        st.session_state["last_sync"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    progress_bar.empty()
    status_text.empty()
    st.sidebar.success("Sincronização concluída com sucesso!")

if "last_sync" in st.session_state:
    st.sidebar.caption(f"Última verificação: {st.session_state['last_sync']}")

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Persistência Garantida:**\n"
    "Os dados dos candles ficam armazenados de forma permanente no banco de dados, evitando downloads repetidos e acelerando a análise."
)

# -----------------------------------------------------------------------------
# FUNÇÃO AUXILIAR: Obter ou carregar dados de mercado
# -----------------------------------------------------------------------------
def get_market_analysis(force: bool = False):
    if "market_data" not in st.session_state or not st.session_state["market_data"] or force:
        with st.spinner("Carregando análise (priorizando cache do banco)..."):
            st.session_state["market_data"] = sync_all_tickers(force_download=force)
            st.session_state["last_sync"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return st.session_state["market_data"]


# -----------------------------------------------------------------------------
# ABA 1: RADAR DE OPORTUNIDADES (SCREENER)
# -----------------------------------------------------------------------------
if selected_menu == "🎯 Radar de Oportunidades":
    st.title("🎯 Radar de Oportunidades - Swing Trade B3")
    st.markdown("Identificação automática de ações com setups técnicos em gráficos diários, com persistência em banco.")

    market_data = get_market_analysis()

    if not market_data:
        st.warning("Nenhum dado encontrado no banco. Clique no botão '🚀 Sincronizar Mercado Agora' na barra lateral.")
    else:
        df_screener = pd.DataFrame(market_data)

        # Contadores de métricas
        total_ativos = len(df_screener)
        compras_fortes = len(df_screener[df_screener['signal'] == 'COMPRA FORTE'])
        compras = len(df_screener[df_screener['signal'] == 'COMPRA'])
        em_alta = len(df_screener[df_screener['trend'].isin(['Alta', 'Forte Alta'])])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Ativos Monitorados", total_ativos)
        col2.metric("Sinais Compra Forte", compras_fortes, delta=f"{compras_fortes} ativos" if compras_fortes else None)
        col3.metric("Oportunidades de Compra", compras, delta=f"{compras} ativos" if compras else None)
        col4.metric("Em Tendência de Alta", f"{em_alta}/{total_ativos}", delta=f"{(em_alta/total_ativos)*100:.0f}%")

        st.markdown("### Filtros de Busca")
        fcol1, fcol2, fcol3 = st.columns(3)

        with fcol1:
            filtro_sinal = st.multiselect(
                "Filtrar por Sinal:",
                options=["COMPRA FORTE", "COMPRA", "ATENÇÃO (Aguardando Gatilho)", "NEUTRO", "ALERTA (Sobrecomprado)"],
                default=["COMPRA FORTE", "COMPRA", "ATENÇÃO (Aguardando Gatilho)"]
            )
        with fcol2:
            setores_disponiveis = sorted(list(df_screener['sector'].dropna().unique()))
            filtro_setor = st.multiselect("Filtrar por Setor:", options=setores_disponiveis, default=[])

        with fcol3:
            rsi_max = st.slider("IFR (14) Máximo:", min_value=10, max_value=90, value=65)

        # Aplicar Filtros
        df_filtered = df_screener.copy()
        if filtro_sinal:
            df_filtered = df_filtered[df_filtered['signal'].isin(filtro_sinal)]
        if filtro_setor:
            df_filtered = df_filtered[df_filtered['sector'].isin(filtro_setor)]
        df_filtered = df_filtered[df_filtered['rsi'] <= rsi_max]

        # Ordenar por prioridade (Comprar Forte primeiro, depois Compra, etc.)
        df_filtered = df_filtered.sort_values(by=["priority", "risk_reward"], ascending=[False, False])

        st.markdown(f"#### Resultados Encontrados: **{len(df_filtered)} ativos**")

        # Formatação para a visualização
        display_cols = [
            "ticker", "name", "sector", "close", "trend", "rsi",
            "signal", "strategy", "entry_price", "stop_loss", "stop_loss_pct",
            "target_1", "target_2", "risk_reward", "data_source"
        ]
        # Garantir que colunas existam
        cols_present = [c for c in display_cols if c in df_filtered.columns]

        col_rename = {
            "ticker": "Ticker",
            "name": "Empresa",
            "sector": "Setor",
            "close": "Preço (R$)",
            "trend": "Tendência",
            "rsi": "IFR (14)",
            "signal": "Sinal Técnico",
            "strategy": "Estratégia",
            "entry_price": "Entrada (R$)",
            "stop_loss": "Stop (R$)",
            "stop_loss_pct": "Stop (%)",
            "target_1": "Alvo 1 (R$)",
            "target_2": "Alvo 2 (R$)",
            "risk_reward": "Risco/Retorno",
            "data_source": "Origem dos Dados"
        }

        df_display = df_filtered[cols_present].rename(columns=col_rename)

        def color_signals(val):
            if "COMPRA FORTE" in str(val):
                return "background-color: #00E676; color: black; font-weight: bold;"
            elif "COMPRA" in str(val):
                return "background-color: #69F0AE; color: black; font-weight: bold;"
            elif "ATENÇÃO" in str(val):
                return "background-color: #FFE57F; color: black;"
            elif "ALERTA" in str(val):
                return "background-color: #FF8A80; color: black;"
            return ""

        styled_df = df_display.style.applymap(color_signals, subset=["Sinal Técnico"])
        st.dataframe(styled_df, use_container_width=True, height=450)

        # Destaques de Compra
        compras_df = df_filtered[df_filtered['priority'] >= 2]
        if not compras_df.empty:
            st.markdown("### 🌟 Destaques de Compra para Análise")
            for _, item in compras_df.iterrows():
                with st.expander(f"🟢 **{item['ticker']} - {item['name']}** | {item['strategy']} (Preço: R$ {item['close']:.2f})"):
                    c_col1, c_col2, c_col3 = st.columns([1, 1, 2])
                    with c_col1:
                        st.write(f"**Entrada:** R$ {item['entry_price']:.2f}")
                        st.write(f"**Stop Loss:** R$ {item['stop_loss']:.2f} (`{item['stop_loss_pct']:.1f}%`)")
                    with c_col2:
                        st.write(f"**Alvo 1 (Parcial):** R$ {item['target_1']:.2f} (`+{item['target_1_pct']:.1f}%`)")
                        st.write(f"**Alvo 2 (Final):** R$ {item['target_2']:.2f} (`+{item['target_2_pct']:.1f}%`)")
                        st.write(f"**Relação R:R:** 1:{item['risk_reward']}")
                    with c_col3:
                        st.info(f"**Racional Técnico:** {item['reason']}")

# -----------------------------------------------------------------------------
# ABA 2: ANÁLISE GRÁFICA & TÉCNICA DETALHADA
# -----------------------------------------------------------------------------
elif selected_menu == "📈 Análise Gráfica & Técnica":
    st.title("📈 Análise Gráfica & Técnica Detalhada")

    tickers_list = get_active_tickers()
    symbols = [t["symbol"] for t in tickers_list]

    col_sel1, col_sel2, col_sel3 = st.columns([2, 1, 1])
    with col_sel1:
        ticker_escolhido = st.selectbox("Selecione um ativo para analisar no gráfico:", symbols, index=0)
    with col_sel2:
        periodo_escolhido = st.selectbox("Período de Candles:", ["6 meses", "1 ano", "2 anos"], index=1)
        limit_map = {"6 meses": 130, "1 ano": 252, "2 anos": 504}
        candle_limit = limit_map[periodo_escolhido]
    with col_sel3:
        st.write("")
        st.write("")
        btn_refresh_ticker = st.button("🔄 Atualizar Ativo na B3", use_container_width=True)

    # Obter dados do ativo usando Cache Inteligente do Banco
    with st.spinner(f"Carregando candles de {ticker_escolhido} (banco de dados)..."):
        df_candles, origem_dados = get_or_sync_ticker_candles(
            ticker_escolhido,
            force_download=btn_refresh_ticker,
            min_candles=candle_limit
        )

        if not df_candles.empty:
            df_with_ind = calculate_all_indicators(df_candles)
            signal_data = analyze_swing_trade_signals(df_with_ind, ticker_escolhido)
        else:
            df_with_ind = pd.DataFrame()
            signal_data = None

    if df_with_ind.empty:
        st.error(f"Não foi possível carregar os dados de {ticker_escolhido}. Clique em 'Atualizar Ativo na B3'.")
    else:
        # Indicador de Origem
        badge_cor = "green" if "banco" in origem_dados else "blue"
        st.caption(f"📦 Fonte: **:{badge_cor}[{origem_dados.upper()}]** | Candles carregados: **{len(df_with_ind)}** | Último pregão: **{df_with_ind.index[-1].strftime('%d/%m/%Y')}**")

        # Cartão de Status do Ativo
        st.markdown("### Painel Operacional")
        mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)

        preco_atual = float(df_with_ind['Close'].iloc[-1])
        preco_anterior = float(df_with_ind['Close'].iloc[-2]) if len(df_with_ind) >= 2 else preco_atual
        var_dia = ((preco_atual - preco_anterior) / preco_anterior) * 100.0 if preco_anterior > 0 else 0.0

        mcol1.metric("Preço Atual", f"R$ {preco_atual:.2f}", f"{var_dia:+.2f}%")
        mcol2.metric("Tendência", signal_data['trend'] if signal_data else "N/A")
        mcol3.metric("IFR (14)", f"{signal_data['rsi']:.1f}" if signal_data else "N/A")
        mcol4.metric("Sinal Técnico", signal_data['signal'] if signal_data else "N/A")
        mcol5.metric("Risco / Retorno", f"1:{signal_data['risk_reward']}" if signal_data else "N/A")

        if signal_data and signal_data.get("reason"):
            if signal_data['priority'] >= 2:
                st.success(f"🎯 **Setup Detectado:** {signal_data['strategy']}\n\n**Racional:** {signal_data['reason']}")
            elif signal_data['priority'] == 1:
                st.warning(f"👀 **Observação:** {signal_data['strategy']}\n\n**Racional:** {signal_data['reason']}")
            else:
                st.info(f"⚪ **Status:** {signal_data['strategy']}\n\n{signal_data['reason']}")

        # Opções de visualização do gráfico
        with st.expander("🛠️ Personalizar Indicadores no Gráfico", expanded=False):
            gcol1, gcol2, gcol3, gcol4 = st.columns(4)
            with gcol1:
                show_ema9 = st.checkbox("EMA 9 (Amarela)", value=True)
                show_ema20 = st.checkbox("EMA 20 (Azul)", value=True)
            with gcol2:
                show_ema50 = st.checkbox("EMA 50 (Laranja)", value=True)
                show_ema200 = st.checkbox("EMA 200 (Roxa)", value=True)
            with gcol3:
                show_bb = st.checkbox("Bandas de Bollinger", value=True)
            with gcol4:
                show_macd = st.checkbox("Painel MACD", value=True)

        # Gráfico Plotly
        fig = build_swing_chart(
            df_with_ind.tail(candle_limit),
            ticker=ticker_escolhido,
            signal_info=signal_data,
            show_ema9=show_ema9,
            show_ema20=show_ema20,
            show_ema50=show_ema50,
            show_ema200=show_ema200,
            show_bb=show_bb,
            show_macd=show_macd
        )
        st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# ABA 3: CALCULADORA DE RISCO & POSIÇÃO
# -----------------------------------------------------------------------------
elif selected_menu == "🧮 Calculadora de Risco":
    st.title("🧮 Calculadora de Dimensionamento de Posição & Risco")
    st.markdown("Calcule o número exato de ações para operar sem arriscar além do planejado.")

    tickers_list = get_active_tickers()
    symbols = [t["symbol"] for t in tickers_list]

    calc_col1, calc_col2 = st.columns([1, 1])

    with calc_col1:
        st.subheader("Parâmetros da Conta & Ativo")
        capital_total = st.number_input("Capital Total da Conta (R$):", min_value=1000.0, value=30000.0, step=1000.0)
        risco_pct = st.slider("Risco Máximo Tolerado na Operação (% do Capital):", min_value=0.5, max_value=5.0, value=1.5, step=0.1)

        st.markdown("---")
        preencher_auto = st.checkbox("Preencher dados automaticamente a partir de um ativo", value=True)

        preco_entrada_def = 30.00
        preco_stop_def = 28.50
        alvo_1_def = 32.25
        alvo_2_def = 33.75

        if preencher_auto:
            ativo_calc = st.selectbox("Ativo:", symbols, index=0)
            df_c, _ = get_or_sync_ticker_candles(ativo_calc, force_download=False)
            if not df_c.empty:
                df_c_ind = calculate_all_indicators(df_c)
                sig = analyze_swing_trade_signals(df_c_ind, ativo_calc)
                if sig:
                    preco_entrada_def = float(sig['entry_price'])
                    preco_stop_def = float(sig['stop_loss'])
                    alvo_1_def = float(sig['target_1'])
                    alvo_2_def = float(sig['target_2'])

        preco_entrada = st.number_input("Preço de Entrada (R$):", min_value=0.1, value=preco_entrada_def, step=0.10)
        preco_stop = st.number_input("Preço de Stop Loss (R$):", min_value=0.1, value=preco_stop_def, step=0.10)
        alvo_1 = st.number_input("Preço Alvo 1 (R$):", min_value=0.1, value=alvo_1_def, step=0.10)
        alvo_2 = st.number_input("Preço Alvo 2 (R$):", min_value=0.1, value=alvo_2_def, step=0.10)
        lote_padrao = st.checkbox("Arredondar para Lote Padrão de 100 ações", value=False)

    with calc_col2:
        st.subheader("Resultado do Dimensionamento")
        resultado_risco = calculate_position_size(
            capital_total=capital_total,
            risco_por_operacao_pct=risco_pct,
            preco_entrada=preco_entrada,
            preco_stop=preco_stop,
            alvo_1=alvo_1,
            alvo_2=alvo_2,
            lote_padrao=lote_padrao
        )

        if "error" in resultado_risco:
            st.error(resultado_risco["error"])
        else:
            qtd = resultado_risco["qtd_acoes"]
            st.success(f"### Quantidade a Comprar: **{qtd} ações**")

            rcol1, rcol2 = st.columns(2)
            rcol1.metric("Capital a Alocar", f"R$ {resultado_risco['capital_alocado']:,.2f}")
            rcol2.metric("% da Carteira Comprometido", f"{resultado_risco['pct_capital_alocado']:.1f}%")

            st.markdown("#### Simulação de Resultados")
            scol1, scol2, scol3 = st.columns(3)

            scol1.metric(
                "Perda Máxima no Stop",
                f"-R$ {resultado_risco['perda_maxima_real_rs']:,.2f}",
                f"{((preco_stop - preco_entrada)/preco_entrada)*100:.1f}%",
                delta_color="inverse"
            )
            scol2.metric(
                "Lucro no Alvo 1",
                f"+R$ {resultado_risco['lucro_alvo_1_rs']:,.2f}",
                f"{resultado_risco['retorno_alvo_1_pct']:.1f}%"
            )
            scol3.metric(
                "Lucro no Alvo 2",
                f"+R$ {resultado_risco['lucro_alvo_2_rs']:,.2f}",
                f"{resultado_risco['retorno_alvo_2_pct']:.1f}%"
            )

            st.info(
                f"**Relação Risco : Retorno:** 1 : {resultado_risco['risco_retorno_ratio']}\n\n"
                f"Para cada R$ 1,00 arriscado nesta operação, você busca ganhar R$ {resultado_risco['risco_retorno_ratio']:.2f} no Alvo 2."
            )

# -----------------------------------------------------------------------------
# ABA 4: HISTÓRICO DE SINAIS
# -----------------------------------------------------------------------------
elif selected_menu == "📋 Histórico de Sinais":
    st.title("📋 Histórico de Sinais Gerados")
    st.markdown("Registro contínuo dos sinais técnicos identificados e armazenados no banco de dados.")

    with get_db_session() as session:
        signals = session.query(SwingSignal).order_by(SwingSignal.date.desc(), SwingSignal.id.desc()).limit(200).all()

        if not signals:
            st.info("Nenhum sinal salvo no histórico ainda. Execute uma sincronização no menu lateral.")
        else:
            data = [{
                "Data": s.date,
                "Ticker": s.ticker_symbol,
                "Sinal": s.signal_type,
                "Estratégia": s.strategy,
                "Entrada (R$)": s.entry_price,
                "Stop (R$)": s.stop_loss,
                "Alvo 1 (R$)": s.target_1,
                "Alvo 2 (R$)": s.target_2,
                "R:R": s.risk_reward,
                "Status": s.status,
                "Detalhes": s.details
            } for s in signals]

            df_hist = pd.DataFrame(data)
            st.dataframe(df_hist, use_container_width=True)

# -----------------------------------------------------------------------------
# ABA 5: GERENCIAR CARTEIRA (ATIVOS)
# -----------------------------------------------------------------------------
elif selected_menu == "⚙️ Gerenciar Carteira (Ativos)":
    st.title("⚙️ Gerenciamento de Ativos Monitorados")
    st.markdown("Adicione, desative ou remova ações da B3 monitoradas pelo sistema.")

    col_add, col_list = st.columns([1, 2])

    with col_add:
        st.subheader("Adicionar Nova Ação")
        novo_ticker = st.text_input("Código do Ticker (ex: BBSE3, VAMO3):").strip().upper()
        nome_empresa = st.text_input("Nome da Empresa (opcional):").strip()
        setor_empresa = st.text_input("Setor (opcional):").strip()

        if st.button("➕ Adicionar Ativo", use_container_width=True):
            if novo_ticker:
                symbol = novo_ticker if novo_ticker.endswith(".SA") else f"{novo_ticker}.SA"
                # Testar se yfinance reconhece
                with st.spinner(f"Verificando {symbol} na B3..."):
                    df_check, _ = get_or_sync_ticker_candles(symbol, force_download=True, min_candles=50)
                    if df_check.empty:
                        st.error(f"Não foi possível encontrar dados para {symbol} na B3. Verifique o código.")
                    else:
                        add_ticker(symbol, name=nome_empresa, sector=setor_empresa)
                        st.success(f"Ativo {symbol} adicionado com sucesso e histórico gravado no banco!")
                        st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()
            else:
                st.warning("Informe o código da ação.")

    with col_list:
        st.subheader("Ativos Atualmente Monitorados")
        tickers_cadastrados = get_active_tickers()
        df_tickers = pd.DataFrame(tickers_cadastrados)

        st.dataframe(df_tickers, use_container_width=True, height=350)

        st.markdown("#### Desativar Ativo")
        symbols_cad = [t["symbol"] for t in tickers_cadastrados]
        ticker_del = st.selectbox("Escolha um ticker para remover do monitoramento:", symbols_cad)
        if st.button("🗑️ Remover Ativo", type="secondary"):
            if remove_ticker(ticker_del):
                st.success(f"{ticker_del} removido do monitoramento.")
                st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()
