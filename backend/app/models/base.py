from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def enum_field(default: Any = ..., **kwargs: Any) -> Any:
    """An enum column stored as its string value (VARCHAR), so new values need no migration."""
    return Field(default=default, sa_type=String(32), **kwargs)


def json_field(default_factory: Any = list, **kwargs: Any) -> Any:
    return Field(default_factory=default_factory, sa_type=JSON, **kwargs)


def dt_field(default: Any = None, *, default_factory: Any = None, **kwargs: Any) -> Any:
    if default_factory is not None:
        return Field(default_factory=default_factory, sa_type=UTCDateTime, **kwargs)
    return Field(default=default, sa_type=UTCDateTime, **kwargs)


class TableBase(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_type=UTCDateTime, sa_column_kwargs={"onupdate": utcnow}
    )
