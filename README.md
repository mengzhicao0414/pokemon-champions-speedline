# Pokémon Champions 速度线

GitHub Pages 从 `main` 分支根目录发布。`usage.json` 中的单双打前十使用率来自 MunchStats 整理的游戏内 Battle Data，每天由 `build_usage.py` 更新。

配置弹窗的技能、道具及特性说明存于 `details.json`。技能与道具资料参考 [PokéAPI](https://github.com/PokeAPI/pokeapi/tree/master/data/v2/csv) 主系列数据；特性优先使用页面现有的《宝可梦冠军》游戏文本。主系列资料可能与冠军实际规则不同，具体以游戏内显示为准。需要重建说明时运行 `python build_details.py`。
