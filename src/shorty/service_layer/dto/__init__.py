"""Framework-independent data transferred through application interfaces."""

from shorty.service_layer.dto.queries import LinkSummary, RedirectTarget
from shorty.service_layer.dto.results import CreatedLink, LinkPage, PurgeResult

__all__ = (
    'CreatedLink',
    'LinkPage',
    'LinkSummary',
    'PurgeResult',
    'RedirectTarget',
)
