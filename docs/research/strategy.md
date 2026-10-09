# Competitive Yu-Gi-Oh! Strategy: Notes for an AI Pilot

Researched 2026-10-09. Sources are listed at the end. Card text was checked against the YGOPRODeck API, and list status against the TCG Forbidden & Limited list of 2026-09-21. Points tagged **[synthesis]** are my own reasoning from card text and the cited material, not claims made by a source.

Format snapshot (TCG, Sept/Oct 2026): Maxx "C" is **Forbidden**. Triple Tactics Talent, Harpie's Feather Duster, Called by the Grave and Crossout Designator are Limited, and Droll & Lock Bird is Semi-Limited. Ash, Imperm, Veiler, Ghost Ogre, Nibiru, the Mulcharmies, the Dominus traps, Droplet, Evenly Matched, DRNM, Lightning Storm, Super Poly and Triple Tactics Thrust are unrestricted. A Sept 2026 banlist review describes the format as decks that "position themselves to win going first through ~2 pieces of interaction" (Kachmarik, Flipside).

---

## 1. Going first vs going second

**Principles**
- The first player cannot draw or attack on turn 1. Opening hands are 5 cards going first and 6 going second (Konami beginner guide; Inexorably, *Dice Theory*).
- Combo decks that can build a multi-interruption board through 1–2 hand traps choose to go first. At the top level that has been the default for most of the modern era. Players go second by choice mainly with decks built for it: high-ceiling OTK or breaker decks such as Sky Striker (Konami's LD26 Sky Striker guide describes 8000 damage in one Battle Phase), or when the opponent's deck is far stronger on the play.
- The Cardmarket "Prevent a board or break it" framework (Atlus, 2020) still applies. Going second, you either stop the board from forming (hand traps) or let it form and dismantle it (breakers). Modern hand traps rarely end turn 1 outright. Their job is to leave "a board the rest of your cards can handle".
- Current TCG writers say a top deck needs "a strong plan going both first and second". Choose based on the matchup, not a fixed rule (TCGplayer meta coverage, 2026).

**Implications for an AI pilot**
- Make turn order a decision variable. Estimate P(win | first) and P(win | second) for each deck pair by simulation, rather than hard-coding "always first".
- Use separate policies or evaluation weights for the play and the draw. Going first, the objective is to maximize disruption the opponent must get through. Going second, it is to maximize the chance of breaking the board and then winning or out-resourcing.

## 2. Hand trap usage

**General timing**
- **Hit the chokepoint, not the first activation.** The chokepoint is the card or effect the combo must pass through, with no alternate route. Experienced players warn that the first activation is often a bait: a starter that is cheap to lose, played so you spend Ash on it (Dueling Nexus hand trap guide; Master Duel community threads on Drytron Alpha).
- Going second, "stop the opponent from playing" effects such as Mulcharmies and Nibiru often beat single-effect negates when the opponent has many routes (MDM Branded/Labrynth list notes).

**Card-specific rules of thumb** (card text verified; tactics sourced or marked)
- **Ash Blossom.** Negates effects that add from Deck to hand, Special Summon from Deck, or send from Deck to GY. Drawing counts as adding from the Deck, so Ash also stops Maxx "C" and the Mulcharmies; an MDM list note calls Ash the protection against "getting Maxx C'ed". It is weak when topdecked against an established board, because it cannot touch on-field negates.
- **Infinite Impermanence.** Can be activated from hand only if you control no cards. It targets a face-up monster, so it works on the payoff or negater, not just the starter, and it stays live on your own turn as a breaker. Set Imperm also negates S/T in its column. The rule of thumb: don't activate Spells in the column of an opponent's set card (MapleBlade, *Rule-of-Thumb*). Community advice: you can chain-block Ash but not Imperm.
- **Effect Veiler.** Works only in the opponent's Main Phase and only on a face-up monster. Play around it by activating effects in Standby or Battle Phase where possible (MapleBlade), or by using GY/hand effects it cannot reach. [synthesis] Veiler a monster that has several remaining activations that turn.
- **Ghost Ogre & Snow Rabbit.** Destroys a field monster or face-up S/T that activates, without negating it. [synthesis] It is best against continuous cards and field spells, and poor against cards that trigger on leaving the field.
- **Droll & Lock Bird** (Semi-Limited). Triggers after a non-Draw-Phase add from the Deck, then stops all further Deck-to-hand adds for both players that turn. [synthesis] Fire it after the first search when the opponent's plan needs a second search. Never fire it on your own turn if you still need to search.
- **Mulcharmies** (Fuwalos: Special Summons from Deck/ED; Purulia: Normal or Special Summons from hand; Meowls: Special Summons from GY or banishment). Each requires that **you control no cards**, and you can activate only one per turn. At the End Phase you must shuffle your hand down to the opponent's card count +6. Activating early, before the Main Phase, applies to every summon and is used "to force the opponent to stop". Chaining to a summon is a draw-maximizing play with a weaker hand (community analysis of Maxx "C" timing). [synthesis] Activating in Standby forces the opponent to answer with Ash before the combo starts, which uses up Ash before your other hand traps. Pick the Mulcharmy whose summon type matches the opponent's engine.
- **Nibiru.** Usable once the opponent has Normal or Special Summoned 5+ monsters this turn. It tributes every face-up monster and gives you a token. To play around it, "summon a negation before the fifth summon, or summon fewer than five times" (MapleBlade; Atlus). [synthesis] As the Nibiru holder, fire it after the opponent has spent negates or committed key materials, not at the first legal moment, provided no omni-negate is up yet.
- **Dominus Impulse / Purge** (traps usable from hand if the opponent controls a card). These negate Special-Summoning and search effects respectively. Using one from hand **permanently** bans three monster Attributes for you, so whether it is playable depends on your own deck. They don't trigger Triple Tactics Talent because they aren't monster effects (Arcknight, YGOrg, 2025).

**Which hand trap first** [synthesis, consistent with the sources above]
1. Turn-wide effects (Mulcharmy) come first, at Standby or before the Main Phase, because their value grows with time remaining.
2. Ash and Droll go on the search starter or chokepoint. They become dead once the board exists.
3. Imperm and Veiler go on the payoff or negater, or are held. Imperm stays live into your own turn.
4. Nibiru goes last, after the 5th summon and ideally after the opponent has spent protection.
5. If the opponent may hold Called by the Grave or Crossout, lead with the less important hand trap to draw it out.

**Implications for an AI pilot**
- Model hand traps as response options at every priority window, with phase and condition constraints: Veiler only in the opponent's Main Phase, the "control no cards" checks, and Nibiru's per-turn summon counter.
- Value an activation by the opponent's best continuation, not the immediate effect. That requires search over the opponent's line, or a learned model of their remaining routes, to tell a chokepoint from bait.
- Track once-per-turn and Mulcharmy exclusivity. Apply the End Phase hand cap in the evaluation.

## 3. Playing first into hand traps

**Principles**
- Make non-committal plays first: searches and draws before summons (MDM community notes). Lead with the effect whose negation costs you the least, so the opponent has to choose between spending a hand trap on bait and letting it resolve.
- Bait with redundant starters before the irreplaceable one. Deck guides routinely suggest baiting hand traps with weaker archetype cards before the full combo (Blue-Eyes Primite and Live☆Twin guides).
- Against Nibiru, have a monster negate up by the 4th or 5th summon (Atlus; MapleBlade). Against Veiler and Imperm, use effects outside the Main Phase or from GY or hand where you can. Keep Spells out of columns with set opponent cards.
- Against a resolved Mulcharmy or Maxx "C", either Ash it, end on a smaller board, or take a known count of "gives" (draws for the opponent) and weigh their extra cards against your board. [synthesis] The End Phase +6 cap means a large give is partly clawed back if your final card count is high.

**Resilient vs maximal board** [synthesis, supported by deck guides]
- Stop comboing once the extra board pieces add less than they expose. Each extra summon can feed Fuwalos or Purulia, move toward Nibiru's threshold, or spend resources you need for turn 3.
- Prefer a board with interruptions spread across card types (monster negate + set trap + hand trap held) to a board stacked in one zone that a single breaker answers.

**Implications for an AI pilot**
- Search over action order, not just the action set. The same cards in a different order give different expected boards under hand-trap interference.
- Evaluate a board as an expectation over the opponent's likely hand-trap holdings, which needs a prior over the opponent's deck. Include a "stop here" action.
- Penalize extra summons in the evaluation while Mulcharmy draw effects or Nibiru are live.

## 4. Going second: board breakers

**Card-by-card** (text verified; tactics sourced or marked)
- **Forbidden Droplet** (Quick-Play). Send N cards to negate N monsters and halve their ATK. The opponent can't respond with cards of the same original types as the cards sent. [synthesis] Send one Monster, one Spell and one Trap to shut off all three response types. The ATK halving often turns a negate into lethal.
- **Dark Ruler No More** (Normal Spell). Negates all face-up opponent monsters, and no monster effects can respond. **The opponent takes no damage for the rest of the turn**, so DRNM breaks the board but cannot also OTK that turn. Effects come back next turn, so the board still needs clearing (Atlus). Pairs well with Evenly Matched (Arcknight).
- **Evenly Matched** (Trap, usable from hand if you control no cards). At the end of the Battle Phase, the opponent banishes face-down down to your card count, and they choose what to keep. Standard sequencing: go to the Battle Phase with few cards on field, activate at the end, then use Normal Summon and plays in Main Phase 2 (TCGplayer Side Deck Theory). It can be negated, and it uses up your Battle Phase (Atlus).
- **Lightning Storm.** Requires that you control no face-up cards. Choose to destroy all ATK-position monsters or all S/T. It must be one of your first actions. Defense-position negaters dodge it (MapleBlade).
- **Harpie's Feather Duster** (Limited). Destroys all opponent S/T, but set cards can chain in response. Kaiju, Lava Golem and Sphere Mode remove by tribute at the cost of your Normal Summon or tempo (Atlus).
- **Triple Tactics Talent** (Limited). Live only if the opponent has activated a monster effect during your Main Phase. Bait the omni-negate first, then steal the negater, hand-rip, or draw 2.
- **Triple Tactics Thrust.** If the opponent activated a monster effect this turn, add a Normal Spell or Trap from Deck to hand (when they control a monster), for example DRNM, or set one. Often reached after the opponent hand-traps you.
- **Super Polymerization.** Discard 1 to fuse using monsters from both fields, and nothing can respond. Removes 1–2 monsters, but its value depends on a fitting Fusion in your Extra Deck (Atlus).

**Sequencing through negates**
- Lead with the least important threat or a "must-answer" bait to draw out the omni-negate, then play the real breaker. Talent and Thrust reward this naturally.
- Prefer breakers that can't be responded to (Super Poly, DRNM against monster negates, Droplet with type lockout) against boards with omni-negates, and spend them on the negater before your combo starts.
- Order by condition first: "control no cards" or "no face-up cards" effects (Lightning Storm, Imperm and Evenly from hand, Mulcharmies) have to go before you place anything.

**OTK vs grind** [synthesis]
- Go for the OTK when the opponent's remaining interaction after the breakers can't stop lethal, and their hand (a known count) is unlikely to hold the out.
- Grind when lethal isn't available or DRNM was the breaker. Then build the board that survives their next turn, since the first player will have untapped resources plus a draw.
- A top TCG writer prefers board breakers to an extra hand trap as the 6th card, and suggests holding several "pushes" so you can get through weaker interruptions going second (TCGplayer YCS Columbus tech article). The usual consensus answer is a meta-dependent mix of both.

**Implications for an AI pilot**
- Represent which effect types each opponent interruption can respond to (monster, spell, trap, targeted or not, destroy or banish or negate). The value of a breaker comes from that interaction.
- Search must include the opponent's responses at every window, and DRNM's no-damage clause has to feed the lethal calculator.
- Evaluate "board broken + lethal" vs "board broken + strong turn-3 position" as distinct terminal values.

## 5. End-board construction

**Principles** (mainly synthesis; supported by deck guides and the Atlus and Kachmarik articles)
- **Interruption count** is the first-order metric. The format is shaped by playing through "~2 pieces of interaction" (Kachmarik), so a board's practical value roughly equals its interruptions **after** the likely 1–2 hand traps or breakers.
- **Quality varies by type:**
  - Omni-negates (any card type) are worth more than type-restricted negates. Negates are worth more than "destroy" effects. Quick-effect monster negates are weaker against DRNM or Droplet. Set Counter Traps beat monster-based breakers. A Duelist's Advance article calls an omni-negate Counter Trap the best protection against breakers.
  - Diversity across zones and types (monster, set trap, hand trap kept) means no single breaker clears everything.
- **Floodgates** that stop the opponent's engine outright can be worth more than several negates in the matchup they hit. Floodgates are strongest when going first (TheGamer trap ranking).
- **Follow-up:** GY or banished recursion and "when this leaves the field" effects keep value after a board wipe and decide the grind.
- **Position:** defense position dodges Lightning Storm, ATK-based removal and ARK. Avoid placing in Extra Monster Zone columns that removal can target (MapleBlade).

**Implications for an AI pilot**
- The board evaluator needs features for: interruption count by response type, which breaker types each interruption stops (Droplet, DRNM, Evenly, Lightning Storm, Harpie's, Super Poly, Kaiju), floodgate coverage against the opponent's engine, recursion value, and position.
- [synthesis] A strong proxy: run simulated opponent turn-2 rollouts with sampled 6-card hands from a meta prior, and score P(board survives with ≥1 interruption).

## 6. Resource game, card advantage, tempo, life points

**Principles**
- Card advantage is a crude ledger of +1s and −1s. Experienced writers call it necessary but limited, because cards differ greatly in value (YGOPRODeck card advantage articles; *Philosophy of Greed*, goatformat).
- Tempo, the pace of exchanges, matters a lot. Spending cards to build a board or stop a key combo is often correct (YGOPRODeck).
- Combo decks win by generating overwhelming power in a few turns. If they don't, decks with steady "linear" power out-grind them. Resources have threshold value: being 1 card short and 10 cards short can both lose (Inexorably, *Dice Theory*).
- Life points are a resource. [synthesis] LP matter only relative to the opponent's lethal threshold. Taking hits to keep cards is usually right until the opponent can plausibly OTK you from their current resources.
- A game turns into a grind when both players have used their main engines and breakers and neither board creates lethal next turn. From then on, recursion, searchable resources, and non-once-per-turn effects decide it [synthesis].

**Implications for an AI pilot**
- The evaluation function should weight usable resources (searchable starters, GY recursion, live hand traps, Normal Summon availability) above raw card count.
- Model LP non-linearly, with a steep cost when LP falls below the opponent's estimated burst damage.

## 7. Battle Phase principles

**Principles**
- **Evenly Matched timing:** it fires at the end of the Battle Phase. As the attacker going second, enter the Battle Phase with as few cards on field as practical. Keep Normal Summon and set plays for Main Phase 2 (TCGplayer Side Deck Theory). As the defender facing a possible Evenly, use Quick effects and set cards before it resolves, since banished face-down cards are gone [synthesis].
- **Attacking into set cards** [synthesis]: attack with the monster you can most afford to lose first. Keep negates or quick effects up during battle. Consider effects that are only live in the Battle Phase (Veiler can't be used there).
- **Lethal check** [synthesis]: before committing, compute damage over every attack order, against every known or possible opponent response (Battle Phase hand traps, set traps, effects that negate or redirect attacks). Account for "no damage" effects such as DRNM. If lethal fails against a plausible response, compare the board after a failed lethal with the board after a conservative line.

**Implications for an AI pilot**
- Battle has to be modeled step by step (attack declaration, damage step, end of Battle Phase), with response windows, because Evenly Matched, Gorz-like cards and Battle Phase hand traps attach to specific windows.
- Lethal search should be an exhaustive sub-search over attack orders and targets, robust to likely opponent responses (minimax over sampled hidden information).

## 8. Side decking in best-of-3

**Principles**
- In games 2 and 3, the loser of the previous duel chooses turn order (Yugipedia). Most first-player decks choose to go first again. Plan the side deck around "I'm on the play after winning G1, on the draw after losing" only if the opponent's choice is predictable [synthesis].
- **Side differently on the play and on the draw.** Going first, bring in floodgates and protection (anti-hand-trap cards, Called by the Grave or Crossout, Thrust-style tools). Cut dead-on-the-play cards such as Evenly Matched and DRNM. Going second, bring in breakers (Droplet, DRNM, Lightning Storm, Harpie's, Evenly, Super Poly, Kaiju) and more hand traps, and cut floodgates and slow cards (deck profile examples on YGOPRODeck; Ryan Atlus; TheGamer). A Blue-Eyes profile, for example, swaps Ash for Thrust cards going second.
- Use cards that hit many matchups, such as S/T removal, generic floodgates, and "go second" cards. Don't side when a matchup is already good. Aim for about 15 tested side cards, and check that heavy siding (around 9 in) doesn't dilute your engine (PRL, YGOPRODeck *Sidedecking basics*).

**Implications for an AI pilot**
- Treat siding as an optimization problem: for each (matchup, turn order) cell, choose a main deck from main + side that maximizes simulated win rate. Keep a separate list for the play and the draw.
- After game 1, update beliefs about the opponent's deck and side (cards seen) and re-optimize. Have the pilot predict the opponent's turn-order choice when picking a side configuration.

---

## Sources

- Ryan Atlus, "Going Second: Prevent a Board or Break It," Cardmarket Insight, 2020-06-04: https://insight.cardmarket.com/en/Insight/Articles/Going-Second-Prevent-a-Board-or-Break-It
- Carter Kachmarik, "A Review of the September 2026 Yu-Gi-Oh! Banlist," Flipside Gaming, 2026-09-23: https://flipsidegaming.com/blogs/yu-gi-oh-articles/a-review-of-the-september-2026-yu-gi-oh-banlist
- Arcknight, "How to Outsmart the 'Justice Hunters' Meta?", YGOrganization, 2025-04-06: https://ygorganization.com/how-to-outsmart-the-justice-hunters-meta
- Inexorably, "Dice Theory and Branch Theory," YGOrganization, 2014: https://ygorganization.com/dicetheory
- MapleBlade, "Rule-of-Thumb: Cards that Change the Way we Play," YGOPRODeck: https://ygoprodeck.com/article/rule-of-thumb-cards-that-change-the-way-we-play-135655
- PRL, "Sidedecking basics: 3 rules that apply to every format," YGOPRODeck: https://ygoprodeck.com/article/sidedecking-basics-3-rules-that-apply-to-every-format-30590
- "Side deck theory: oppressive v reactive," YGOPRODeck: https://ygoprodeck.com/article/side-deck-theory-oppressive-v-reactive-15416
- Keebsters, "The Evolution of Handtraps," YGOPRODeck (~2018): https://ygoprodeck.com/article/the-evolution-of-handtraps-25775
- YGOPRODeck card advantage articles: https://ygoprodeck.com/card-advantage-part-one-basics/ and https://ygoprodeck.com/card-advantage-the-most-useful-tool-for-evaluating-cards-and-why-you-can-never-use-it/
- "The Philosophy of Greed," Goat Format: https://beta.goatformat.com/articles/the-philosophy-of-greed
- TCGplayer, "Side Deck Theory: Evenly Matched Levels The Playing Field" (via search excerpt): https://www.tcgplayer.com/content/article/Side-Deck-Theory-Evenly-Matched-Levels-The-Playing-Field/3cee6260-c27f-4031-8c9f-816a115fd823/
- TCGplayer, "The Best Tech Yu-Gi-Oh Cards for YCS Columbus" (via search excerpt): https://www.tcgplayer.com/content/article/The-Best-Tech-Yu-Gi-Oh-Cards-for-YCS-Columbus/2e9ed929-65d7-4e9e-bbe6-0cae5e3113cc/
- TCGplayer, "The Best Advanced Decks in Yu-Gi-Oh Right Now (September 2026)": https://www.tcgplayer.com/content/article/The-Best-Advanced-Decks-in-Yu-Gi-Oh-Right-Now-September-2026/948e13fa-57fd-4839-a15f-04564a63704c/
- Konami, LD26 Sky Striker guide: https://www.yugioh-card.com/eu/ld26-sky-striker-guide/ ; Beginner's Guide PDF: https://img.yugioh-card.com/eu/wp-content/uploads/2022/07/EN-YS17-Beginner-Guide.pdf
- TCG Forbidden & Limited list (2026-09-21), via https://ygo-decklab.com/en/banlist-yugioh and https://www.db.yugioh-card.com/yugiohdb/forbidden_limited.action
- Dueling Nexus, hand trap guide: https://duelingnexus.com/blog/yugioh-hand-traps/
- GameFAQs thread on Drytron chokepoints: https://gamefaqs.gamespot.com/boards/326292-yu-gi-oh-master-duel/79995811
- Master Duel Meta tournament deck notes (Branded, Labrynth, Live☆Twin, Yummy): https://www.masterduelmeta.com/top-decks/master-i/september-2025/branded/pearls/pZLst
- Moegirl wiki on Maxx "C" activation timing (community analysis): https://mzh.moegirl.org.cn/en/%E5%A2%9E%E6%AE%96%E7%9A%84Z
- Yugipedia, "Duel" (match turn-order rule): https://yugipedia.com/wiki/Duel
- TheGamer, trap-type ranking (floodgates strongest going first): https://www.thegamer.com/yu-gi-oh-tcg-every-trap-type-ranked/
- Card texts: YGOPRODeck API, https://db.ygoprodeck.com/api/v7/cardinfo.php

Source caveat: TCGplayer article pages render client-side and could not be fetched in full, so claims from them come from search-result excerpts. No rigorous 2025–26 first/second win-rate dataset was found.
