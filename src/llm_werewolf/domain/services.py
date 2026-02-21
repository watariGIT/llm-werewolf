import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role, Team

DEFAULT_ROLE_COMPOSITION: list[Role] = [
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.SEER,
    Role.WEREWOLF,
]

REQUIRED_PLAYER_COUNT = 5


def assign_roles(player_names: list[str], rng: random.Random | None = None) -> list[Player]:
    """配役: プレイヤー名リストにランダムで役職を割り当てる。

    Args:
        player_names: 5人のプレイヤー名リスト
        rng: テスト用の乱数生成器（None の場合は新規インスタンスを使用）

    Returns:
        役職が割り当てられた Player リスト

    Raises:
        ValueError: プレイヤー数が5人でない場合
    """
    if len(player_names) != REQUIRED_PLAYER_COUNT:
        raise ValueError(f"Player count must be {REQUIRED_PLAYER_COUNT}, got {len(player_names)}")

    if rng is None:
        rng = random.Random()

    roles = list(DEFAULT_ROLE_COMPOSITION)
    rng.shuffle(roles)

    return [Player(name=name, role=role) for name, role in zip(player_names, roles)]


def create_game(player_names: list[str], rng: random.Random | None = None) -> GameState:
    """ゲーム初期化: 配役を行い GameState を生成する。

    Args:
        player_names: 5人のプレイヤー名リスト
        rng: テスト用の乱数生成器（None の場合は新規インスタンスを使用）

    Returns:
        初期化された GameState
    """
    players = assign_roles(player_names, rng=rng)
    return GameState(players=players)


def check_victory(game: GameState) -> Team | None:
    """勝利判定: 勝利陣営を返す。未決着なら None。

    判定ルール:
        - 人狼が全滅 → Team.VILLAGE
        - 村人陣営の生存者数 ≦ 人狼の生存者数 → Team.WEREWOLF

    Args:
        game: 判定対象の GameState

    Returns:
        勝利した陣営（Team）。未決着なら None
    """
    alive_werewolf_count = len(game.alive_werewolves)
    alive_village_count = len(game.alive_village_team)

    if alive_werewolf_count == 0:
        return Team.VILLAGE

    if alive_village_count <= alive_werewolf_count:
        return Team.WEREWOLF

    return None
