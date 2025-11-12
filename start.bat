@echo off
chcp 65001 > nul
title 电机控制系统
echo ========================================
echo 电机控制与光谱仪数据采集系统 v2.0
echo ========================================
echo.
echo 正在启动程序...
echo.

python start.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo 程序启动失败！
    echo ========================================
    echo.
    echo 可能的原因:
    echo 1. Python未安装或未添加到PATH
    echo 2. 缺少必要的依赖库
    echo.
    echo 解决方法:
    echo 1. 安装Python 3.8+
    echo 2. 运行: pip install -r requirements.txt
    echo.
    pause
) else (
    echo.
    echo 程序已关闭
)

