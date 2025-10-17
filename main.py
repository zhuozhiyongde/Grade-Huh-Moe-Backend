from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


@app.post("/med-scores")
async def fetch_med_scores(payload: CredentialPayload):
    gid = (payload.gid or "").strip() or None
    if gid and not Session._is_valid_gid(gid):
        return {"success": False, "errMsg": "GID 格式不正确，请重新填写"}

    session = Session(
        {"username": payload.username, "password": payload.password, "gid": gid}
    )
    try:
        await run_in_threadpool(session.login)
        data = await run_in_threadpool(session.get_grade)
        return {"success": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or "医学部成绩获取失败"
        return {"success": False, "errMsg": message}
    finally:
        await run_in_threadpool(session.close)
