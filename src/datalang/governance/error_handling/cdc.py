from .base import AppError
from fastapi import status


class CDCError(AppError):
    default_message = "A CDC operation failed."
    error_code = "CDC_ERROR"


class CDCUserError(CDCError):
    default_message = "CDC user operation failed."
    error_code = "CDC_USER_ERROR"


class CDCUserAlreadyExistsError(CDCUserError):
    default_message = "CDC user already exists."
    error_code = "CDC_USER_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT


class CDCUsernameDuplicated(CDCUserError):
    default_message = "CDC username is duplicated."
    error_code = "CDC_USERNAME_DUPLICATED"
    status_code = status.HTTP_409_CONFLICT


class CDCUserNotFoundError(CDCUserError):
    default_message = "CDC user not found."
    error_code = "CDC_USER_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class CDCUserPermissionError(CDCUserError):
    default_message = "CDC user lacks the required privileges."
    error_code = "CDC_USER_PERMISSION_ERROR"
    status_code = status.HTTP_403_FORBIDDEN


class CDCConnectorError(CDCError):
    default_message = "CDC connector operation failed."
    error_code = "CDC_CONNECTOR_ERROR"


class CDCConnectorNotFoundError(CDCConnectorError):
    default_message = "CDC connector not found."
    error_code = "CDC_CONNECTOR_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class CDCConnectorAlreadyExistsError(CDCConnectorError):
    default_message = "CDC connector already exists."
    error_code = "CDC_CONNECTOR_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT
