from __future__ import annotations
from sqlalchemy.orm import Session

from ..models import Setting
from ..interfaces.base import ISettingsRepo


class SqlSettingsRepo(ISettingsRepo):
    KEY = "app_yaml"

    def __init__(self, session: Session):
        self.s = session

    def get_yaml(self) -> str:
        row = self.s.query(Setting).filter(Setting.key == self.KEY).one_or_none()
        return row.value_yaml if row else ""

    def put_yaml(self, yaml_str: str) -> None:
        row = self.s.query(Setting).filter(Setting.key == self.KEY).one_or_none()
        if row:
            row.value_yaml = yaml_str
        else:
            self.s.add(Setting(key=self.KEY, value_yaml=yaml_str))
