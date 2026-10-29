import datetime
import logging
from typing import List, Optional, Callable, Dict, Any, Tuple
import pandas as pd
import yfinance as yf
from sqlalchemy import func

from database.connection import get_db_session, init_db
from database.models import Ticker, DailyCandle, SwingSignal
from src.default_tickers import DEFAULT_TICKERS
from src.indicators import calculate_all_indicators
from src.strategies import analyze_swing_trade_signals

logger = logging.getLogger(__name__)

# Cache em memória para eventos de calendário (Balanços e Dividendos)
_CALENDAR_CACHE: Dict[str, Tuple[datetime.datetime, Dict[str, Any]]] = {}

def ensure_initial_tickers():
    """Garante que a lista inicial padrão de tickers da B3 esteja cadastrada."""
    init_db()
    with get_db_session() as session:
        count = session.query(Ticker).count()
        if count == 0:
            for item in DEFAULT_TICKERS:
                t = Ticker(
                    symbol=item["symbol"],
                    name=item["name"],
                    sector=item["sector"],
                    is_active=True
                )
                session.add(t)
            session.commit()
            logger.info(f"Cadastrados {len(DEFAULT_TICKERS)} tickers padrão.")

def get_active_tickers() -> List[Dict[str, str]]:
    """Retorna a lista de tickers ativos cadastrados no banco."""
    ensure_initial_tickers()
    with get_db_session() as session:
        tickers = session.query(Ticker).filter(Ticker.is_active == True).all()
        return [{"symbol": t.symbol, "name": t.name or t.symbol, "sector": t.sector or "Geral"} for t in tickers]

def add_ticker(symbol: str, name: str = "", sector: str = "") -> bool:
    """Adiciona um novo ticker ao monitoramento."""
    symbol = symbol.strip().upper()
    if not symbol.endswith(".SA"):
        symbol = f"{symbol}.SA"

    with get_db_session() as session:
        existing = session.query(Ticker).filter(Ticker.symbol == symbol).first()
        if existing:
            existing.is_active = True
            if name:
                existing.name = name
            if sector:
                existing.sector = sector
        else:
            new_ticker = Ticker(symbol=symbol, name=name or symbol, sector=sector or "Outros", is_active=True)
            session.add(new_ticker)
        session.commit()
    return True

def remove_ticker(symbol: str) -> bool:
    """Desativa ou remove um ticker da lista ativa."""
    with get_db_session() as session:
        t = session.query(Ticker).filter(Ticker.symbol == symbol).first()
        if t:
            t.is_active = False
            session.commit()
            return True
    return False

def clean_yfinance_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Trata MultiIndex gerado por versões recentes do yfinance."""
    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if hasattr(df.index, 'tz_localize') and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    elif hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    col_mapping = {col: col.capitalize() for col in df.columns}
    df = df.rename(columns=col_mapping)

    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required:
        if col not in df.columns:
            logger.warning(f"Coluna esperada {col} não encontrada no dataframe do yfinance.")
            return pd.DataFrame()

    return df

def fetch_stock_candles(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Baixa os dados históricos de um ticker via yfinance e retorna DataFrame limpo."""
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        df = clean_yfinance_dataframe(data)
        return df
    except Exception as e:
        logger.error(f"Erro ao baixar dados para {ticker}: {e}")
        return pd.DataFrame()

