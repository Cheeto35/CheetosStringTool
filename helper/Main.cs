using System.Collections.Generic;
using Alta;
using Alta.Console;
using Alta.Intelligence;
using HarmonyLib;
using MelonLoader;
using UnityEngine;

[assembly: MelonInfo(typeof(CheetosStringToolHelper.Main), "CheetosStringToolHelper", "1.0.0", "Cheeto35")]
[assembly: MelonGame("Alta", "A Township Tale")]

namespace CheetosStringToolHelper
{
    // Server side of the Cheetos String Tool. The game has no command that lists material numbers, so this adds one,
    // and the String Tool asks for it when TavernKeeper connects. Every mod's materials end up in the same table, so
    // they all show up here.
    public class Main : MelonMod
    {
        public override void OnInitializeMelon()
        {
            CommandService.CommandCollection.Collect(typeof(Main).Assembly);
            LoggerInstance.Msg("CheetosStringToolHelper 1.0.0: added the 'stringtool materials' command");
        }
    }

    public class MaterialInfo
    {
        public uint Hash { get; set; }
        public string Name { get; set; }
        // The name of the texture material it's drawn with. Mod materials are usually copies of a game one, so the
        // String Tool can borrow that one's swatch.
        public string Looks { get; set; }
    }

    [Module("stringtool", "Cheetos String Tool helper")]
    public static class Commands
    {
        [Command("materials", "List every physical material on this server, mods included, with its number")]
        public static List<MaterialInfo> Materials()
        {
            var list = new List<MaterialInfo>();
            HashedGeneralValue<PhysicalMaterial>.CheckItems();
            foreach (PhysicalMaterial m in HashedGeneralValue<PhysicalMaterial>.All)
            {
                if (m == null) continue;
                int hash = Traverse.Create(m).Field("hash").GetValue<int>();
                if (hash == 0) continue;
                Material look = Look(m);
                list.Add(new MaterialInfo { Hash = unchecked((uint)hash), Name = m.name, Looks = look != null ? look.name : "" });
            }
            list.Sort((a, b) => a.Hash.CompareTo(b.Hash));
            return list;
        }

        static Material Look(PhysicalMaterial m)
        {
            var channels = Traverse.Create(m).Field("materialChannels").GetValue<System.Collections.IEnumerable>();
            if (channels == null) return null;
            foreach (object ch in channels)
            {
                if (ch == null) continue;
                var t = Traverse.Create(ch);
                Material mat = t.Field("nonDeformingMaterial").GetValue<Material>() ?? t.Field("material").GetValue<Material>();
                if (mat != null) return mat;
            }
            return null;
        }
    }
}
