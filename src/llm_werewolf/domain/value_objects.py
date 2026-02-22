from __future__ import annotations

from enum import Enum


class Team(str, Enum):
    """陣営"""

    VILLAGE = "village"
    WEREWOLF = "werewolf"


class NightActionType(str, Enum):
    """夜行動種別"""

    DIVINE = "divine"
    ATTACK = "attack"


class Role(str, Enum):
    """役職"""

    VILLAGER = "villager"
    SEER = "seer"
    WEREWOLF = "werewolf"

    @property
    def team(self) -> Team:
        if self == Role.WEREWOLF:
            return Team.WEREWOLF
        return Team.VILLAGE

    @property
    def night_action_type(self) -> NightActionType | None:
        """この役職の夜行動種別を返す。夜行動がなければ None。"""
        return _ROLE_NIGHT_ACTION.get(self)

    @property
    def has_night_action(self) -> bool:
        """この役職が夜行動を持つかどうか。"""
        return self.night_action_type is not None


_ROLE_NIGHT_ACTION: dict[Role, NightActionType] = {
    Role.SEER: NightActionType.DIVINE,
    Role.WEREWOLF: NightActionType.ATTACK,
}


class Phase(str, Enum):
    """フェーズ"""

    DAY = "day"
    NIGHT = "night"


class PlayerStatus(str, Enum):
    """生存状態"""

    ALIVE = "alive"
    DEAD = "dead"
