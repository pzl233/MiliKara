# 定制版说明

本分支基于上游 MiliKara v1.2.0，保留原项目的 MIT 许可和版权声明。`custom` 是定制功能分支；`main` 保留上游版本，之后可在检查差异后同步。

## 片头署名

打开项目的 **卡拉OK字幕 → 歌曲信息 → 片头署名**，开启“显示片头署名”。可以填写视频制作者，选择是否显示分离模型、字幕字体；说明留空时自动读取项目分离轨的模型来源和此次渲染解析后的字幕字体（含已启用的注音 / 翻译字体），不会把全局默认模型误写成当前项目的模型，也不会列出对齐模型。

排列方式可选“多行信息卡”或“顶部单行”。展开“位置与显示时间”后，可选靠左、居中、靠右，并调节出现时间、时长、字号和边距。单行过长时自动缩小字号；署名会避让歌词与翻译，空间不足时可能提前结束或不显示。

- 出现时间从音频开头算起，范围为 0–3600 秒。
- 显示时长范围为 1–600 秒；片尾歌曲信息也支持最多 600 秒。
- “预览片头署名”会跳到署名出现后最多 1.5 秒的位置；短署名取显示区间的中间位置，并限制在音频结尾之前。按钮位于预览图下方和署名设置内。
- 署名只在片头出现；原有片尾歌曲信息不会重复显示制作署名。

**已有项目**需要在该项目内开启署名，再重新生成视频。极简模式里的“片头署名”是之后新建任务的默认值，不会追改旧项目。已导出的视频文件也不会自动改变。

## 字幕透明度

- **卡拉OK字幕 → 歌词 → 字幕透明度**：同步调节歌词、注音、翻译、倒计时及逐字特效；描边、阴影和荧光一起变化。
- **歌曲信息 → 片头署名 → 署名透明度**：独立调节制作署名。原歌曲信息卡使用同一个值，也可在“信息透明度”中调整。

界面中 **0% 完全不透明，100% 完全透明**。旧项目没有该字段时保持原效果。透明度会与原有阴影、荧光强度相乘，保留扫光与淡入淡出；预览、ASS 字幕和生成的视频使用相同处理。

HTTP API 仍保存完整的 `KaraokeStyle`：`text.opacity` 和 `info.opacity` 为 **0–100 的不透明度**，100 表示完全不透明，与界面“透明度”方向相反。其他新增字段包括 `info.credits_enabled`、`credits_layout`（`card` / `single-line`）、`creator`、`model_text`、`font_text`、`show_models`、`show_fonts`；`info.position` 支持 `top-left`、`top-center`、`top-right`。

## 安装与更新

按 [README 的源码安装步骤](../README.md#安装) 克隆本 fork。仓库已经包含构建后的网页资源，直接安装 Python 项目即可使用新增界面；修改前端之后才需要重新构建。

```bash
git clone --branch custom https://github.com/pzl233/MiliKara.git
cd MiliKara
uv venv --python 3.12 .venv
uv pip install -e ".[ml,separation]"
```

还需要带 libass 的 ffmpeg。运行命令和 GPU 安装方法见 README。模型权重会在第一次需要时下载，之后可离线使用；Frazer / becruily 模型详见 [模型说明](frazer-becruily.md)。

本 fork 尚未发布定制离线安装包。上游的 Releases、版本检查和离线更新器仍指向原作者；运行上游更新器会回到上游程序。保留定制功能请更新 `custom` 分支的源码并重新安装。

## 开发验证

前端：

```bash
cd frontend
npm ci
npm run build
```

Python（先安装开发依赖，真实画面检查需要 ffmpeg / ffprobe 和可用字体）：

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_production_credits.py tests/test_subtitle_opacity.py tests/test_karaoke.py tests/test_round5_render.py
```

新增测试覆盖署名实际模型来源、旧样式兼容、居中排版、预览跳转与草稿保存、时间范围，以及透明度在扫光、描边、阴影、荧光和特效中的实际渲染效果。模型支持有独立的配置与兼容测试，见模型说明。
