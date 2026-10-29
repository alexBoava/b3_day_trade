from typing import Dict, Any, Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def build_swing_chart(
    df: pd.DataFrame,
    ticker: str,
    signal_info: Optional[Dict[str, Any]] = None,
    show_ema9: bool = True,
    show_ema20: bool = True,
    show_ema50: bool = True,
    show_ema200: bool = True,
    show_bb: bool = True,
    show_macd: bool = True
) -> go.Figure:
    """
    Constrói um gráfico técnico completo e interativo com Candlesticks,
    Médias Móveis, Bandas de Bollinger, Volume, IFR (RSI) e MACD,
    além de projetar Entrada, Stop Loss e Alvos no gráfico.
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados disponíveis para exibição.", showarrow=False, font=dict(size=16))
        return fig

    # Definir subplots: 1: Preço e Médias, 2: Volume, 3: IFR, 4: MACD
    row_heights = [0.55, 0.15, 0.15, 0.15] if show_macd else [0.60, 0.20, 0.20]
    rows = 4 if show_macd else 3

    subplot_titles = [f"Preço Diário - {ticker}", "Volume", "IFR (14)"]
    if show_macd:
        subplot_titles.append("MACD (12, 26, 9)")

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=subplot_titles,
        row_heights=row_heights
    )

    # Cores dos candles
    colors_up = '#26A69A'
    colors_down = '#EF5350'

    # 1. Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name="Candles",
            increasing_line_color=colors_up,
            decreasing_line_color=colors_down,
            increasing_fillcolor=colors_up,
            decreasing_fillcolor=colors_down
        ),
        row=1, col=1
    )

    # Bandas de Bollinger
    if show_bb and 'BB_Upper' in df.columns and 'BB_Lower' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['BB_Upper'],
                mode='lines', line=dict(color='rgba(150, 150, 200, 0.4)', width=1, dash='dot'),
                name="BB Superior", showlegend=False
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['BB_Lower'],
                mode='lines', line=dict(color='rgba(150, 150, 200, 0.4)', width=1, dash='dot'),
                fill='tonexty', fillcolor='rgba(100, 100, 180, 0.05)',
                name="Bandas Bollinger", showlegend=True
            ),
            row=1, col=1
        )

    # Médias Móveis
    if show_ema9 and 'EMA9' in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df['EMA9'], mode='lines', line=dict(color='#FFD54F', width=1.5), name="EMA 9 (Rápida)"),
            row=1, col=1
        )
    if show_ema20 and 'EMA20' in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df['EMA20'], mode='lines', line=dict(color='#29B6F6', width=1.8), name="EMA 20 (Curto Prazo)"),
            row=1, col=1
        )
    if show_ema50 and 'EMA50' in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df['EMA50'], mode='lines', line=dict(color='#FFA726', width=2), name="EMA 50 (Médio Prazo)"),
            row=1, col=1
        )
    if show_ema200 and 'EMA200' in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df['EMA200'], mode='lines', line=dict(color='#AB47BC', width=2.2), name="EMA 200 (Longo Prazo)"),
            row=1, col=1
        )

    # Projeção de Gatilho / Níveis de Swing Trade (Entrada, Stop Loss, Alvo 1, Alvo 2)
    if signal_info and signal_info.get("entry_price"):
        entrada = signal_info["entry_price"]
        stop = signal_info["stop_loss"]
        alvo1 = signal_info["target_1"]
        alvo2 = signal_info["target_2"]

        # Linha Entrada
        fig.add_hline(
            y=entrada, line_dash="dash", line_color="#42A5F5", line_width=1.5,
            annotation_text=f"Entrada: R$ {entrada:.2f}",
            annotation_position="top right",
            annotation_font=dict(color="#42A5F5", size=11),
            row=1, col=1
        )
        # Linha Stop Loss
        fig.add_hline(
            y=stop, line_dash="dash", line_color="#FF1744", line_width=1.8,
            annotation_text=f"Stop: R$ {stop:.2f} ({signal_info.get('stop_loss_pct', 0):.1f}%)",
            annotation_position="bottom right",
            annotation_font=dict(color="#FF1744", size=11),
            row=1, col=1
        )
        # Linha Alvo 1
        fig.add_hline(
            y=alvo1, line_dash="dot", line_color="#00E676", line_width=1.5,
            annotation_text=f"Alvo 1: R$ {alvo1:.2f} ({signal_info.get('target_1_pct', 0):.1f}%)",
            annotation_position="top right",
            annotation_font=dict(color="#00E676", size=11),
            row=1, col=1
        )
        # Linha Alvo 2
        fig.add_hline(
            y=alvo2, line_dash="dot", line_color="#00C853", line_width=1.8,
            annotation_text=f"Alvo 2: R$ {alvo2:.2f} ({signal_info.get('target_2_pct', 0):.1f}%)",
            annotation_position="top right",
            annotation_font=dict(color="#00C853", size=11),
            row=1, col=1
        )

    # 2. Volume
    vol_colors = [colors_up if c >= o else colors_down for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(
        go.Bar(
            x=df.index, y=df['Volume'],
            marker_color=vol_colors, name="Volume", showlegend=False
        ),
        row=2, col=1
    )
    if 'Volume_MA20' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['Volume_MA20'],
                mode='lines', line=dict(color='#B0BEC5', width=1.5), name="Vol Médio 20", showlegend=False
            ),
            row=2, col=1
        )

    # 3. IFR (RSI 14)
    if 'RSI' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['RSI'],
                mode='lines', line=dict(color='#FFCA28', width=2), name="IFR (14)", showlegend=False
            ),
            row=3, col=1
        )
        # Linhas de Sobrecompra (70) e Sobrevenda (30)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(239, 83, 80, 0.7)", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(38, 166, 154, 0.7)", row=3, col=1)
        fig.add_hline(y=50, line_dash="dash", line_color="rgba(255, 255, 255, 0.2)", row=3, col=1)

        # Destacar Divergência de Alta no IFR se detectada
        if signal_info and "Divergência" in str(signal_info.get("strategy", "")):
            fig.add_annotation(
                x=df.index[-1],
                y=float(df['RSI'].iloc[-1]),
                text="📈 Divergência de Alta!",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#00E676",
                font=dict(color="#00E676", size=12, family="Arial"),
                bgcolor="rgba(0, 50, 0, 0.7)",
                row=3, col=1
            )

    # 4. MACD
    if show_macd and 'MACD' in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df['MACD'], mode='lines', line=dict(color='#29B6F6', width=1.5), name="MACD", showlegend=False),
            row=4, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df['MACD_Signal'], mode='lines', line=dict(color='#FF7043', width=1.5), name="Sinal", showlegend=False),
            row=4, col=1
        )
        hist_colors = [colors_up if h >= 0 else colors_down for h in df['MACD_Hist']]
        fig.add_trace(
            go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=hist_colors, name="Hist MACD", showlegend=False),
            row=4, col=1
        )

    # Layout Geral
    fig.update_layout(
        template="plotly_dark",
        height=850 if show_macd else 700,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        hovermode="x unified"
    )

    fig.update_yaxes(title_text="R$", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    fig.update_yaxes(title_text="IFR", range=[0, 100], row=3, col=1)
    if show_macd:
        fig.update_yaxes(title_text="MACD", row=4, col=1)

    return fig
