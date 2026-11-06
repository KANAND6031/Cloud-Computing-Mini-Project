@echo off
setlocal enabledelayedexpansion

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

if "%1"=="train" goto train
if "%1"=="test" goto test
if "%1"=="lint" goto lint
if "%1"=="up" goto up
if "%1"=="down" goto down
if "%1"=="" goto help
goto help

:help
echo Targets:
echo   make up          - Create k3d cluster and deploy SeaweedFS
echo   make down        - Tear down the k3d cluster
echo   make train       - Train Pythia-70M student model (use SUBSET=50 for quick test)
echo   make test        - Run unit tests
echo   make lint        - Run linting with ruff
exit /b 0

:up
k3d cluster create --config cluster/k3d.yaml
kubectl apply -f deployment/seaweedfs.yaml
exit /b !errorlevel!

:down
k3d cluster delete cloud-assignment
exit /b !errorlevel!

:train
shift
set SUBSET_ARG=
:train_loop
if "%~1"=="" goto run_train
set ARG=%~1
if /i "!ARG:~0,7!"=="SUBSET=" (
    set SUBSET_ARG=--subset !ARG:~7!
)
shift
goto train_loop

:run_train
%PYTHON% training/train.py !SUBSET_ARG!
exit /b !errorlevel!

:test
%PYTHON% -m pytest tests/
exit /b !errorlevel!

:lint
ruff check .
exit /b !errorlevel!
