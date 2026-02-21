from enum import Enum


class Team(str, Enum):
    """陣営"""

    VILLAGE = "village"
    WEREWOLF = "werewolf"


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


class Phase(str, Enum):
    """フェーズ"""

    DAY = "day"
    NIGHT = "night"


class PlayerStatus(str, Enum):
    """生存状態"""

    ALIVE = "alive"
    DEAD = "dead"
