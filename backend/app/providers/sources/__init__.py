"""Real job sources. Each module exposes a JobSource class plus a pure `parse_*` mapper."""

from collections.abc import Callable

from app.models.enums import Source
from app.providers.base import JobSource

REAL_SOURCES: dict[Source, Callable[[], JobSource]] = {}
