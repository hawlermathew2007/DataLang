from .base import AppError
from fastapi import status


class SessionError(AppError):
    default_message = "A session error occurred."
    error_code = "SESSION_ERROR"


class SessionNotFoundError(SessionError):
    default_message = "Session not found. Please connect to a database."
    error_code = "SESSION_NOT_FOUND"
    status_code = status.HTTP_401_UNAUTHORIZED


class SessionExpiredError(SessionError):
    default_message = "Session expired. Please reconnect."
    error_code = "SESSION_EXPIRED"
    status_code = status.HTTP_401_UNAUTHORIZED


class SessionPermissionError(SessionError):
    default_message = "You don't have permission to access this session."
    error_code = "SESSION_PERMISSION_DENIED"
    status_code = status.HTTP_403_FORBIDDEN


class SessionOwnerMismatchError(SessionError):
    default_message = "Session belongs to another owner."
    error_code = "SESSION_OWNER_MISMATCH"
    status_code = status.HTTP_403_FORBIDDEN