def fetch_calendar_events(ticker: str) -> Dict[str, Any]:
    """
    Obtém datas de eventos corporativos relevantes (Balanço Trimestral e Data-Ex de Proventos).
    Utiliza cache em memória de 6 horas para evitar requisições redundantes.
    """
    now = datetime.datetime.now()
    if ticker in _CALENDAR_CACHE:
        cached_time, cached_data = _CALENDAR_CACHE[ticker]
        if (now - cached_time).total_seconds() < 21600:
            return cached_data

    info: Dict[str, Any] = {
        "earnings_date": None,
        "days_to_earnings": None,
        "ex_dividend_date": None,
        "days_to_dividend": None
    }
    today = datetime.date.today()

    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if isinstance(cal, dict):
            ed = cal.get('Earnings Date')
            if ed and isinstance(ed, list) and len(ed) > 0:
                first_ed = ed[0]
                if hasattr(first_ed, 'date'):
                    first_ed = first_ed.date()
                if isinstance(first_ed, datetime.date):
                    info["earnings_date"] = first_ed
                    info["days_to_earnings"] = (first_ed - today).days

            ex_div = cal.get('Ex-Dividend Date')
            if ex_div:
                if hasattr(ex_div, 'date'):
                    ex_div = ex_div.date()
                if isinstance(ex_div, datetime.date):
                    info["ex_dividend_date"] = ex_div
                    info["days_to_dividend"] = (ex_div - today).days
    except Exception as e:
        logger.debug(f"Não foi possível obter calendário de {ticker}: {e}")

    _CALENDAR_CACHE[ticker] = (now, info)
    return info

def get_latest_candle_date(ticker: str) -> Optional[datetime.date]:
    """Retorna a data mais recente armazenada no banco para o ticker."""
    with get_db_session() as session:
        latest = session.query(func.max(DailyCandle.date)).filter(DailyCandle.ticker_symbol == ticker).scalar()
        return latest

def get_candle_count(ticker: str) -> int:
    """Retorna a quantidade de candles já salvos no banco para o ticker."""
    with get_db_session() as session:
        count = session.query(func.count(DailyCandle.id)).filter(DailyCandle.ticker_symbol == ticker).scalar()
        return count or 0

def is_trading_day_up_to_date(latest_date: Optional[datetime.date]) -> bool:
    """
    Avalia se o último candle no banco já corresponde ao pregão fechado mais recente da B3.
    """
    if not latest_date:
        return False

    today = datetime.date.today()
    if latest_date >= today:
        return True

    weekday = today.weekday()
    now = datetime.datetime.now()

    if weekday == 5 and latest_date >= (today - datetime.timedelta(days=1)):
        return True
    if weekday == 6 and latest_date >= (today - datetime.timedelta(days=2)):
        return True
    if weekday == 0 and now.hour < 18 and latest_date >= (today - datetime.timedelta(days=3)):
        return True
    if weekday in [1, 2, 3, 4] and now.hour < 18 and latest_date >= (today - datetime.timedelta(days=1)):
        return True

    return False

def save_candles_to_db(ticker: str, df: pd.DataFrame) -> Tuple[int, int]:
    """Salva ou atualiza candles no banco de dados."""
    if df.empty:
        return (0, 0)

    inserted_count = 0
    updated_count = 0
    today = datetime.date.today()
    recent_threshold = today - datetime.timedelta(days=3)

    with get_db_session() as session:
        existing_records = {
            r.date: r for r in session.query(DailyCandle).filter(DailyCandle.ticker_symbol == ticker).all()
        }

        for idx, row in df.iterrows():
            c_date = idx.date() if hasattr(idx, 'date') else idx

            if c_date in existing_records:
                if c_date >= recent_threshold:
                    candle = existing_records[c_date]
                    candle.open = float(row['Open'])
                    candle.high = float(row['High'])
                    candle.low = float(row['Low'])
                    candle.close = float(row['Close'])
                    candle.adj_close = float(row.get('Adj close', row['Close']))
                    candle.volume = int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    updated_count += 1
            else:
                try:
                    candle = DailyCandle(
                        ticker_symbol=ticker,
                        date=c_date,
                        open=float(row['Open']),
                        high=float(row['High']),
                        low=float(row['Low']),
                        close=float(row['Close']),
                        adj_close=float(row.get('Adj close', row['Close'])),
                        volume=int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    )
                    session.add(candle)
                    existing_records[c_date] = candle
                    inserted_count += 1
                except Exception as e:
                    logger.debug(f"Erro ao inserir candle de {ticker} em {c_date}: {e}")

        session.commit()

    return (inserted_count, updated_count)

