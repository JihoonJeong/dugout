"""감독(매니저) 관리 — JSON 파일 기반."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Manager:
    manager_id: str
    nickname: str
    created_at: str = ""


class ManagerStore:
    """JSON 파일 기반 매니저 저장소."""

    def __init__(self, store_path: str = "data/managers.json"):
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        with open(self._path) as f:
            return json.load(f)

    def _save(self, managers: list[dict]) -> None:
        with open(self._path, "w") as f:
            json.dump(managers, f, indent=2)

    def register(self, nickname: str) -> Manager:
        """새 감독 등록. 닉네임 중복 체크."""
        nickname = nickname.strip()
        if not nickname or len(nickname) > 20:
            raise ValueError("Nickname must be 1-20 characters")

        managers = self._load()
        # 중복 체크
        for m in managers:
            if m["nickname"].lower() == nickname.lower():
                raise ValueError(f"Nickname '{nickname}' is already taken")

        mgr = Manager(
            manager_id=str(uuid.uuid4())[:8],
            nickname=nickname,
            created_at=datetime.utcnow().isoformat(),
        )
        managers.append(asdict(mgr))
        self._save(managers)
        logger.info("Manager registered: %s (%s)", mgr.nickname, mgr.manager_id)
        return mgr

    def get(self, manager_id: str) -> Manager | None:
        for m in self._load():
            if m["manager_id"] == manager_id:
                return Manager(**m)
        return None

    def get_all(self) -> list[Manager]:
        return [Manager(**m) for m in self._load()]

    def nickname_exists(self, nickname: str) -> bool:
        return any(
            m["nickname"].lower() == nickname.strip().lower() for m in self._load()
        )
