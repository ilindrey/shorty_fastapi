"""Tests for the framework-independent error hierarchy."""

from shorty.exceptions import (
    ApplicationError,
    ConcurrentUpdateError,
    DomainError,
    InvalidSubpartError,
    ShortyError,
    SubpartAlreadyExistsError,
    SubpartGenerationError,
)


def test_expected_errors_share_the_shorty_base_class() -> None:
    assert issubclass(DomainError, ShortyError)
    assert issubclass(ApplicationError, ShortyError)
    assert issubclass(InvalidSubpartError, DomainError)
    assert issubclass(SubpartAlreadyExistsError, ApplicationError)
    assert issubclass(ConcurrentUpdateError, ApplicationError)
    assert issubclass(SubpartGenerationError, ApplicationError)