def load_candles_from_db(ticker: str, limit: int = 300) -> pd.DataFrame:
    """Carrega os últimos candles salvos no banco de dados para um ticker."""
    with get_db_session() as session:
        records = (
            session.query(DailyCandle)
            .filter(DailyCandle.ticker_symbol == ticker)
            .order_by(DailyCandle.date.desc())
            .limit(limit)
            .all()
        )

        if not records:
            return pd.DataFrame()

        records.reverse()
        data = [{
            "Date": r.date,
            "Open": r.open,
            "High": r.high,
            "Low": r.low,
            "Close": r.close,
            "Adj Close": r.adj_close or r.close,
            "Volume": r.volume or 0
        } for r in records]

        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return df

def get_or_sync_ticker_candles(ticker: str, force_download: bool = False, min_candles: int = 120) -> Tuple[pd.DataFrame, str]:
    """Cache-First Inteligente com busca incremental."""
    count = get_candle_count(ticker)
    latest_date = get_latest_candle_date(ticker)
    today = datetime.date.today()

    if not force_download and count >= min_candles and is_trading_day_up_to_date(latest_date):
        df_cached = load_candles_from_db(ticker, limit=min_candles * 2)
        if not df_cached.empty and len(df_cached) >= 20:
            return df_cached, "banco (cache local atualizado)"

    if not force_download and count >= min_candles and latest_date:
        days_gap = (today - latest_date).days
        if days_gap <= 20:
            delta_df = fetch_stock_candles(ticker, period="1mo", interval="1d")
            if not delta_df.empty:
                save_candles_to_db(ticker, delta_df)
                df_updated = load_candles_from_db(ticker, limit=min_candles * 2)
                return df_updated, "banco (após sincronização incremental)"

    fresh_df = fetch_stock_candles(ticker, period="1y", interval="1d")
    if not fresh_df.empty:
        save_candles_to_db(ticker, fresh_df)
        df_full = load_candles_from_db(ticker, limit=300)
        return df_full, "yfinance (download inicial gravado no banco)"

    df_fallback = load_candles_from_db(ticker, limit=300)
    return df_fallback, "banco (offline / fallback)"

def get_market_regime() -> Dict[str, Any]:
    """
    Avalia a saúde geral do mercado brasileiro via BOVA11 / Ibovespa.
    Classifica o regime em Favorável, Cautela ou Defensivo.
    """
    bova_df, _ = get_or_sync_ticker_candles("BOVA11.SA", min_candles=100)
    if bova_df.empty or len(bova_df) < 25:
        return {
            "status": "Indefinido",
            "badge": "⚪ Mercado Neutro",
            "color": "gray",
            "detail": "Sem dados suficientes do Ibovespa/BOVA11.",
            "bova_close": 0.0,
            "bova_var": 0.0
        }

    bova_ind = calculate_all_indicators(bova_df)
    last = bova_ind.iloc[-1]
    c = float(last['Close'])
    ema20 = float(last['EMA20'])
    ema50 = float(last['EMA50'])

    prev_c = float(bova_ind['Close'].iloc[-2]) if len(bova_ind) >= 2 else c
    var_dia = ((c - prev_c) / prev_c) * 100.0 if prev_c > 0 else 0.0

    if c > ema20 > ema50:
        return {
            "status": "Favorável",
            "badge": "🟢 Mercado Favorável (Tendência de Alta)",
            "color": "green",
            "bova_close": c,
            "bova_var": var_dia,
            "detail": "Ibov operando acima das médias EMA 20 e 50. Cenário ideal para swing trade."
        }
    elif c > ema50:
        return {
            "status": "Cautela",
            "badge": "🟡 Mercado em Correção (Cautela)",
            "color": "orange",
            "bova_close": c,
            "bova_var": var_dia,
            "detail": "Ibov acima da EMA 50, mas abaixo da EMA 20. Opere com lote reduzido."
        }
    else:
        return {
            "status": "Defensivo",
            "badge": "🔴 Mercado Defensivo (Abaixo da EMA 50)",
            "color": "red",
            "bova_close": c,
            "bova_var": var_dia,
            "detail": "Ibov em tendência de baixa. Priorizar caixa e compras de reversão estrita."
        }

