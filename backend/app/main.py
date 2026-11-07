import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, engine
from .routers import academics, admin, auth, community, parent, public
from .seed import run as seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aussnsc")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # for schema changes later, add Alembic migrations
    seed()
    yield


app = FastAPI(title="AUSSNSC School API", version="1.0.0", lifespan=lifespan,
              description="Backend for the AUSSNSC Android app (Ahammad Uddin Shah Shishu Niketan School & College).",
              docs_url="/docs" if settings.enable_docs else None,
              redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


API = "/api/v1"
for r in (auth.router, public.router, academics.router, parent.router, community.router, admin.router):
    app.include_router(r, prefix=API)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "env": settings.env}
