from llm_werewolf.domain.value_objects import Phase, PlayerStatus, Role, Team


class TestTeam:
    def test_values(self) -> None:
        assert Team.VILLAGE.value == "village"
        assert Team.WEREWOLF.value == "werewolf"


class TestRole:
    def test_values(self) -> None:
        assert Role.VILLAGER.value == "villager"
        assert Role.SEER.value == "seer"
        assert Role.WEREWOLF.value == "werewolf"

    def test_team_mapping(self) -> None:
        assert Role.VILLAGER.team == Team.VILLAGE
        assert Role.SEER.team == Team.VILLAGE
        assert Role.WEREWOLF.team == Team.WEREWOLF


class TestPhase:
    def test_values(self) -> None:
        assert Phase.DAY.value == "day"
        assert Phase.NIGHT.value == "night"


class TestPlayerStatus:
    def test_values(self) -> None:
        assert PlayerStatus.ALIVE.value == "alive"
        assert PlayerStatus.DEAD.value == "dead"
