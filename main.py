# Python
import ast
import asyncio
import base64
import importlib.util
import json
import logging
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

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Загрузка .env
load_dotenv()

# Параметры из окружения
CPU_LIMIT = int(os.getenv("CPU_LIMIT_SECONDS", 2))
MEMORY_LIMIT = int(os.getenv("MEMORY_LIMIT_MB", 64)) * 1024 * 1024
TIMEOUT = int(os.getenv("EXEC_TIMEOUT_SECONDS", 3))
AUTH_USER = os.getenv("BASIC_AUTH_USER")
AUTH_PASS = os.getenv("BASIC_AUTH_PASS")

app = FastAPI()


class CodeRequest(BaseModel):
    code: str
    args: List


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
            logger.warning("Unauthorized access attempt")
            raise ValueError("Invalid credentials")
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return JSONResponse(status_code=401, content={"detail": "Invalid basic auth"})

    return await call_next(request)


def set_limits():
    system = platform.system()

    try:
        if CPU_LIMIT > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
            logger.info(f"RLIMIT_CPU set to {CPU_LIMIT}s")
        else:
            logger.info("RLIMIT_CPU disabled (value=0)")

        if MEMORY_LIMIT > 0:
            if system == "Linux":
                resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
                logger.info(f"RLIMIT_AS set to {MEMORY_LIMIT // (1024 * 1024)} MB")
            elif system == "Darwin":
                logger.warning(
                    "RLIMIT_AS is not supported on macOS — skipping memory limit"
                )
        else:
            logger.info("RLIMIT_AS disabled (value=0)")

    except ValueError as ve:
        logger.error(f"Invalid resource limit value: {ve}")
    except Exception as e:
        logger.exception(f"set_limits failed: {e}")
        raise


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
        logger.info(f"Extracted imports: {modules}")
        return list(modules)
    except Exception as e:
        logger.error(f"Failed to extract imports: {e}")
        return []


def ensure_modules_installed(modules: list[str]):
    missing = []
    for name in modules:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if not missing:
        return
    logger.info(f"Installing missing modules: {missing}")
    try:
        subprocess.run(
            ["pip", "install", "--no-cache-dir"] + missing,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("Modules installed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Pip install error: {e.stderr.decode().strip()}")
        raise RuntimeError(f"Failed to install modules: {e.stderr.decode().strip()}")
    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error during pip install: {e}")
        raise RuntimeError(f"Subprocess error: {e}")


def sync_run(wrapped_code: str) -> dict:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as tmp:
        tmp.write(wrapped_code)
        tmp.flush()
        tmp_path = tmp.name

    logger.info(f"Executing code at {tmp_path}")
    try:
        run_args = {
            "args": ["python3", tmp_path],
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": TIMEOUT,
        }
        if platform.system() == "Linux":
            run_args["preexec_fn"] = set_limits

        result = subprocess.run(**run_args)
        logger.info(f"Execution finished with code {result.returncode}")
        return {
            "stdout": result.stdout.decode().strip(),
            "stderr": result.stderr.decode().strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        logger.warning("Code execution timed out")
        return {"error": "Execution timed out"}
    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error: {e}")
        return {"error": f"Subprocess error: {e}"}
    except Exception as e:
        logger.error(f"Unknown execution error: {e}")
        return {"error": f"Unknown error: {e}"}
    finally:
        os.unlink(tmp_path)
        logger.debug(f"Deleted temp file {tmp_path}")


@app.post("/run")
async def run_code(payload: CodeRequest):
    logger.info("Received code execution request")
    try:
        modules = extract_imports(payload.code)
        ensure_modules_installed(modules)

        wrapped_code = f"""{payload.code}

args = {json.dumps(payload.args)}
result = run(*args)
print(result)
"""
        result = await asyncio.get_running_loop().run_in_executor(
            None, sync_run, wrapped_code
        )
        logger.info(f"{result}")

        if "error" in result:
            logger.error(f"Execution error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except Exception as e:
        logger.exception("Unhandled exception during /run")
        raise HTTPException(status_code=500, detail=str(e))
