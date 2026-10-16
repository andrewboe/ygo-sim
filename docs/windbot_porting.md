# Porting a WindBot deck executor

How to port an IceYGO/windbot deck executor (`Game/AI/Decks/<Name>Executor.cs`, MIT) to
`wsl/windbot_decks/<name>.py` so ygo-sim's card handlers run it (docs/windbot_plan.md, phase 3). The goal is
WindBot's behaviour, rule for rule: same rows in the same order, same conditions, same overrides. Keep the
C# names (PascalCase) so the port reads side by side with the source.

## Layout

```python
"""<Deck> executor, ported from IceYGO/windbot Game/AI/Decks/<Name>Executor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: <what the env can't show, see below, and anything left out>."""
from windbot import *                      # Card, CardId helpers, enums, CardContainer functions, Rand
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:                              # the C# CardId class, all constants
    JailChicken = 12345678


class ElfnoteExecutor(DefaultExecutor):
    DECK_EXECUTOR = True                   # GameAI's fallbacks (pass, end turn) count as choices

    def __init__(self):
        super().__init__()
        self.AddExecutor(ExecutorType.Activate, CardId.X, self.XActivate)   # rows in the C# order
        self.someFlag = False              # C# fields -> attributes set in __init__
```

Register the deck names it plays in `wsl/windbot_decks/__init__.py`.

## C# to Python

| C# | Python |
|---|---|
| `AddExecutor(ExecutorType.T, CardId.X, Func)` / `(T, Func)` / `(T, CardId.X)` / `(T)` | same call with `self.Func`; `AddExecutor(T)` keeps WindBot's DefaultNoExecutor rule |
| `Bot`, `Enemy`, `Duel`, `Util`, `AI`, `Card`, `ActivateDescription` | `self.Bot`, ... (same names) |
| `ClientCard` | `windbot.Card` (same members: `Id`, `Location`, `Sequence`, `Controller`, `Position`, `Attack`, `Level`, `Rank`, `LinkCount`, `Data`, `IsCode`, `HasType`, `HasSetcode`, `IsFaceup`, `IsOnField`, `GetDefensePower`, `GetAttackPower`, `IsMonsterDangerous`...) |
| `ChainInfo` | `windbot.ChainInfo` (`RelatedCard`, `ActivatePlayer`, `ActivateDescription`, `ActivateLocation`, `IsActivateCode`, `Targets`...) |
| `Duel.GetCurrentChainCard()`, `GetCurrentSolvingChainInfo()`, `IsCurrentSolvingChainNegated()`, `CurrentChain`, `CurrentChainInfo`, `LastChainPlayer`, `ChainTargets`, `LastChainTargets`, `LastSummonedCards`, `MainPhase.*`, `BattlePhase.*`, `Fields[i]` | same names |
| `AI.SelectCard(...)`, `SelectNextCard`, `SelectThirdCard`, `SelectMaterials`, `SelectPosition`, `SelectYesNo`, `SelectOption`, `SelectPlace`, `HaveSelectedCards`, `FindSumSelection`, `FindTributeSelection`, `AI.Attack(a, d)` | same names (`windbot_gameai.GameAI`) |
| `new BattlePhaseAction(BattlePhaseAction.BattleAction.ToMainPhaseTwo)` | `BattlePhaseAction(BattlePhaseAction.BattleAction.ToMainPhaseTwo)` |
| `Util.CheckSelectCount`, `ShuffleList`, `GetStringId`, `GetLastChainCard`, `IsChainTarget`, `GetProblematicEnemyCard`... | same names |
| `cards.GetMatchingCards(f)`, `GetHighestAttackMonster`, `GetFloodgate`, `ContainsCardWithId`... (CardContainer) | module functions: `GetMatchingCards(cards, f)`; `list.GetMonsters()` is `GetMonstersOf(list)` |
| `cards.Sort(CardContainer.CompareCardAttack)` | `cards.sort(key=CompareCardAttack)` |
| `Program.Rand` | `windbot.Rand` |
| LINQ `Where/Any/All/Count(f)/FirstOrDefault/OrderBy...ThenByDescending/ToList/Distinct` | comprehensions, `any`/`all`, `sum(1 for ...)`, `next(..., None)`, `sorted(key=(a, -b))`, `list`, `dict.fromkeys` |
| `list.Contains(card)`, `==` on cards | `in`, `==`: cards compare by (Id, Controller, Location, Sequence), standing in for WindBot's object identity |
| `null` | `None`; `IList<ClientCard>` -> list |
| overrides `OnSelectCard(cards, min, max, hint, cancelable)` etc. | same method names and argument order as `windbot.Executor` (`min_`, `max_`, `sum_`); call the base with `super()` |
| `Logger.DebugWriteLine`, deck-specific `...Log(...)` helpers | drop the calls (keep the logic around them) |

## What the env can't show

These evaluate as below; keep the C# logic, it just sees these values:
`IsDisabled()` is always False; `BattlingMonster` is None; Xyz material codes are 0 (counts are right);
`EquipCards` / `TargetCards` / `OwnTargets` are empty; link markers are 0; `Announces` is empty; `Attacked`
is False; `IsSpecialSummoned` is False; `LastLocation` is 0; hint descriptions (OnPlayerHint) and zone hints
(OnHintZone) don't arrive. Message callbacks (OnMove, OnChaining, OnChainSolved, OnChainEnd, OnNewPhase,
OnNewTurn, OnPosChange, OnSummoning, OnSpSummoned) do arrive, with the chain state of their time but the
current board.

If the executor needs a helper `windbot.py` doesn't have (an AIUtil / ClientField / CardContainer member),
write it as a module-level function in the executor file, named as in WindBot, and list it in the port's
docstring; it moves into `windbot.py` at review.

## Checking a port

```
wsl.exe -e bash <scratch>/run_test.sh exec_smoke.py <deck> <other deck> 2000 windbot_decks.<name>:<Class> -
```
runs self-play where every decision goes through the executor and prints exceptions (deduplicated, with
tracebacks), how often rows pick, and the top picks. A port is done when the smoke run has no errors on its
deck against two other decks and the top picks look like the deck's combo cards.
