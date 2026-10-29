@echo off
echo ========================================================
echo   Iniciando B3 Swing Trade Monitor com Docker e Postgres
echo ========================================================

docker compose up --build -d

echo.
echo Containers iniciados!
echo Acesse o dashboard no seu navegador: http://localhost:8501
echo Para parar os containers: docker compose down
pause
