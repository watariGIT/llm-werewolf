from llm_werewolf.domain.value_objects import NightActionType, Phase, PlayerStatus, Role, Team


class TestTeam:
    def test_values(self) -> None:
        assert Team.VILLAGE.value == "village"
        assert Team.WEREWOLF.value == "werewolf"


class TestNightActionType:
    def test_values(self) -> None:
        assert NightActionType.DIVINE.value == "divine"
        assert NightActionType.ATTACK.value == "attack"
        assert NightActionType.GUARD.value == "guard"


class TestRole:
    def test_values(self) -> None:
        assert Role.VILLAGER.value == "villager"
        assert Role.SEER.value == "seer"
        assert Role.WEREWOLF.value == "werewolf"
        assert Role.KNIGHT.value == "knight"
        assert Role.MEDIUM.value == "medium"
        assert Role.MADMAN.value == "madman"

    def test_team_mapping(self) -> None:
        assert Role.VILLAGER.team == Team.VILLAGE
        assert Role.SEER.team == Team.VILLAGE
        assert Role.WEREWOLF.team == Team.WEREWOLF
        assert Role.KNIGHT.team == Team.VILLAGE
        assert Role.MEDIUM.team == Team.VILLAGE
        assert Role.MADMAN.team == Team.WEREWOLF

    def test_night_action_type(self) -> None:
        assert Role.VILLAGER.night_action_type is None
        assert Role.SEER.night_action_type == NightActionType.DIVINE
        assert Role.WEREWOLF.night_action_type == NightActionType.ATTACK
        assert Role.KNIGHT.night_action_type == NightActionType.GUARD
        assert Role.MEDIUM.night_action_type is None
        assert Role.MADMAN.night_action_type is None

    def test_has_night_action(self) -> None:
        assert Role.VILLAGER.has_night_action is False
        assert Role.SEER.has_night_action is True
        assert Role.WEREWOLF.has_night_action is True
        assert Role.KNIGHT.has_night_action is True
        assert Role.MEDIUM.has_night_action is False
        assert Role.MADMAN.has_night_action is False


class TestPhase:
    def test_values(self) -> None:
        assert Phase.DAY.value == "day"
        assert Phase.NIGHT.value == "night"


class TestPlayerStatus:
    def test_values(self) -> None:
        assert PlayerStatus.ALIVE.value == "alive"
        assert PlayerStatus.DEAD.value == "dead"
