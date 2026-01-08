@echo off
chcp 65001 > nul
title 电机控制系统
echo ========================================
echo 电机控制与光谱仪数据采集系统 v2.0
echo ========================================
echo.
echo 正在启动程序...
echo.

REM 使用虚拟环境中的Python启动程序
.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo 程序启动失败！
    echo ========================================
    echo.
    echo 可能的原因:
    echo 1. 虚拟环境未创建或损坏
    echo 2. 缺少必要的依赖库
    echo.
    echo 解决方法:
    echo 1. 运行: python -m venv .venv
    echo 2. 运行: .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
) else (
    echo.
    echo 程序已关闭
)
