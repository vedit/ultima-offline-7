# Credits and distribution boundaries

Ultima Offline 7 is an independent development project. Ultima VII and Ultima Online game content remains the property of its respective rights holders. Neither game is included. Players supply their own installations.

## Code dependencies

- **ClassicUO**, by its contributors: the client overlay derives from the pinned [ClassicUO source](https://github.com/ClassicUO/ClassicUO). Retain its [BSD 2-Clause notice](game/client/LICENSE.md), source headers and recursive dependency notices, including FNA, SDL, FileEmbed and MP3Sharp.
- **Kitrinx/Ultima7_Decomp**, by Jamie Blanks and the original code's authors: the native overlay uses the pinned [portable Black Gate source](https://github.com/Kitrinx/Ultima7_Decomp). Its [upstream notice](game/native/LICENSE) distinguishes pre-existing code from new original code. Do not describe the entire original game as MIT-licensed. Keep the upstream notices, libmatoya and audio dependency notices with any build.
- **Exult**, by its contributors: the atlas reads frame metadata from the separately obtained [Exult v1.12.1 source](https://github.com/exult/exult/tree/v1.12.1). Exult is not the runtime gameplay engine here. Retain its notices in that checkout.
- Python dependencies retain their own licenses; see their installed distributions. No blanket project license is being assigned over third-party work by this setup change.

## Game data and generated output

The build reads local U7 and UO data and generates a private atlas, map, art overlays and intro audio/background. These outputs still contain or derive from retail content. A successful local build is not permission to upload them.

Authored Guardian pose sources under `game/intro/art` are tracked separately from original cutscene references. They are interim AI-assisted fan artwork. Local original-game reference captures, extracted frames, vocals and generated intro assets are excluded.

## Optional music

Players can select a locally installed Exult digital music folder in the game's audio options. No recordings or MT-32 ROMs are bundled or automatically downloaded.

Credit **Simon Quinn** for his MT-32 recordings and **Exult** and its contributors, as described in the [Exult documentation](https://exult.info/docs.html). Credit the original Ultima VII composers, led by **Dana Glover**, with additional music by **Raymond Benson, Herman Miller, David Watson, Kathleen Jones and Kirk Winterrowd**; retain the full credits supplied with your game. Preserve any notices accompanying the selected recordings. Attribution does not by itself grant redistribution permission.
