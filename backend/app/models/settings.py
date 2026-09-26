from typing import Any

from sqlmodel import Field

from app.models.base import TableBase, json_field


class AppSetting(TableBase, table=True):
    __tablename__ = "app_setting"

    key: str = Field(unique=True, index=True)
    value: dict[str, Any] = json_field(dict)
