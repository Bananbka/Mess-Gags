import time
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from loguru import logger

from app.core.config import settings
from app.core.logger import setup_logging
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    global_exception_handler
)
from app.core.responses import SuccessResponse
from app.infrastructure.mongo import connect_to_mongo, close_mongo_connection
from app.infrastructure.redis import init_redis

setup_logging(is_production=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mess&Gags API...")
    await connect_to_mongo()
    await init_redis()
    yield
    logger.info("Stopping Mess&Gags API...")
    await close_mongo_connection()


app = FastAPI(title="Mess&Gags API", lifespan=lifespan)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    logger.info(f"Incoming request: {request.method} {request.url.path}")

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(
        f"Completed request: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.4f}s")

    return response


@app.get("/health", response_model=SuccessResponse[dict])
async def health_check():
    return SuccessResponse(data={"status": "ok", "project": "Mess&Gags"})


@app.get("/error-test")
async def error_test():
    raise AppException(
        status_code=400,
        error_code="TEST_ERROR",
        message="Це тестова помилка, щоб перевірити формат"
    )
