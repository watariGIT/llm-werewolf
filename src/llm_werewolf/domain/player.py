from dataclasses import dataclass, field

from llm_werewolf.domain.value_objects import PlayerStatus, Role


@dataclass(frozen=True)
class Player:
    """プレイヤーエンティティ"""

    name: str
    role: Role
    status: PlayerStatus = field(default=PlayerStatus.ALIVE)

    @property
    def is_alive(self) -> bool:
        return self.status == PlayerStatus.ALIVE

    def killed(self) -> "Player":
        """処刑または襲撃により死亡した新しいプレイヤーを返す"""
        if not self.is_alive:
            raise ValueError(f"{self.name} is already dead")
        return Player(name=self.name, role=self.role, status=PlayerStatus.DEAD)
