# Cheetos String Tool

Made By Cheeto.

A Tavern launcher addon for making A Township Tale **strings**: the long lists of numbers that spawn items in combinations the game normally won't let you build. Think a greatsword blade on a stake, a pouch on a sword, or a bag full of potions.

You don't have to edit any code. Pick a base item, pick a slot, attach something, choose a metal, and repeat. Every item, slot and material shows its real name, and a 2D drawing shows what you're building as you go.

## What you need

- The Tavern launcher (client), with TavernKeeper.
- Console access to the server you want to spawn on (the console token).

## Install

1. Download `CheetosStringTool-1.1.1.zip` from the releases page.
2. Unzip it into the launcher's `addons` folder, so you end up with `addons/string_builder/client.py`.
3. Open the launcher, open **Addons**, and tick **Cheetos String Tool**.
4. Open TavernKeeper and connect to your server. A **String Tool** tab appears after Macros.

## Using it

| | |
|---|---|
| **Items** (left) | Type to search. Double-click an item to start a new string with it, or to put it in the selected slot. Tick "Only items that fit" to see what normally goes in that slot. You can attach anything anywhere; that's what strings are for. |
| **Parts** (middle) | Everything in your string, with each slot and what's in it. Empty slots show as ○, and docks holding something show as ◆. Select a part to change its material or remove it. Scroll sideways to see long builds. |
| **Piece** | Crafted items like lanterns, pouches and quivers are made of pieces (bars, flaps, straps). Pick one piece, or All pieces, and choose a material to give just that piece its own look. |
| **Materials…** | Opens the item on its own, drawn large, to change its material or its pieces' materials. Hover to see each piece's name, click pieces (Ctrl-click for more), then click a material in the palette. Double-clicking a crafted item in the drawing or in Parts opens it too. |
| **Item scale** | Sizes the whole build. The game only uses the base item's scale. |
| **Holds** | Select a dock (a quiver's arrow dock, a lantern's fuel dock), then click Holds to search for what goes in it and how many, like 999 arrows. |
| **Settings** | Change what an item saves: a potion's liquid (a preset like Health Potion, or a custom mix with its own colour, look and effects, and how many sips), a dynamite fuse, durability, never despawning, how cooked food is, a firework's colour, enchantments, stats and more. Settings you don't touch keep the item's normal values, and **Normal values** puts one back. Tick *Show every setting* for the rest of what the game saves. |
| **Gift boxes** | Select a gift mail box and click Holds (or double-click the box) to write the To and From names on it and pack things inside: search for items with an amount, or put in a whole string from your strings or the clipboard, even another gift box. |
| **Attach a string to this slot** | Puts a whole string, with everything on it, into the selected slot or dock. Pick one from your strings or paste one from the clipboard. |
| **Refresh / Items** | When TavernKeeper connects, the addon reads the server's own item list, parts and dock contents, so modded items work too. Refresh reads them again. |
| **2D view** (right) | A drawing of the item at real size, each part shaped and coloured like the game's own model and material. Click a part to select it, or click an empty slot marker (dashed circle) to fill it. Auto picks the clearest view; Side, Front, Top and Back are there too. Scroll to zoom, and hold right click to move the drawing. |
| **Spawn preview** | Spawns the string in front of the target player. |
| **Clear preview** | Removes everything Spawn preview put out, including anything still attached to it or inside it. Pieces someone has already pulled off or taken out are separate items by then, so Clear leaves those. |
| **Copy string** | Copies the string so you can share it or spawn it yourself with `spawn string <player> <string>`. |
| **Paste string** | Loads a string from your clipboard, so you can open and edit strings you already have. |
| **My strings** | The built-in collection plus your own saved strings. Search them, load one, or save what you're working on. |

## Mod materials

Materials added by mods can be picked like any other material. Mod materials show which mod they come from in the materials list.

- **CrystalLeather**'s blue, green and purple crystal leathers are built in.
- **Any other mod:** put `CheetosStringToolHelper.dll` (from the releases page) in your server's `Mods` folder and restart the server. When TavernKeeper connects, the addon asks the server for every material it has, mods included, and lists them by name. The game has no command for this on its own, which is what the helper adds (`stringtool materials`).
- **Without the helper**, click **Add…** next to Material, or **Add a material…** in the Materials window, and type the material's number and a name. If a string you load uses a material the addon doesn't know, it shows as "Unknown #number"; click it to name it. Names you give are kept on your PC.

The helper only adds that one command and doesn't change anything else on the server.

## The built-in strings

The addon comes with almost 200 of my strings to load, spawn and pull apart: weapons, bags, potions, stakes and more. A few old strings that no longer work in the current game were left out.

## Notes

- **Spawn strings with `spawn string <player> <string>`, not `spawn string-raw`.** A raw spawn puts the item at the position saved inside the string, and for these strings that's the world origin, where nothing is loaded. The game then stores the item in the origin chunk's save file, and enough of them can crash the server when that chunk loads.
- Strings you load are kept exactly as they were until you change them. Changed and new strings are saved in the current game's format.
- The addon's own item data comes from game build main-1.7.2.1.42203, and it uses that until a server is connected. If a server has items the addon doesn't know, it shows a warning, and those items appear as "Unknown item #number" instead of breaking anything.
- No game models are included. The 2D view draws each part from its size and outline, coloured with small swatches of the game's materials.

## Licence

MIT. See [LICENSE](LICENSE).
