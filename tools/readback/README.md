# Engine readback

The probe calls the installed ModernUO `Server.TileMatrix.GetLandTile` and the unmodified ClassicUO `MapLoader.LoadMap`, `GetIndex` and `Read<MapBlock>` path used by the game client. It opens the same generated profile in both and compares every coordinate with `terrain.json`. It also checks which resource each engine selected. A private `portrait/` directory, when present, is opened through ClassicUO's `GumpsLoader.GetGump` and its complete RGBA image is compared with the converter's reference pixel hash.

Run these from the repository root in PowerShell. The first command provisions ClassicUO's pinned dependencies once. Subsequent builds use the E: package cache offline.

```powershell
.\tools\readback\build.ps1 -Provision
.\tools\readback\build.ps1
py -3.13 -B tools\readback\smoke.py
py -3.13 -B -m tools.readback.check_portrait
& E:\UltimaOffline\Tools\dotnet\dotnet.exe E:\UltimaOffline\Cache\Readback\bin\Readback.dll <generated-profile>
```

Pass the directory containing `terrain.json`, `map0.mul`, `staidx0.mul` and `statics0.mul` as the profile. The output is JSON, with exit code zero for a match. The synthetic smoke test exercises a 16×24 asymmetric map with signed heights, a conflicting UOP that ClassicUO selects ahead of the generated MUL, and a 1,025-entry statics block that would exceed ClassicUO's cap. The optional Exult source oracle compares frame 0 of `FACES.VGA` slot 12 with the palette indices decoded by `shp2pcx`.

The standalone portrait index uses Gump slot 12. It belongs only to this proof and must stay separate from the player's UO artwork. The matching Usecode call was checked against Kitrinx's disassembler, Exult's BG intrinsic table, and the reconstructed Black Gate conversation manager. [ClassicUO map loader](https://github.com/ClassicUO/ClassicUO/blob/ee79d7ebc1cc0e53ff84fe6cae17d389e2737f93/src/ClassicUO.Assets/MapLoader.cs) · [ClassicUO Gump loader](https://github.com/ClassicUO/ClassicUO/blob/ee79d7ebc1cc0e53ff84fe6cae17d389e2737f93/src/ClassicUO.Assets/GumpsLoader.cs) · [ModernUO TileMatrix](https://github.com/modernuo/ModernUO/blob/1c63a13b23ef53cab18032d19d870d13b2a85f4a/Projects/Server/TileMatrix/TileMatrix.cs) · [Black Gate conversation manager](https://github.com/Kitrinx/Ultima7_Decomp/blob/872a613c718abf3a40cf94533887171bec8cfb24/decompiled/Black%20Gate/U7/main/convmgr.c)
