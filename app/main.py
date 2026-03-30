from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse

from .api import transactions, members
from .api.auth import router as auth_router
from .web import router as web_router
from .models import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ProjectSilpPrint", lifespan=lifespan)

app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
app.include_router(members.router, prefix="/members", tags=["members"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(web_router, prefix="/web", tags=["web"])


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})


@app.get("/")
def root():
    return RedirectResponse("/web/login")
