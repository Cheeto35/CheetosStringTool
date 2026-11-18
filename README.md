# String Builder

Made By Cheeto.

A Tavern launcher addon for making A Township Tale **strings**: the long lists of numbers that spawn items in combinations the game normally won't let you build. Think a greatsword blade on a stake, a pouch on a sword, or a bag full of potions.

You don't have to edit any code. Pick a base item, pick a slot, attach something, choose a metal, and repeat. Every item, slot and material shows its real name, and a 2D drawing shows what you're building as you go.

## What you need

- The Tavern launcher (client), with TavernKeeper.
- Console access to the server you want to spawn on (the console token).

## Install

1. Download `string_builder-1.0.0.zip` from the releases page.
2. Unzip it into the launcher's `addons` folder, so you end up with `addons/string_builder/client.py`.
3. Open the launcher, open **Addons**, and tick **String Builder**.
4. Open TavernKeeper and connect to your server. A **String Builder** tab appears after Macros.

## Using it

| | |
|---|---|
| **Items** (left) | Type to search. Double-click an item to start a new string with it, or to put it in the selected slot. Tick "Only items that fit" to see what normally goes in that slot. You can attach anything anywhere; that's what strings are for. |
| **Parts** (middle) | Everything in your string, with each slot and what's in it. Empty slots show as ○. Select a part to change its material or scale, or to remove it. |
| **2D view** (right) | A drawing of the item at real size. Click a part to select it, or click an empty slot marker (dashed circle) to fill it. Auto picks the clearest view; Side, Front, Top and Back are there too. Scroll to zoom. |
| **Spawn preview** | Spawns the string in front of the target player. |
| **Clear preview** | Removes everything Spawn preview put out, including anything still attached to it or inside it. Pieces someone has already pulled off or taken out are separate items by then, so Clear leaves those. |
| **Copy string** | Copies the string so you can share it or spawn it yourself with `spawn string <player> <string>`. |
| **Paste string** | Loads a string from your clipboard, so you can open and edit strings you already have. |
| **My strings** | The built-in collection plus your own saved strings. Search them, load one, or save what you're working on. |

## The built-in strings

The addon comes with over 200 of Cheeto's strings to load, spawn and pull apart: weapons, bags, potions, stakes and more. Please keep the credit if you share them. A few old strings that no longer work in the current game were left out.

## Notes

- **Spawn strings with `spawn string <player> <string>`, not `spawn string-raw`.** A raw spawn puts the item at the position saved inside the string, and for these strings that's the world origin, where nothing is loaded. The game then stores the item in the origin chunk's save file, and enough of them can crash the server when that chunk loads.
- Strings you load are kept exactly as they were until you change them. Changed and new strings are saved in the current game's format.
- The item data comes from game build main-1.7.2.1.42203. If a server has items the addon doesn't know, it shows a warning, and those items appear as "Unknown item #number" instead of breaking anything.
- No game models are included; the 2D view draws each part as an outline at its real size.

## Licence

MIT. See [LICENSE](LICENSE).
