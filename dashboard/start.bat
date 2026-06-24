@echo off
REM =============================================
REM  酒店投资计算器 - 后台看板系统 启动脚本
REM  双击此文件启动本地服务
REM =============================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   酒店投资计算器 · 后台看板系统
echo ============================================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 安装依赖（首次运行）
if not exist "venv\" (
    echo [首次运行] 创建虚拟环境并安装依赖...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install flask
) else (
    call venv\Scripts\activate.bat
)

echo [启动] 服务运行中...
echo.
echo   看板地址: http://localhost:5099/?auth=admin888
echo   健康检查: http://localhost:5099/api/health
echo.
echo   按 Ctrl+C 停止服务
echo ============================================================
echo.

python server.py
pause
