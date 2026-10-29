# 📈 B3 Swing Trade Monitor & Scanner

Sistema profissional de rastreamento, análise técnica e monitoramento de ações da **B3 (Bolsa de Valores Brasileira)** para **Swing Trade**, desenvolvido em **Python**, **Streamlit**, **Plotly** e banco de dados **PostgreSQL** orquestrado com **Docker**.

---

## 🎯 Objetivo

Diferente do Day Trade (que busca operações intradiárias em gráficos de minutos), este sistema é voltado para **Swing Trade** (operações com duração de dias a semanas) utilizando **gráficos diários (D1)**. 

O sistema automatiza:
1. **Coleta e persistência diária** de candles históricos via `yfinance` e `PostgreSQL`.
2. **Cálculo de múltiplos indicadores técnicos**: Médias Móveis Exponenciais (EMA 9, 20, 50, 200), IFR/RSI (14) com suavização clássica de Wilder, MACD (12, 26, 9), Bandas de Bollinger (20, 2), ATR (14) e padrões de candlestick (Martelo, Engolfo de Alta, Inside Bar).
3. **Detecção automatizada de Setups de Compra de alta probabilidade**:
   - **Recuo na Tendência (Trend Pullback)**: Compra na correção saudável sobre a EMA 20 ou EMA 50 com IFR equilibrado.
   - **Sobrevenda com Gatilho (IFR < 38)**: Repique com stop curto em zonas de suporte ou banda inferior.
   - **Setup 9.1 de Larry Williams**: Inversão da EMA 9 com gatilho no rompimento da máxima.
   - **Rompimento de Resistência (Breakout)**: Aceleração com volume acima da média.
4. **Gestão de Risco Automatizada**: Cálculo técnico de **Preço de Entrada**, **Stop Loss**, **Alvo 1 (Parcial 1:1.5)**, **Alvo 2 (Final 1:2.5)** e **Relação Risco:Retorno**.
5. **Calculadora de Dimensionamento de Posição**: Informando seu capital e tolerância ao risco (ex: 1% a 2%), o sistema calcula exatamente quantas ações comprar e a alocação máxima recomendada.

---

## 🏗️ Arquitetura do Sistema

```
b3_day_trade/
├── app.py                     # Interface Web Streamlit interativa
├── Dockerfile                 # Imagem Docker otimizada da aplicação
├── docker-compose.yml         # Orquestração do app + banco PostgreSQL
├── requirements.txt           # Dependências Python (pip)
├── environment.yml            # Ambiente Miniconda / Anaconda
├── run_docker.bat             # Atalho Windows para iniciar no Docker
├── run_local.bat              # Atalho Windows para iniciar localmente
├── database/
│   ├── __init__.py
│   ├── connection.py          # Conexão resiliente (PostgreSQL c/ fallback SQLite)
│   └── models.py              # Tabelas: tickers, daily_candles, swing_signals
├── src/
│   ├── __init__.py
│   ├── default_tickers.py     # Cesta com as principais ações e ETFs da B3
│   ├── data_collector.py      # Sincronização yfinance + gravação em banco
│   ├── indicators.py          # Motor vetorial de indicadores (puro Pandas/NumPy)
│   ├── strategies.py          # Regras e filtros de Swing Trade
│   ├── chart_builder.py       # Gráficos interativos Candlestick com Plotly
│   └── risk_manager.py        # Algoritmo de dimensionamento e gestão de risco
└── tests/
    └── test_engine.py         # Testes automatizados do motor analítico
```

---

## 🐳 Como Executar com Docker (Recomendado)

O projeto inclui orquestração completa com **Docker Compose**, subindo o banco **PostgreSQL** e o painel **Streamlit** em containers isolados.

### 1. Iniciar os Containers

Certifique-se de que o **Docker Desktop** esteja aberto no seu computador e execute:

```bash
docker compose up --build
```

*(Ou simplesmente dê dois cliques no arquivo `run_docker.bat` no Windows)*

### 2. Acessar o Dashboard

Abra seu navegador em:
👉 **`http://localhost:8501`**

Para parar a execução:
```bash
docker compose down
```

---

## 📦 Como Disponibilizar e Compartilhar a Imagem Docker

Você pode gerar uma imagem Docker pronta da aplicação para rodar em qualquer servidor, nuvem ou computador sem precisar instalar Python ou dependências:

