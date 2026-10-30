from .base import AppError
from fastapi import status


class DatabaseError(AppError):
    default_message = "A database error occurred."
    error_code = "DATABASE_ERROR"


class DatabaseConnectionError(DatabaseError):
    default_message = "Unable to connect to the database."
    error_code = "DATABASE_CONNECTION_ERROR"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class DatabaseAuthenticationError(DatabaseError):
    default_message = "Database authentication failed."
    error_code = "DATABASE_AUTHENTICATION_ERROR"
    status_code = status.HTTP_401_UNAUTHORIZED


class DatabasePermissionError(DatabaseError):
    default_message = "Insufficient database privileges."
    error_code = "DATABASE_PERMISSION_ERROR"
    status_code = status.HTTP_403_FORBIDDEN


class DatabaseNotFoundError(DatabaseError):
    default_message = "Database not found."
    error_code = "DATABASE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class DatabaseOperationError(DatabaseError):
    default_message = "Database operation failed."
    error_code = "DATABASE_OPERATION_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
