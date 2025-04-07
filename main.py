# Python
import asyncio
import base64
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

load_dotenv()

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
        b64_encoded = auth.split(" ")[1]
        decoded = base64.b64decode(b64_encoded).decode()
        username, password = decoded.split(":", 1)
        if username != AUTH_USER or password != AUTH_PASS:
            raise ValueError("Invalid credentials")
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid basic auth"})

    return await call_next(request)


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
        if platform.system() == "Linux":
            run_args["preexec_fn"] = set_limits

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


@app.post("/run")
async def run_code(payload: CodeRequest):
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
