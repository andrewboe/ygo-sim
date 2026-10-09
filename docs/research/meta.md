# TCG Competitive Meta: Oct 2025 to Oct 2026 (BETB launch)

Researched 2026-10-09. Written for the deck simulator. It complements `strategy.md`, which covers general play theory.

**How to read this.** Claims come from the sources at the end. Points tagged **[data]** come from this repo's `data/tournament_meta_decks_60d.json`, which holds 957 YGOPRODeck TCG tournament lists dated 2026-07-10 to 2026-10-03. Sliced at the F&L date (2026-09-21): **184 post-ban lists**, mostly WCQ Regionals plus YCS Guayaquil; counts are mean copies per list. **[synthesis]** = my reasoning from card text (local `cards.json`), not a sourced claim.

Naming: YGOPRODeck calls the "Dark Magician Chaos Ritual" / "Chaos Ritual" decks on yugiohmeta.com **Light and Darkness Ritual (LDR / ROLAD)**.

---

## 1. Format snapshot

### Forbidden & Limited list, TCG, effective 2026-09-21
This was announced on the YCS Paris stream (YGOrganization; Flipside). I could not reach Konami's own page, and the card tables on yugiohmeta and MDM did not render.
- **Forbidden:** Kewl Tune Rotary, Dimension Shifter, Archlord Kristya, Wind-Up Hunter, Protectcode Talker, Reprodocus, Phantasmal Lord Ultimitl Bishbaalkin, PSY-Framelord Omega. A partial Yugipedia snippet also showed Archnemeses Protos moving to Forbidden. I could not verify that against another source.
- **Limited:** Elfnote Tinia, Prohibited Power Patron Portal - Terminus.
- **Semi-Limited:** Branded in High Spirits.
- **Unlimited:** Mind Master and Elder Entity Norden (both errata'd; their entry carries a "until September 28th" exception note that YGOrg did not explain), Unchained Soul of Sharvara, M-X-Saber Invoker, Wind-Up Carrier Zenmaity, Metamorphosis, Mirage of Nightmare, Premature Burial, Purrely Delicious Memory, Runick Fountain.
- Standing restrictions that matter, taken from `strategy.md`: Maxx "C" is Forbidden. Triple Tactics Talent, Harpie's Feather Duster, Called by the Grave and Crossout Designator are Limited. Droll & Lock Bird is Semi-Limited.
- **What the list did, per Flipside:** it removed Kewl Tune, the #1 deck of the summer, from contention. Elfnote "basically only lost 2 Tinia and Omega" and stays top-3. ROLAD and Mitsurugi went untouched even after ROLAD won Paris. Flipside also expects Toons (*Magnificent Maestros*, TCG **2026-11-12** per Konami EU) to have "free rein" until the next list. No date for the next list has been announced.

### Field shares
| Deck group | Pre-ban share [data] (Jul 10 to Sep 20, n=773) | Post-ban share [data] (Sep 21 to Oct 3, n=184) |
|---|---|---|
| LDR (all variants) | 22.8% | 23.9% |
| Kewl Tune | 18.8% | 0% |
| Elfnote (all) | 14.4% | 17.9% |
| Blitzclique | 4.0% | 6.5% |
| Mitsurugi (non-LDR) | 4.3% | 6.0% |
| Invoked | 4.0% | 5.4% |
| Branded | 5.8% | 4.9% |
| Power Patron / Artmage | 4.3% | 4.9% |
| Sky Striker / Radiant Typhoon | 5.8% | 4.3% |
| Maliss, Magistus/Fairy Tail, Yummy | ~2% each | ~3.3% each |
| Lunalight | 0.6% | 2.7% |

The sim's current weights match the post-ban column well. The one thing to check: yugiohmeta's "last month" tier list still counts Kewl Tune at 11%, because its window straddles the ban.

### Staple usage, post-ban [data] (share of lists running ≥1 in main / in side)
- **Mulcharmy Fuwalos** 92% main (avg 2.76). **Ash Blossom** 81% (avg 2.4). **Droll & Lock Bird** 86% (avg 1.7, the Semi-Limited cap). **Mulcharmy Purulia** 70% main plus 34% side. Fuwalos+Purulia is now the default "draw-punish" pair. Meowls is side-only (7%).
- **Situational main:** F&V 31%, Ghost Belle 29%, Dominus Impulse 27%, Harmonia 22%, Ghost Ogre 22%, Nibiru 20%, Super Poly 20%, Dominus Spark 19%; Veiler 8%, Imperm 12%.
- **Side:** Solemn Judgment 52%, Nibiru 50%, TTT 43%, Feather Duster 40%, Pot of Sloth 39%, Called 36%, Ghost Ogre 29%, Lava Golem 24%, Accusation 24%, Evenly Matched 23%, Ra Sphere 17%, Crow 16%, Mistaken Arrest 14%.
- **Implication [synthesis]:** most opening hands going second hold 1 to 2 hand traps, and the most common of them punish *any* Extra Deck summon (Fuwalos) or hand summon (Purulia) without targeting a specific chokepoint. A sim hand-trap model should treat "draw-punish" as distinct from "negate". RotK notes the same Mulcharmy effect (smaller end boards) in the OCG.

### Going first vs second
No source gives TCG first/second win-rate data for this format. Flipside describes the format as decks that win going first "through ~2 pieces of interaction". Most top decks (Elfnote, LDR, Mitsurugi, Power Patron) are built to go first. The clear go-second decks are Blitzclique (YGOPRODeck author: "pure go-second") and, to a lesser degree, Branded (Branded Fusion) and Sky Striker. Treat everything else in this paragraph as [synthesis].

---

## 2. Deck profiles

Chokepoints are [synthesis] from card text unless a source is cited.

### 2.1 Elfnote (~17%, #1)
- **Engine.** Synchro "Singer" monsters whose effects key off the **center Main Monster Zone** (MDM guide). Core counts [data]: Elfnote Lucina 3, Regina 3, Elfnote Power Patron 2.7, Medius the Pure 2.2, Vidolium the Unstable Power Patron of Unity 2.2, Elfnotes: Welcome Home 2, Tinia 1, Fortuna 1, Rhapsodia of Madness 1, Terminus 1, Junoldo 1. Variants: Angelechy (4), Synchron (3), Fiendsmith (2).
  - Lucina searches an Elfnote monster.
  - Regina, when summoned to the center zone, Special Summons an Elfnote from the Deck.
  - Elfnote Power Patron gives +3 Levels and an instant Synchro, then searches an Elfnote card when used as material.
  - Medius searches or summons a Power Patron.
  - Welcome Home summons an Elfnote from the Deck and imposes a Synchro-only Extra Deck lock.
- **Opponent-turn disruption** comes from monsters in the GY or on the field moving into the center zone: Lucina bounces a Level ≤6 monster, Tinia banishes a random card from the hand until End Phase, Fortuna bounces a face-up Spell/Trap.
- **End boards** (Master Duel lists, not TCG-verified):
  - Baronne de Fleur + Herald + Ecclesia + trap.
  - Baronne + Auxilla + a Level 12 dragon + Rhapsodia + Atrii, with Regina and Tinia summoned on the opponent's turn.
  - Extra Deck staples [data]: Crystal Wing, F.A. Dawn Dragster, Seraphim Strelitzia, June Pride, Chaos Angel.
  - RoadoftheKing reports the OCG Ars Magna build ending on about 8 disruptions: 3 negates plus 2 hand banishes.
- **Chokepoints [synthesis].**
  - Ash on **Lucina's search** or **Medius's search/summon**. Ash, Veiler or Imperm on **Regina's Deck summon**. Droll after the first search.
  - Fuwalos/Purulia are both live: Lucina and Tinia summon themselves from the hand, and the deck makes many Synchro summons. MDM calls the deck "awkward" against Fuwa/Maxx C.
  - The deck plays through Ash/Imperm better than most, thanks to Loading... and starter redundancy.
  - It is weak to center-zone denial (Orcust tokens, zone locks) and to Nibiru (1.5 copies in the average side).
- **Tech [data].** Main: Ash 2.5 (including alt-art printings), Harmonia 2.3, Ghost Belle 1.8, Droll 1.4, Ghost Ogre 0.9, Nibiru 0.7, Called 0.5. Side: Nibiru 1.5, Ghost Ogre, Lava Golem, Sloth, Judgment, Crow, Mistaken Arrest.
- **Matchups and turn order.** Strong going first. The MDM guide calls it weak going second because the Power Patron engine struggles into established boards. Flipside says Omega's ban "gives players more cards going second" against it.
- **Results.** Japan Championship 2026 T8. YCS Montreal (Aug 15, 755p): winner (F. Osorio) and T4, 7 in T32. YCS Paris (Sep 19, 2588p): runner-up, T4 and 2×T8. YCS Guayaquil (Oct 3, 263p): **winner** (G. Trivino), T4, 2×T8, 12 of T32. Duluth WCQ winner. NA WCQ 6 of 64. EU WCQ one T8.
- **Trajectory:** rising, and now co-#1 with LDR. The Tinia limit barely slowed it.

### 2.2 Light and Darkness Ritual / "Dark Magician Chaos Ritual" (~16%) and "Chaos Ritual" (~6%)
- **Engine.** Rituals of *Magician of Dark Chaos - Black Chaos* and *Black Luster Soldier - Soldier of Light and Darkness* through **Light and Darkness Ritual**. The Ritual Spell recurs itself plus a card that mentions it from the GY, and it can banish GY monsters as Tributes.
- **Support cards:**
  - **Griffoh** (3.0) is a discard Quick Effect that sets an LDR Quick-Play/Trap from the Deck, and it can serve as the whole Tribute for a Level 8 Ritual.
  - **Black Chaos** (2.4) discards itself to place an LDR Continuous Trap such as Mind Shuffle, and it is unaffected by opponent's activated effects while a Ritual Spell is in the GY.
  - **Skull Archfiend of Chaos** (1.4), when sent to the GY, dumps a Ritual Spell and searches the Ritual monster.
  - **Ragged Records of Rites** (2.5) is a searcher.
  - **Pre-Preparation of Rites** (1.4).
- **The DM package:** Dark Magical Curtain 2.0, Magicians' Souls, Magician's Rod, Gaze of Timaeus, DM the Pharaoh's Servant. It feeds **Dark Magician of Destruction** (77%) and Red-Eyes Dark Dragoon (68%).
- **Common side engines:**
  - Azamina/Sinful Spoils: WANTED 2.0, Diabellstar 1.8, The Hallowed Azamina.
  - Mitsurugi: Prayers 1.8, Ritual, Mirror, Aramasa, Saji, Murakumo, Habakiri, each about 0.6.
  - Branded (7 lists).
- **Interaction and Links.** Main-deck **Dominus Impulse** 1.8 and **Dominus Spark** 1.2. Links [data]: S:P Little Knight 86%, Contract Witch, Charmer Quartet, Selene, Zenna's Doll Maidens. Protectcode Talker (Paris winner) is now banned.
- **Typical board** (YGOPRODeck community breakdown; not a TCG tournament source): Magician of Dark Chaos (protected, banishes face-down) + Dark Magician of Destruction + a set Mind Shuffle/Quick-Play from Griffoh + Dominus traps in hand.
- **Chokepoints [synthesis].**
  - Ash hits Ragged Records, Skull Archfiend's search, Curtain, Diabellstar/WANTED and Mitsurugi searches. It does *not* hit Griffoh's set or Black Chaos's place.
  - Once Magician of Dark Chaos or Black Chaos is protected, only targeting removal (or non-activated removal) works, so interrupt early.
  - GY-based hand traps (Ghost Belle, D.D. Crow, Bystials) hit LDR's GY recursion and Skull Archfiend.
  - Fuwalos punishes the DM Fusion and Link turns.
  - **Dominus Impulse from the hand** shuts off the owner's own LIGHT/EARTH/WIND monster effects. That is an engine constraint the sim must model.
- **Tech [data].** Main: Fuwalos 3.0, Purulia 2.6, Ash 2.3, Droll 1.9, Kuriboh - Multiply! 1.5, Harmonia 0.6, F&V 0.6, Nibiru 0.5. Side: Nibiru 1.7, Sloth 1.5, **Lava Golem 0.9**, TTT, Spark, Ra Sphere Mode, Mitsurugi singles. TCG Corner says LDR and Mitsurugi players are already siding **The Great Gallant Bandit** (BETB).
- **Matchups and turn order.** No source covers specific matchups. It plays as a first-turn control deck, but its Dominus/Kuriboh suite also works going second [synthesis].
- **Results.** NA WCQ (Jul 11) 12 of 64. EU WCQ 13 of 64. YCS Montreal 3×T8 (9 of T32). **YCS Paris winner** (Vladis Baranovskis, DM build with Mitsurugi/Azamina), 11 of 64. YCS Guayaquil runner-up (Franco Persano, Azamina Mitsurugi DM) plus 2×T8, 10 of T32. Kissimmee WCQ winner (LDR Branded Elfnote).
- **Trajectory:** stable at #1–2. BETB gives it **Black Skull Dragon, the Archfiend of Unity** (sets an LDR Spell/Trap on summon) and **Spell Shattering Sword** (usually 1 copy each, per TCG Corner and RotK).
- **"Chaos Ritual" vs "DM Chaos Ritual".** These are the same engine without the DM package, built on Azamina, Branded, Mitsurugi or Fiendsmith instead. In the OCG (RotK, Jul 18 to Aug 2) LDR had 20 of 145 top decks across variants: DM 6, Clown Crew 4, Dogmatika 3, Azamina 2, Fallen 2. Clown Crew LDR (BETB-EN099 *Clown Crew Cappello*) is the OCG shell to watch.

### 2.3 Sky Striker / Radiant Typhoon (~10%)
- **Engine [data].** Engage! 2.6, Radiant Typhoon Vision 2.6, Raye 2.2, Linkage! 2.2, Widow Anchor 2.2, Lemnisgate 1.5, Roze 1.4, Pot of Desires 1.6, Upstart Goblin 1.1, F&V 2.5. Extra Deck: the Sky Striker Links plus Albion/Ecclesia via F&V.
- **Plan.** A spell-based grind deck: Raye goes into a Link, and Quick-Play spells give interaction on either turn.
- **Chokepoints [synthesis].** Ash on Engage! (search) or Linkage!. Called/Crow on GY effects. Fuwalos only matters on Link turns. Solemn Judgment and Spell counters hurt it, and so does Anti-Spell-type floodgates.
- **Tech [data].** Ash 2.2, Droll 2.0, Ghost Ogre 1.4, Fuwalos 1.1, MST 0.9, Forbidden Crown 0.9, Called 1.0. Side: Fuwalos, Accusation, Evenly Matched, Ra Sphere.
- **Turn order.** Flexible. It is the most going-second-viable of the top decks [synthesis].
- **Results.** YCS Sydney (Feb 28, 746p): **winner** (Radiant Typhoon, D. Italiano) plus a T8. YCS Columbus (May 23–24, 1618p): Radiant Typhoon Sky Striker T8. **NA WCQ 2026 winner** (Ryan Yu). Catskill WCQ T4 (Sep). Post-ban [data]: 1 winner, 3×T4, 4×T8.
- **Trajectory:** steady tier 1.5. BETB adds Swiftwind Panther Warrior / Dark Time Wizard, which pair with the Radiant Typhoon engine (TCG Corner).

### 2.4 Blitzclique (~8%)
- **Engine.** EARTH Thunder monsters that destroy a card and then Special Summon from the hand. Counts [data]: Surge, Crackle, Whisker, Breakaway at 3; Grain 2.9; Coulomb 2.9; Alternator 2; Emi 1; Steppleader 0.9; Pot of Extravagance 1.7; Pot of Prosperity 0.7.
  - Surge: reveal → destroy a monster → SS a Thunder; searches a Blitzclique when a card is destroyed.
  - Grain: the same for Spells/Traps, and it searches a Spell or Coulomb.
  - Crackle: an opponent's-turn reveal that destroys an activating monster.
  - Whisker: the boss. It summons up to 3 Thunders from the hand and destroys that many cards, and it has a negate.
  - Coulomb: gives the opponent a token to search.
  - Lock: only Effect monsters from the hand may be Special Summoned.
- **Plan.** A dedicated **go-second** breaker deck (YGOPRODeck author). Extra Deck: Albion 100%, Dogma Dragon 91%, Malong, TY-PHON Sky Crisis, Ecclesia (via F&V 2.8).
- **Chokepoints [synthesis].** Ash on Surge's/Grain's/Coulomb's search. The reveal effects are activations in the hand, so Imperm cannot hit them. Fuwalos does little because summons come from the hand. **Purulia** is much better against it. Its turn-1 board is thin, so going first against it is preferable.
- **Tech [data].** Fuwalos 2.8, Droll 1.7, Ash 1.6, Harmonia 1.2, Dominus Purge 1.2, Purulia 1.1. Side: **Lava Golem 2.0**, Sloth 1.8, Purulia, Dimensional Fissure, Return Stroke, Thunder King Rai-Oh. BETB adds **Blitzclique Overvolt** and Gallant Bandit as a breaker (author's list).
- **Results.** Genesys-format WCQ tops in NA/EU/OCE; that is a separate format. Advanced format: Guayaquil T4 and T32, Bundaberg WCQ winner, Folkestone T4 (Branded Blitzclique). Post-ban [data]: 3 winners, 2 runner-ups.
- **Trajectory:** rising. It gains from Kewl Tune leaving and from the breaker-heavy BETB environment.

### 2.5 Invoked (~6%)
- **Engine [data].** Aleister the Reminiscent 3, Aleister the Invoker 2.9, Aiwass, Divine Spirit of the Law 2.9, Sacred Spirit Sword Aiwass 2.7, Magical Meltdown 2.9, Invocation - "Sword" 2.6, Invocation 2.1, Super Poly 1.8.
- **Pieces.**
  - Aleister the Reminiscent banishes an Invoked to search Invocation.
  - Aiwass banishes itself to search an Aleister and grants an extra Normal Summon.
  - Magical Meltdown makes Fusion activations unnegatable, and the opponent cannot respond to those Fusion Summons.
- **Chokepoints [synthesis].** Ash on Aiwass's or Aleister's search. Once Meltdown resolves, chain-negation of Fusions is off, so interaction has to land before Meltdown or on the searches. Fuwalos draws still apply because they are not activations. GY hate (Crow, Bystials, Ghost Belle) hits Aiwass and Invocation recursion.
- **Tech [data].** Fuwalos 2.7, Ash 2.7, Purulia 2.1, Droll 1.8, Ghost Belle 1.2, Called 0.9, Nibiru 0.8. Side: Ghost Ogre 1.4, Nibiru, Accusation, D.D. Crow.
- **Results.** EU WCQ T8 (D. Siracusa). Paris and Montreal T32. Post-ban [data]: **4 winners**, 1 runner-up, 1×T4, 4×T8. That is the best conversion rate in the post-ban sample.
- **BETB.** **Invoked De Anima** (on summon, wipes the opponent's Extra-Deck monsters or their Spells/Traps; negates GY effects) and **Invocation - "Grail"** (can use an opponent's monster as material). OCG impact unconfirmed (1 Invoked top in RotK sample).

### 2.6 Magistus Invoked Fairy Tail (~5%)
- **Engine [data].** Fairy Tail - Luna 3 (on Normal Summon, searches an 1850-ATK Spellcaster; Quick Effect bounce), Regulus 2.5, Spenta 2.3, Aleister the Reminiscent 2.3, Fairy Tail Ball 2.2, Verre Magic - Lacrima 2.2, Matchgiru 1.7, Super Poly 1.7, Crowley/Zoroa/Endymion Empire 1.
- **Plan.** MD players say it plays through half boards and OTKs via the field spell; it bricks without Crowley.
- **Chokepoints [synthesis].** Ash on Luna's search or Regulus's search. Fuwalos is heavy against the Magistus Link/Fusion climb.
- **Side [data].** Santa Claws 1.7, Nibiru, Sloth, Lightning Storm.
- **Results.** It was the Columbus "sleeper" that just missed T8 (YGOPRODeck). Fairy Tail T32 at Montreal. Post-ban [data]: runner-up, T4, 4×T8.

### 2.7 Mitsurugi (~5%) and Mitsurugi Yummy (~6%)
- **Engine [data, pure].** Prayers 3, Pre-Prep 3, Aramasa 2.8, Murakumo 2.7, Mitsurugi Ritual 2.3, Ragged Records 1.8, Ruler of the End of the World 2.3, plus singles of Saji, Kusanagi, Wousu, Habakiri, Futsu, Mirror, Great Purification.
  - Prayers searches and/or revives with a Reptile tribute.
  - Aramasa and Saji search when summoned *or Tributed*.
  - Mitsurugi Ritual can Ritual Summon from the Deck.
  - **Ame no Murakumo**, when Special Summoned, destroys all opposing monsters, and it has a "discard or negate" Quick Effect.
- **Mitsurugi Yummy [data].** Adds Marshmao☆Yummy 3, Lollipo/Cooky/Cupsy, Yummy Way Synchros, plus Sky Striker Engage!/Hornet Drones for Kagari/Camellia. DM Curtain 2.8 is also present, so many TCG "Mitsurugi Yummy" lists are actually **DM Mitsurugi Yummy**. MD lists end on Baronne + Murakumo + Herald + Yummy interrupts + Prayers/Purification.
- **Chokepoints [synthesis].**
  - Ash on Prayers, Aramasa/Saji, or Mitsurugi Ritual summoning from the Deck. Droll after the first search.
  - An MD author says one Prayers "can shut down the pure build" (context: Prayers to 1 in MD).
  - Pure Mitsurugi barely uses the Extra Deck on turn 1, so **Purulia beats Fuwalos** against it (Ritual Summons from the hand count).
  - Yummy plays hit Fuwalos hard.
- **Tech [data].** Pure: Fuwalos 3, **Dominus Impulse 3**, Ash 2.5, Droll 1.3, Super Poly 1.3, Purulia 1.2. Side: **Dimensional Fissure 2.3**, Purulia, Ra Sphere, Nibiru, Accusation. Yummy: Fuwalos 3, Purulia 3, Ash 2, Droll 2, Imperm 1.5, Veiler 1.3, Spark 1.3, Ghost Belle 1.3. Side: Nibiru 2.3, Accusation, Ra.
- **Results.** EU WCQ **runner-up** (pure). Columbus T8. Team YCS Las Vegas (Apr 18): Mitsurugi in the winning team and Yummy the most common T16 archetype. Guayaquil T16. Post-ban [data]: pure 2 runner-ups, 1×T4. Yummy 1×T4, 5×T8, no wins.
- **Trajectory:** stable. Flipside argued Prayers/Ritual should have been hit and was not.

### 2.8 Branded (~5%)
- **Engine [data].** F&V 3, Super Poly 2.2, Fallen of the White Dragon 2, Branded in High Spirits 2 (now Semi-Limited), Nadir Servant 2, Aluber 1.9, Branded Opening 1.9, Blazing Cartesia 1.8, Incredible Ecclesia 1.7, Branded Fusion 1. A Dracotail sub-engine (Faimena, Lukias, Urgula, Mululu, Phryxul) appears in about a third of lists. Extra Deck: the standard Branded fusion suite (Secreterion, Mirrorjade, Albion, Titaniklad, Granguignol, Rindbrumm).
- **Character.** YGOPRODeck calls it a grind deck whose engine resists hand traps, with Aluber's GY effect stopping OTKs and Branded Fusion "relevant going second".
- **Chokepoints [synthesis].** Ash on Branded Fusion (sends from the Deck) or on Aluber's/Opening searches. Crow/Belle on Fusion GY triggers (Albion, Mirrorjade). **Mistaken Arrest** (side 2.4 avg) is the deck's own tool against searchers.
- **Results.** **YCS Columbus winner** (Jesse Kotton, Branded Dracotail; Branded runner-up too). Team YCS Las Vegas runner-up team. EU WCQ 2×T4. Sydney: Dracotail 13 of T32. Since then it has slipped to about 5%. Flipside calls the High Spirits hit "out of touch".

### 2.9 Power Patron / Artmage (~4%)
- **Engine [data].** Nervedo the Shadebeast Power Patron 3 (Pendulum Effect negates an opponent's monster effect activated in response to a Power Patron/Artmage monster effect), Vidolium 2.9, Pendulum Treasure 2.7, Medius the Pure 2.1, Artmage Power Patron 1.8 (Quick-Effect Fusion), Jupredo 1.6, Artmage spells, Terminus 1 (Limited), Junoldo 1.1.
- **FTK history.** A Gustav Max FTK topped regionals early in the Blazing Dominion format (YGOrg). Terminus being Limited now targets this.
- **Chokepoints [synthesis].** Ash on Medius or Terminus (sends from the Deck). Nervedo punishes monster-effect hand traps (Ash/Veiler/Belle/Ogre) used in response to its monsters, so spell- or trap-based interaction (Droplet, Called, Dominus) is better. Fuwalos is very strong against its Fusion/Link/Pendulum volume.
- **Side [data].** Ash 2.3, Purulia 2.0, Evenly Matched 1.7, Forbidden Crown 1.1.
- **Results.** Team YCS Las Vegas winning team (Artmage, K. Rodrigues Goncalves). Paris 3 Artmage in T64. Post-ban [data]: **3 winners**, 2 runner-ups.
- **BETB (OCG-proven).** **Ars Magna** monsters, **Theorealized Medius**, **Ars Magna "Citrinitas"** (treated as Artmage/DoomZ/Elfnote; searches Medius/Ars Magna), **Philosophorum** (negates), and **Mediclius the Extraordinary Power Patron** (generic Link: mass negate; banishes all opposing cards when pointing to 3). OCG: Ars Magna Power Patron and Ars Magna Artmage both topped. Expect it to rise.

### 2.10 Lunalight (~4%)
- **Engine [data].** Gold Leo 3 (searches a Lunalight on summon, then discards), Tri-Brigade Fraktall 2.6, Fire Formation - Tenki 2.2, Masquerade 2.4, Luna Light Perfume 2, Scarlet Tiger/Black Sheep/Silver Hound 2, Kaleido Chick 1.8, Heavy Polymerization 1.6, Foolish Burial Goods 1.6.
- **Chokepoints [synthesis].** Ash on Gold Leo's search, Fraktall's send or Tenki's search. Fuwalos hits its Fusion/Xyz turn.
- **Tech [data].** Dominus Impulse 2.4, Fuwalos 3, Purulia 2.2, Droll 1.6. Side: Ash, Meowls, Droplet, Mask of Restrict.
- **Results.** Sydney 2 in T32 and some Las Vegas presence. Post-ban [data]: 1 winner, 4×T8. I found no YCS top-8 in this window.
- **Turn order:** I could not confirm whether it prefers going first or second.

### 2.11 Maliss (~2.5%)
- **Engine [data].** Chessy Cat 3 (banishes a Maliss to draw 2), March Hare 3, Backup @Ignister 3, Allure of Darkness 2.3, Maliss in Underground 2, Wizard @Ignister, Gold Sarcophagus, Terraforming, Maliss traps. It is a Cyberse Link deck with banish recursion.
- **Interaction:** Dominus Impulse 3, Spark 1.7, Imperm 2.2, Ash 2.5, Bystials.
- **Chokepoints [synthesis].** Ash on Chessy Cat's draw or Backup @Ignister. Fuwalos against the long Link chain. Its banish triggers mean banish-based hate (Fissure, Crow) can feed it rather than stop it.
- **Side [data].** Purulia 2.7, Mistaken Arrest 2.0, Nibiru 1.8.
- **Results.** Team Las Vegas (8 in T16, its peak). Arapiraca WCQ winner (Sep 27, Maliss @Ignister). Post-ban [data]: 2 winners. Small share, high conversion.

### 2.12 Important decks missing from the sim field
- **Kewl Tune.** It was #1 all summer: EU WCQ winner, NA WCQ 27 of 64, Montreal runner-up plus 10 of T32, Paris 8 of T64. **Rotary is Forbidden**, and Flipside calls it out of contention, possibly rogue. Leaving it out is correct.
- **Toon (OCG-dominant; TCG 2026-11-12).** RotK has it #1 in the OCG with 32 of 145 top decks (Jul–Aug), and Flipside says it is "functionally Tier 0". TCG legal from *Magnificent Maestros* (with Witchcrafter/Unchained support); add it in November.
- **Angelechy (Elfnote).** BETB-TCG adds 7 Angelechy cards (EN090–096). Angelechy Elfnote was already 2% on yugiohmeta. Worth tracking.
- **Artmage, DoomZ, Dracotail, Sacred Beasts, Ryzeal.** Each holds 1–3% (yugiohmeta). DoomZ was a Columbus top-3 contender but has faded.

---

## 3. Beyond the Brave (TCG 2026-10-09 street date, EN set confirmed in local `cards.json`)

The OCG got these cards on about 2026-07-18. TCG names differ from fan translations.

| Card (TCG name) | What it does | Who uses it | OCG evidence |
|---|---|---|---|
| **The Great Gallant Bandit** | Tribute Summoned using your hand and/or the *opponent's* monsters while you control none, i.e. Lava Golem-style removal. If Normal Summoned it negates GY/hand/banish effects, and it flips the opponent's monsters to Defense in the Battle Phase. | Any deck that does not need its Normal Summon: LDR, Mitsurugi, Blitzclique. **Not Toon.** | RotK: "metagame shift towards board breakers" |
| **Hey, Space Trunade!** | Non-targeting bounce of up to 2 field cards, then each player bottoms that many cards from the hand. | Side or main board breaker; works against Elfnote continuous spells and LDR traps [synthesis]. | Widely sided per RotK; answered by Anti-Spell Fragrance and Appointer/Mind Crush |
| **Ars Magna** ×3, **"Citrinitas"**, **"Philosophorum"**, **Theorealized Medius**, **Mediclius** | Power Patron Link support. Citrinitas counts as an Elfnote card, so Elfnote can fetch it (Tinia places Elfnote Continuous Spells; Power Patron searches Elfnote cards) [synthesis from text]. | Elfnote, Power Patron, Artmage | Ars Magna Elfnote is the #1 OCG Elfnote build (7 of 48 lists in local OCG 30d data; RotK 5+2 of 20) |
| **Black Skull Dragon, the Archfiend of Unity**, **Spell Shattering Sword** | LDR extenders/interaction. | LDR, as 1-ofs | TCG Corner, RotK |
| **Invoked De Anima**, **Invocation - "Grail"** | Invoked boss and Fusion spell. | Invoked, Magistus | No OCG top-cut evidence found |
| **Blitzclique Overvolt** | Recurring destruction spell. | Blitzclique | None found |
| Dark Time Wizard, Swiftwind Panther Warrior, D-HERO, Atlantis, Ashtra, Umbral Horror, Adamancipator | New or refreshed themes. | Rogue | DTW/D-HERO 1–3 OCG tops each |
| Angelechy cards, Verre, Clown Crew Cappello (TCG-exclusive extras EN082–100) | — | Angelechy Elfnote, Magistus, Clown Crew LDR | — |

**Expected TCG shifts.** These are [synthesis] built on OCG results:
1. Elfnote gets stronger through the Ars Magna and Citrinitas package.
2. Power Patron/Artmage gains a real engine.
3. Breakers move up: Gallant Bandit replaces Lava Golem, and Trunade becomes a flexible out.
4. Siding against breakers becomes a thing.
5. LDR gets marginal upgrades.

No TCG event with BETB has been reported yet; YCS Guayaquil (Oct 3) was pre-BETB.

---

## 4. Results timeline (Advanced format, last ~12 months)
| Event | Date | Size | Winner | Notes |
|---|---|---|---|---|
| NA Remote Duel YCS / YCS Bologna | Dec 2025 | — | not confirmed | Konami coverage found but I could not identify the winner's deck |
| YCS Sydney | 2026-02-28 | 746 | Radiant Typhoon | Dracotail 13 of T32 |
| Team YCS Las Vegas | 2026-04-18 | 1167 | Team Ares (Artmage) | Yummy, Maliss, Dracotail most common |
| YCS Columbus | 2026-05-23 | 1618 | Branded Dracotail (J. Kotton) | Kewl Tune most represented |
| NA WCQ | 2026-07-11 | 2060 | Sky Striker (R. Yu) | KT 27 of 64, LDR 12 |
| EU WCQ | 2026-07-11 | 2268 | Kewl Tune (T. Gräfe) | KT 16 of 64, LDR 13 |
| YCS Montreal | 2026-08-15 | 755 | Elfnote | KT 10, LDR 9, Elfnote 7 of T32 |
| YCS Paris | 2026-09-19 | 2588 | LDR / DM Chaos Ritual (V. Baranovskis) | last pre-ban event; LDR 11, Elfnote 8, KT 8 of T64 |
| YCS Guayaquil | 2026-10-03 | 263 | Elfnote (G. Trivino) | first post-ban YCS; Elfnote 12, LDR 10 of T32 |

---

## Sources
- YGOrganization, TCG Sept 2026 F&L: https://ygorganization.com/putinvokerbackpls
- Flipside Gaming, Sept 2026 banlist review: https://flipsidegaming.com/blogs/yu-gi-oh-articles/a-review-of-the-september-2026-yu-gi-oh-banlist
- Master Duel Meta, TCG F&L news (date only): https://www.masterduelmeta.com/articles/news/september-2026/tcg-forbidden-list/
- Yugioh Meta, F&L page and tier list: https://www.yugiohmeta.com/forbidden-limited-list , https://www.yugiohmeta.com/tier-list
- Yugioh Meta, YCS Paris winning list: https://www.yugiohmeta.com/top-decks/ycs-paris-2026/dark-magician-chaos-ritual/vladis-baranovskis/eB9Eg
- Yugioh Meta, Guayaquil Elfnote T8: https://www.yugiohmeta.com/top-decks/ycs-guayaquil-2026/elfnote/francisco-andres-osorio-bobadilla/zFTGE/
- Yugioh Meta, BETB OCG Medius reveal: https://www.yugiohmeta.com/articles/news/july-8-2026/BETB/
- YGOPRODeck tournaments: YCS Guayaquil https://ygoprodeck.com/tournament/ycs-guayaquil-5164 ; YCS Paris https://ygoprodeck.com/tournament/ycs-paris-5034 ; YCS Montreal https://ygoprodeck.com/tournament/ycs-montreal-4842 ; NA WCQ https://ygoprodeck.com/tournament/north-america-wcq-2026-4746 ; EU WCQ https://ygoprodeck.com/tournament/european-wcq-2026-4747 ; YCS Sydney https://ygoprodeck.com/tournament/ycs-sydney-4294 ; Team YCS Las Vegas https://ygoprodeck.com/tournament/team-ycs-las-vegas-4492
- YGOPRODeck, YCS Columbus event breakdown: https://ygoprodeck.com/article/event-breakdown-ycs-columbus-302868
- YGOPRODeck, tournament meta decks feed: https://ygoprodeck.com/category/decks/tournament-meta-decks
- YGOPRODeck decks: Guayaquil runner-up LDR https://ygoprodeck.com/deck/azamina-mitsurugi-dark-magician-light-and-darkness-ritual-736533 ; Guayaquil Mitsurugi https://ygoprodeck.com/deck/mitsurugi-736578 ; go-second Blitzclique https://ygoprodeck.com/deck/blitzclique-723758 ; LDR community breakdown https://ygoprodeck.com/deck/ritual-of-light-and-darkness-708905
- Road of the King, OCG 2026.07 metagame report (weeks 3–5): https://roadoftheking.com/ocg-2026-07-metagame-report-3-4-5/
- TCG Corner (RespectYGO), BETB impactful cards: https://tcg-corner.com/blogs/news/respectygobeyond-the-brave
- Master Duel Meta, Elfnote guide (MD, used for engine and weaknesses only): https://www.masterduelmeta.com/articles/guides/elfnote-galacticjoey/
- YGOrganization, Power Patron FTK article: https://ygorganization.com/become-the-power-patron-master-with-these-ftks/
- Konami EU, Magnificent Maestros product page: https://www.yugioh-card.com/eu/product/magnificent-maestros/
- Local data: `data/tournament_meta_decks_60d.json`, `data/tournament_meta_decks_ocg_30d.json`, `data/cards.json` (card text and BETB-EN set list)

**Not confirmed:**
- Konami's official F&L page.
- The meaning of the Sept 28 exception note.
- Late-2025 YCS winners' decks.
- TCG first/second win rates.
- Any TCG BETB-legal results.
- Specific matchup percentages: no source published TCG matchup data.