### Opção A: Salvar a Imagem em Arquivo `.tar` (Para envio direto)

1. Construa a imagem:
```bash
docker build -t b3-swing-trade-app:latest .
```

2. Salve a imagem em um arquivo compactado:
```bash
docker save -o b3_swing_trade_image.tar b3-swing-trade-app:latest
```

3. Em outra máquina, carregue a imagem:
```bash
docker load -i b3_swing_trade_image.tar
```

### Opção B: Publicar no Docker Hub (Compartilhamento público/privado)

1. Faça login na sua conta do Docker Hub:
```bash
docker login
```

2. Defina a tag da imagem com o seu usuário:
```bash
docker tag b3-swing-trade-app:latest SEU_USUARIO_DOCKER/b3-swing-trade:latest
```

3. Envie para o Docker Hub:
```bash
docker push SEU_USUARIO_DOCKER/b3-swing-trade:latest
```

Qualquer pessoa ou servidor poderá rodar com:
```bash
docker run -p 8501:8501 SEU_USUARIO_DOCKER/b3-swing-trade:latest
```

---

## 🐍 Como Executar Localmente com Miniconda / Anaconda

Se preferir rodar direto no terminal usando Conda:

### 1. Criar o Ambiente Conda

```bash
conda env create -f environment.yml
```

Ou criar manualmente via `conda-forge`:
```bash
conda create -n b3_swing_trade -c conda-forge python=3.10 -y
conda activate b3_swing_trade
pip install -r requirements.txt
```

### 2. Ativar o Ambiente e Executar

```bash
conda activate b3_swing_trade
streamlit run app.py
```

*(Ou dê dois cliques no arquivo `run_local.bat`)*

> **Nota:** Caso o PostgreSQL não esteja rodando fora do Docker, a aplicação utilizará automaticamente o banco de dados **SQLite local (`b3_swing_trade.db`)** como fallback, permitindo o funcionamento imediato sem configurações extras!

---

## 📊 Estratégias de Swing Trade Implementadas

### 1. Recuo na Tendência (Trend Pullback)
- **Condição**: Ativo em tendência de alta ($Preço > EMA_{50}$ e $EMA_{20} > EMA_{50}$).
- **Correção**: Preço recuou até a região da $EMA_{20}$ ou $EMA_{50}$ (distância $\le 3\%$).
- **Momento**: IFR (14) em correção equilibrada (entre 35 e 55).
- **Gatilho**: Candle de reversão (Martelo, Engolfo de Alta ou fechamento positivo).

### 2. Sobrevenda em Suporte (IFR < 38)
- **Condição**: IFR (14) atingiu nível sobrevendido ($\le 38$).
- **Região**: Preço próximo da Banda Inferior de Bollinger ou $EMA_{200}$.
- **Gatilho**: Reação compradora para busca de repique técnico até a média.

### 3. Setup 9.1 de Larry Williams
- **Condição**: A $EMA_9$ vinha apontando para baixo e virou para cima em candle de alta.
- **Filtro**: Preço acima da $EMA_{50}$ ou $EMA_{200}$.
- **Gatilho**: Rompimento da máxima do candle que virou a média.

### 4. Rompimento de Resistência (Breakout)
- **Condição**: Fechamento rompe a máxima dos últimos 20 dias úteis.
- **Volume**: Volume financeiro do dia pelo menos $1.25\times$ acima da média móvel de 20 dias de volume.

---

## 🛡️ Gestão de Risco e Dimensionamento

O cálculo de posição segue a fórmula matemática de controle de risco institucional:

$$\text{Risco Unitário (R\$)} = \text{Preço de Entrada} - \text{Stop Loss}$$

$$\text{Quantidade de Ações} = \left\lfloor \frac{\text{Capital Total} \times (\text{Risco \%} / 100)}{\text{Risco Unitário}} \right\rfloor$$

- **Alvo 1 (Parcial)**: Relação 1:1.5 (realizar metade da posição e proteger no ponto de entrada).
- **Alvo 2 (Final)**: Relação 1:2.5 ou superior.
- **Stop Loss Técnico**: Posicionado abaixo do suporte recente ou calibrado pelo indicador ATR (Average True Range) para evitar "violinos" por ruído de mercado.

---

## 🧪 Testes Automatizados

Para testar todos os módulos analíticos e de banco:
```bash
python tests/test_engine.py
```
