"""Real job sources. Each module exposes a JobSource class plus a pure `parse_*` mapper."""

from collections.abc import Callable

from app.models.enums import Source
from app.providers.base import JobSource
from app.providers.sources.arbeitnow import ArbeitnowSource
from app.providers.sources.remotive import RemotiveSource

REAL_SOURCES: dict[Source, Callable[[], JobSource]] = {
    Source.arbeitnow: ArbeitnowSource,
    Source.remotive: RemotiveSource,
}
