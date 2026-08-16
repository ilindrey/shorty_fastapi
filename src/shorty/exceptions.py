"""Framework-independent errors exposed by the domain and application layers."""


class ShortyError(Exception):
    """Base class for expected failures produced by Shorty use cases."""


class DomainError(ShortyError):
    """A domain rule was violated."""


class InvalidSubpartError(DomainError):
    """A user-supplied subpart violates naming rules."""


class ApplicationError(ShortyError):
    """An application use case could not be completed."""


class SubpartAlreadyExistsError(ApplicationError):
    """A user-supplied subpart is already occupied."""


class ConcurrentUpdateError(ApplicationError):
    """An aggregate was concurrently modified."""


class SubpartGenerationError(ApplicationError):
    """No free generated subpart could be found within the retry limit."""
