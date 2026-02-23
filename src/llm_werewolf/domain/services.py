import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role, Team

DEFAULT_ROLE_COMPOSITION: list[Role] = [
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.KNIGHT,
    Role.SEER,
    Role.MEDIUM,
    Role.MADMAN,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
]

REQUIRED_PLAYER_COUNT = 9


def assign_roles(player_names: list[str], rng: random.Random | None = None) -> list[Player]:
    """配役: プレイヤー名リストにランダムで役職を割り当てる。

    Args:
        player_names: 9人のプレイヤー名リスト
        rng: テスト用の乱数生成器（None の場合は新規インスタンスを使用）

    Returns:
        役職が割り当てられた Player リスト

    Raises:
        ValueError: プレイヤー数が9人でない場合
    """
    if len(player_names) != REQUIRED_PLAYER_COUNT:
        raise ValueError(f"Player count must be {REQUIRED_PLAYER_COUNT}, got {len(player_names)}")
    if len(set(player_names)) != len(player_names):
        raise ValueError("player_names must be unique")

    if rng is None:
        rng = random.Random()

    roles = list(DEFAULT_ROLE_COMPOSITION)
    rng.shuffle(roles)

    return [Player(name=name, role=role) for name, role in zip(player_names, roles)]


def create_game_with_role(
    player_names: list[str],
    fixed_player: str,
    fixed_role: Role,
    rng: random.Random | None = None,
) -> GameState:
    """指定プレイヤーに指定役職を割り当ててゲームを初期化する。

    Args:
        player_names: 9人のプレイヤー名リスト
        fixed_player: 役職を固定するプレイヤー名
        fixed_role: 割り当てる役職
        rng: テスト用の乱数生成器

    Returns:
        初期化された GameState

    Raises:
        ValueError: プレイヤー数が9人でない場合、固定プレイヤーがリストにない場合、
                    または指定役職が配役構成に存在しない場合
    """
    if len(player_names) != REQUIRED_PLAYER_COUNT:
        raise ValueError(f"Player count must be {REQUIRED_PLAYER_COUNT}, got {len(player_names)}")
    if len(set(player_names)) != len(player_names):
        raise ValueError("player_names must be unique")
    if fixed_player not in player_names:
        raise ValueError(f"{fixed_player} is not in player_names")
    if fixed_role not in DEFAULT_ROLE_COMPOSITION:
        raise ValueError(f"{fixed_role.value} is not in the default role composition")

    if rng is None:
        rng = random.Random()

    remaining_roles = list(DEFAULT_ROLE_COMPOSITION)
    remaining_roles.remove(fixed_role)
    rng.shuffle(remaining_roles)

    players: list[Player] = []
    remaining_idx = 0
    for name in player_names:
        if name == fixed_player:
            players.append(Player(name=name, role=fixed_role))
        else:
            players.append(Player(name=name, role=remaining_roles[remaining_idx]))
            remaining_idx += 1

    return GameState(players=tuple(players))


def create_game(player_names: list[str], rng: random.Random | None = None) -> GameState:
    """ゲーム初期化: 配役を行い GameState を生成する。

    Args:
        player_names: 9人のプレイヤー名リスト
        rng: テスト用の乱数生成器（None の場合は新規インスタンスを使用）

    Returns:
        初期化された GameState
    """
    players = assign_roles(player_names, rng=rng)
    return GameState(players=tuple(players))


def check_victory(game: GameState) -> Team | None:
    """勝利判定: 勝利陣営を返す。未決着なら None。

    判定ルール:
        - 人狼が全滅 → Team.VILLAGE
        - 人狼以外の生存者数 ≦ 人狼の生存者数 → Team.WEREWOLF

    Args:
        game: 判定対象の GameState

    Returns:
        勝利した陣営（Team）。未決着なら None
    """
    alive_werewolf_count = len(game.alive_werewolves)
    alive_non_werewolf_count = len(game.alive_players) - alive_werewolf_count

    if alive_werewolf_count == 0:
        return Team.VILLAGE

    if alive_non_werewolf_count <= alive_werewolf_count:
        return Team.WEREWOLF

    return None


def can_divine(game: GameState, seer: Player, target: Player) -> None:
    """占い師が対象を占えるかチェックする。

    制約違反時は ValueError を送出する。

    Args:
        game: 現在のゲーム状態
        seer: 占い師のプレイヤー
        target: 占い対象のプレイヤー

    Raises:
        ValueError: 制約違反の場合
    """
    if seer.role != Role.SEER:
        raise ValueError(f"{seer.name} is not a seer")
    if not seer.is_alive:
        raise ValueError(f"{seer.name} is dead and cannot divine")
    if target not in game.players:
        raise ValueError(f"{target.name} is not in the game")
    if not target.is_alive:
        raise ValueError(f"{target.name} is dead and cannot be divined")
    if seer.name == target.name:
        raise ValueError(f"{seer.name} cannot divine themselves")
    if target.name in game.get_divined_history(seer.name):
        raise ValueError(f"{seer.name} has already divined {target.name}")


def can_attack(game: GameState, werewolf: Player, target: Player) -> None:
    """人狼が対象を襲撃できるかチェックする。

    制約違反時は ValueError を送出する。

    Args:
        game: 現在のゲーム状態
        werewolf: 人狼のプレイヤー
        target: 襲撃対象のプレイヤー

    Raises:
        ValueError: 制約違反の場合
    """
    if werewolf.role != Role.WEREWOLF:
        raise ValueError(f"{werewolf.name} is not a werewolf")
    if not werewolf.is_alive:
        raise ValueError(f"{werewolf.name} is dead and cannot attack")
    if target not in game.players:
        raise ValueError(f"{target.name} is not in the game")
    if not target.is_alive:
        raise ValueError(f"{target.name} is dead and cannot be attacked")
    if werewolf.name == target.name:
        raise ValueError(f"{werewolf.name} cannot attack themselves")
    if target.role == Role.WEREWOLF:
        raise ValueError(f"{werewolf.name} cannot attack another werewolf {target.name}")


def can_guard(game: GameState, knight: Player, target: Player) -> None:
    """狩人が対象を護衛できるかチェックする。

    制約違反時は ValueError を送出する。

    Args:
        game: 現在のゲーム状態
        knight: 狩人のプレイヤー
        target: 護衛対象のプレイヤー

    Raises:
        ValueError: 制約違反の場合
    """
    if knight.role != Role.KNIGHT:
        raise ValueError(f"{knight.name} is not a knight")
    if not knight.is_alive:
        raise ValueError(f"{knight.name} is dead and cannot guard")
    if target not in game.players:
        raise ValueError(f"{target.name} is not in the game")
    if not target.is_alive:
        raise ValueError(f"{target.name} is dead and cannot be guarded")
    if knight.name == target.name:
        raise ValueError(f"{knight.name} cannot guard themselves")
