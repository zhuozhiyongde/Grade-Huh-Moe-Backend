from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from get_gid import fetch_gid
from playwright.sync_api import sync_playwright
from session import Session


app = FastAPI(title="PKUHSC Grade Proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CredentialPayload(BaseModel):
    username: str
    password: str
    gid: str | None = None


@app.post("/med-gid")
async def fetch_med_gid(payload: CredentialPayload):
    username = payload.username.strip()
    password = payload.password
    if not username:
        return {"success": False, "errMsg": "请填写学号"}
    if not password:
        return {"success": False, "errMsg": "请填写密码"}

    def task() -> str:
        with sync_playwright() as playwright:
            return fetch_gid(playwright, username, password)

    try:
        gid = await run_in_threadpool(task)
        return {"success": True, "gid": gid}
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or "GID 获取失败"
        return {"success": False, "errMsg": message}


@app.post("/med-scores")
async def fetch_med_scores(payload: CredentialPayload):
    gid = (payload.gid or "").strip()
    if not gid:
        return {"success": False, "errMsg": "请填写 GID"}
    if not Session._is_valid_gid(gid):
        return {"success": False, "errMsg": "GID 格式不正确，请重新填写"}

    session: Session | None = None
    try:
        session = Session(
            {"username": payload.username, "password": payload.password, "gid": gid}
        )
        await run_in_threadpool(session.login)
        data = await run_in_threadpool(session.get_grade)
        return {"success": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or "医学部成绩获取失败"
        return {"success": False, "errMsg": message}
    finally:
        if session:
            await run_in_threadpool(session.close)
