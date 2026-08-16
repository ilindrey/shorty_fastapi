"""Pydantic schemas shared by the HTTP representations."""

from pydantic import AnyUrl, BaseModel, Field


class CreateLinkRequest(BaseModel):
    """Payload for shortening a URL."""

    url: AnyUrl
    subpart: str | None = Field(default=None, min_length=3, max_length=32)


class LinkResponse(BaseModel):
    """A single shortened link."""

    subpart: str
    url: str
    clicks: int


class LinkPageResponse(BaseModel):
    """One page of shortened links."""

    items: list[LinkResponse]
    page: int
    page_size: int
    total: int
