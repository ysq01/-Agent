class ToolError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ToolNotFoundError(ToolError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class ToolValidationError(ToolError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=400)
