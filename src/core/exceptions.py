from typing import Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        status_code: int = 400,
        code: str = "BAD_REQUEST",
        message: str = "An error occurred",
        details: Optional[Any] = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(status_code=401, code="UNAUTHORIZED", message=message)


class ForbiddenError(AppException):
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(status_code=403, code="FORBIDDEN", message=message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(status_code=404, code="NOT_FOUND", message=message)


class ConflictError(AppException):
    def __init__(self, message: str = "Resource conflict detected"):
        super().__init__(status_code=409, code="CONFLICT", message=message)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None):
        super().__init__(status_code=422, code="VALIDATION_ERROR", message=message, details=details)


class RateLimitError(AppException):
    def __init__(self, message: str = "Too many requests, please try again later"):
        super().__init__(status_code=429, code="RATE_LIMITED", message=message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    content = {
        "success": False,
        "error": {
            "code": exc.code,
            "message": exc.message,
        },
        "request_id": request_id,
    }
    if exc.details is not None:
        content["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=content)
