@echo off
echo ========================================================
echo   Iniciando B3 Swing Trade Monitor (Modo Local)
echo ========================================================

REM Ativa o ambiente conda caso exista
call "C:\Users\User\Anaconda3\Scripts\activate.bat" b3_swing_trade 2>nul || call conda activate b3_swing_trade 2>nul

echo Executando Streamlit...
streamlit run app.py

pause
