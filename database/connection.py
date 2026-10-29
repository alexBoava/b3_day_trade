import os
import logging
from contextlib import contextmanager
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DATABASE_TYPE = "PostgreSQL" if DATABASE_URL and DATABASE_URL.startswith("postgres") else "SQLite"

# Fallback para SQLite se DATABASE_URL estiver vazio ou inválido
if not DATABASE_URL:
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "b3_swing_trade.db")
    DATABASE_URL = f"sqlite:///{db_path}"
    DATABASE_TYPE = "SQLite"

# Ajustar compatibilidade com psycopg se url começar com postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    if "sqlite" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
except Exception as e:
    logger.warning(f"Erro ao inicializar conexão primária ({DATABASE_URL}): {e}. Usando SQLite.")
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "b3_swing_trade.db")
    DATABASE_URL = f"sqlite:///{db_path}"
    DATABASE_TYPE = "SQLite (Fallback)"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Cria todas as tabelas caso não existam."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Tabelas criadas ou validadas com sucesso no banco: {DATABASE_TYPE}")
        return True
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        return False

# Inicialização automática das tabelas
init_db()

@contextmanager
def get_db_session():
    """Gerenciador de contexto para sessões do banco de dados."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def check_db_connection():
    """Verifica saúde da conexão com o banco."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, DATABASE_TYPE
    except Exception as e:
        return False, str(e)
