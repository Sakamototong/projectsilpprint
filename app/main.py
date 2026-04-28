import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text as sa_text

from .api import transactions, members
from .api.auth import router as auth_router
from .web import router as web_router
from .admin.web import router as admin_router
from .models import Base, engine, SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


_BASE_DIR = Path(__file__).parent

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ProjectSilpPrint", lifespan=lifespan)
app.state.limiter = limiter
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

# ── Number format filters (comma thousand separator) ──
def _fmt(v, d=2):
    try: return f"{float(v):,.{d}f}"
    except (TypeError, ValueError): return "0." + "0"*d
templates.env.filters["fmt"]  = lambda v: _fmt(v, 2)
templates.env.filters["fmt0"] = lambda v: _fmt(v, 0)
templates.env.filters["fmt1"] = lambda v: _fmt(v, 1)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "คำขอบ่อยเกินไป กรุณารอสักครู่"},
    )


app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
app.include_router(members.router, prefix="/members", tags=["members"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(web_router, prefix="/web", tags=["web"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.get("/health")
def health():
    """Health check including database connectivity."""
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        db.close()
    except Exception:
        return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/payment", response_class=HTMLResponse)
async def payment_gateway(request: Request):
    return templates.TemplateResponse(request, "payment_gateway.html")


@app.get("/")
def root():
    return RedirectResponse("/web/login")
