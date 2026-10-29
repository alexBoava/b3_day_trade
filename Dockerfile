# Imagem base oficial Python slim
FROM python:3.10-slim

# Metadados
LABEL maintainer="Antigravity B3 Swing Trade"
LABEL description="Monitor de Ações B3 para Swing Trade com Streamlit e PostgreSQL"

# Evitar criação de arquivos .pyc e garantir output direto no console
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalação de dependências do sistema necessárias para compilação e PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements primeiro para aproveitar cache de camadas do Docker
COPY requirements.txt .

# Atualizar pip e instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código-fonte da aplicação
COPY . .

# Expor a porta padrão do Streamlit
EXPOSE 8501

# Healthcheck do container
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Comando de inicialização do Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
