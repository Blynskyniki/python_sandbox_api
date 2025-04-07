# Python
import ast
import asyncio
import base64
import importlib.util
import json
import os
import platform
import resource
import subprocess
import tempfile
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Загрузка .env
load_dotenv()

# Параметры из окружения
CPU_LIMIT = int(os.getenv("CPU_LIMIT_SECONDS", 2))
MEMORY_LIMIT = int(os.getenv("MEMORY_LIMIT_MB", 64)) * 1024 * 1024
TIMEOUT = int(os.getenv("EXEC_TIMEOUT_SECONDS", 3))
AUTH_USER = os.getenv("BASIC_AUTH_USER")
AUTH_PASS = os.getenv("BASIC_AUTH_PASS")

# Инициализация FastAPI
app = FastAPI()


# Модель запроса
class CodeRequest(BaseModel):
    code: str
    args: List


# Middleware авторизации
@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if not AUTH_USER or not AUTH_PASS:
        return await call_next(request)

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    try:
        decoded = base64.b64decode(auth.split(" ")[1]).decode()
        username, password = decoded.split(":", 1)
        if username != AUTH_USER or password != AUTH_PASS:
            raise ValueError("Invalid credentials")
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid basic auth"})

    return await call_next(request)


# Ограничение ресурсов (Linux only)
def set_limits():
    if platform.system() != "Linux":
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    except Exception as e:
        import sys

        print(f"[sandbox] set_limits failed: {e}", file=sys.stderr)
        raise


# Извлечение импортов из кода
def extract_imports(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".")[0])
        return list(modules)
    except Exception:
        return []


# Установка недостающих библиотек
def ensure_modules_installed(modules: list[str]):
    missing = []
    for name in modules:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if not missing:
        return
    try:
        subprocess.run(
            ["pip", "install", "--no-cache-dir"] + missing,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to install modules: {e.stderr.decode().strip()}")
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"Subprocess error: {e}")


# Запуск кода в subprocess
def sync_run(wrapped_code: str) -> dict:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as tmp:
        tmp.write(wrapped_code)
        tmp.flush()
        tmp_path = tmp.name

    try:
        run_args = {
            "args": ["python3", tmp_path],
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": TIMEOUT,
        }
        # if platform.system() == "Linux":
        #     run_args["preexec_fn"] = set_limits

        result = subprocess.run(**run_args)
        return {
            "stdout": result.stdout.decode().strip(),
            "stderr": result.stderr.decode().strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Execution timed out"}
    except subprocess.SubprocessError as e:
        return {"error": f"Subprocess error: {e}"}
    except Exception as e:
        return {"error": f"Unknown error: {e}"}
    finally:
        os.unlink(tmp_path)


# Основная точка входа
@app.post("/run")
async def run_code(payload: CodeRequest):
    try:
        modules = extract_imports(payload.code)
        await asyncio.get_running_loop().run_in_executor(
            None, ensure_modules_installed, modules
        )

        wrapped_code = f"""{payload.code}

args = {json.dumps(payload.args)}
result = run(*args)
print(result)
"""
        result = await asyncio.get_running_loop().run_in_executor(
            None, sync_run, wrapped_code
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
