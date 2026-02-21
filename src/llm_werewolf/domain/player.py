from dataclasses import dataclass, field

from llm_werewolf.domain.value_objects import PlayerStatus, Role


@dataclass
class Player:
    """プレイヤーエンティティ"""

    name: str
    role: Role
    status: PlayerStatus = field(default=PlayerStatus.ALIVE)

    @property
    def is_alive(self) -> bool:
        return self.status == PlayerStatus.ALIVE

    def kill(self) -> None:
        """処刑または襲撃によりプレイヤーを死亡状態にする"""
        if not self.is_alive:
            raise ValueError(f"{self.name} is already dead")
        self.status = PlayerStatus.DEAD
