"""Custom exceptions for Quality Forge."""


class QualityForgeError(Exception):
    """Base exception for Quality Forge errors."""
    
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigurationError(QualityForgeError):
    """Raised when there's a configuration error."""
    pass


class AnalysisError(QualityForgeError):
    """Raised when there's an error during code analysis."""
    pass


class GitOperationError(QualityForgeError):
    """Raised when there's an error during git operations."""
    pass


class PatchApplicationError(QualityForgeError):
    """Raised when there's an error applying patches."""
    pass


class RateLimitError(QualityForgeError):
    """Raised when rate limits are exceeded."""
    pass


class TokenLimitError(QualityForgeError):
    """Raised when token limits are exceeded."""
    pass


class NetworkError(QualityForgeError):
    """Raised when there's a network-related error."""
    pass