class AppError(Exception):
    """Base exception for application errors."""

    default_message = "An application error occurred."
    error_code = "APP_ERROR"
    status_code = 500

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)
