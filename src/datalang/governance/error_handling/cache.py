from .base import AppError
from fastapi import status


class CacheError(AppError):
    error_code = "CACHE_ERROR"
    default_message = "A cache error occurred."


class CacheNotFoundError(CacheError):
    default_message = "Cache not found."
    error_code = "CACHE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class CachePermissionError(CacheError):
    default_message = "Permission denied."
    error_code = "CACHE_PERMISSION_DENIED"
    status_code = status.HTTP_403_FORBIDDEN


class WrongOwnerError(CacheError):
    error_code = "WRONG_CACHE_OWNER"
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "This cache does not belong to this owner."