def sync_ticker_data(
    ticker: str,
    force_download: bool = False,
    df_benchmark: Optional[pd.DataFrame] = None
) -> Optional[Dict[str, Any]]:
    """
    Sincroniza os dados de um ticker utilizando cache em banco,
    compara força relativa contra o Ibov e consulta eventos corporativos.
    """
    df, origem = get_or_sync_ticker_candles(ticker, force_download=force_download)

    if df.empty or len(df) < 20:
        return None

    # Se benchmark não foi passado e não for o próprio BOVA11, carrega do banco
    if df_benchmark is None and ticker != "BOVA11.SA":
        df_benchmark, _ = get_or_sync_ticker_candles("BOVA11.SA", min_candles=100)

    # Eventos de calendário (Balanço Trimestral e Proventos)
    cal_info = fetch_calendar_events(ticker)

    # Adiciona indicadores
    df_with_ind = calculate_all_indicators(df)
    signal = analyze_swing_trade_signals(
        df_with_ind,
        ticker,
        df_benchmark=df_benchmark,
        calendar_info=cal_info
    )

    if signal:
        signal["data_source"] = origem
        if signal["signal"] in ["COMPRA FORTE", "COMPRA", "ATENÇÃO (Aguardando Gatilho)"]:
            save_signal_to_db(signal)

    return signal

def save_signal_to_db(signal: Dict[str, Any]):
    """Registra um sinal gerado no banco de dados se ainda não registrado no mesmo dia."""
    try:
        with get_db_session() as session:
            sig_date = signal["date"]
            if isinstance(sig_date, str):
                sig_date = datetime.datetime.strptime(sig_date, "%Y-%m-%d").date()

            existing = (
                session.query(SwingSignal)
                .filter(
                    SwingSignal.ticker_symbol == signal["ticker"],
                    SwingSignal.date == sig_date,
                    SwingSignal.strategy == signal["strategy"]
                )
                .first()
            )

            if not existing:
                s = SwingSignal(
                    ticker_symbol=signal["ticker"],
                    date=sig_date,
                    strategy=signal["strategy"],
                    signal_type=signal["signal"],
                    entry_price=signal["entry_price"],
                    stop_loss=signal["stop_loss"],
                    target_1=signal["target_1"],
                    target_2=signal["target_2"],
                    risk_reward=signal["risk_reward"],
                    details=signal["reason"],
                    status="OPEN"
                )
                session.add(s)
                session.commit()
    except Exception as e:
        logger.error(f"Erro ao salvar sinal no banco: {e}")

def sync_all_tickers(
    force_download: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Sincroniza todos os ativos ativos e retorna lista consolidada de análises.
    Sincroniza primeiro o BOVA11 para servir de benchmark para todos os papéis.
    """
    # 1. Sincroniza o Benchmark primeiro
    bova_df, _ = get_or_sync_ticker_candles("BOVA11.SA", force_download=force_download, min_candles=100)

    tickers = get_active_tickers()
    total = len(tickers)
    results = []

    for i, t in enumerate(tickers):
        symbol = t["symbol"]
        if progress_callback:
            progress_callback((i + 1) / total, f"Processando {symbol} ({t['name']})...")

        analysis = sync_ticker_data(symbol, force_download=force_download, df_benchmark=bova_df)
        if analysis:
            analysis["name"] = t["name"]
            analysis["sector"] = t["sector"]
            results.append(analysis)

    return results

def get_database_stats() -> Dict[str, Any]:
    """Retorna estatísticas do banco de dados (total de candles, ativos e última data)."""
    with get_db_session() as session:
        total_candles = session.query(func.count(DailyCandle.id)).scalar() or 0
        total_tickers = session.query(func.count(Ticker.id)).filter(Ticker.is_active == True).scalar() or 0
        total_signals = session.query(func.count(SwingSignal.id)).scalar() or 0
        latest_date = session.query(func.max(DailyCandle.date)).scalar()
        return {
            "total_candles": total_candles,
            "total_tickers": total_tickers,
            "total_signals": total_signals,
            "latest_candle_date": latest_date
        }
