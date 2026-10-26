# frazer / becruily Karaoke 分离模型

本分支增加 `bs-roformer-karaoke-frazer-becruily` 预设，可在设置的人声分离模型中选择，也可使用 CLI：

```console
milikara separate <项目路径> --preset bs-roformer-karaoke-frazer-becruily
```

在本 fork 根目录安装源码及项目原有的可选依赖：

```console
python -m pip install -e ".[separation]"
```

默认模型仍是 MelBand RoFormer。本预设只在分离子进程内使用自己的 MDXC 子类，不修改 `audio-separator` 安装目录、模型注册表或其它预设的推理方法。兼容目标为项目当前约束的 audio-separator 0.30 系列，实测版本为 0.30.2；没有为此升级整个分离引擎。

## 模型文件与下载

首次使用从 [becruily 的作者仓库](https://huggingface.co/becruily/bs-roformer-karaoke/tree/f7849ae934209184dc288d1018cd8a76a7fc8b3c) 下载固定版本的 checkpoint，保存到 MiliKara 的分离模型目录。已验证的本地文件可离线重复使用。下载先写入临时文件，长度和 SHA-256 校验通过后才原子替换为模型文件；失败文件不会作为有效模型保存。

- 文件名：`bs_roformer_karaoke_frazer_becruily.ckpt`
- 固定作者 revision：`f7849ae934209184dc288d1018cd8a76a7fc8b3c`
- 文件大小：`204436907` 字节
- SHA-256：`eb90ee24c1154d83fbcfd27e96182f19e061557cc6e4746953125e08c29389f9`

也可以手动把作者原版 checkpoint 放进 `<模型目录>/separation/`。模型目录遵循 `KARA_ALIGN_MODELS`；未设置时使用应用自己的 `models` 目录，或包安装情况下的用户模型目录。文件名、长度和校验值必须匹配；同名但不匹配的现有文件会报错，不会直接覆盖。

本 Git 仓库不包含 checkpoint。作者仓库在上述 revision 没有 README、模型卡 license 或独立许可证文件，因此本分支不替作者授予权重许可；使用或重新分发权重前，应向作者确认相应条件。

## 配置和兼容修复

`kara_align/audio/configs/bs_roformer_karaoke_frazer_becruily.json` 来自同一作者 revision 的 [`config_karaoke_frazer_becruily.yaml`](https://huggingface.co/becruily/bs-roformer-karaoke/blob/f7849ae934209184dc288d1018cd8a76a7fc8b3c/config_karaoke_frazer_becruily.yaml)，保留推理使用的模型参数、音频采样率 / hop、目标声部以及推理窗口，去掉训练专用配置，并作一项接口适配：

- 省略顶层 `model.mlp_expansion_factor: 4`：0.30.2 的 `BSRoformer` 构造函数不接受该参数，而内部 `MaskEstimator` 的默认值已经是 4。

只对此预设应用以下处理：

- 分块使用实际模型 `stft_hop_length=512`，而非配置里不同的 `audio.hop_length=441`。
- 短音频和尾块位置始终非负，且不会重复运行同一个尾块。
- overlap-add 和权重计数使用一致的有效长度，容忍 `istft` 比输入短不到一个 hop。
- 保留 0.30.2 的按秒设置 overlap 和 CPU 累加方式；人声与伴奏仍经过原库的输出和本项目的分轨长度 / 同步检查。

适配器沿用 [python-audio-separator v0.30.2](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.30.2) 的 MDXC 加载及推理流程。该库为 MIT 许可，版权归 `Copyright (c) 2023 karaokenerds`；完整许可保留于 [audio-separator-MIT.txt](licenses/audio-separator-MIT.txt)。此许可不等同于模型权重许可。

## 验证

`tests/audio/test_bs_roformer_karaoke.py` 覆盖模型身份和配置、离线缓存、原子下载、校验失败、短片 / 尾块覆盖、短 `istft` 输出以及分轨相加重建。

此外，在 Windows、Python 3.12、RTX 4070 Ti / CUDA 上，使用真实 checkpoint 和未修改的 audio-separator 0.30.2 源码完成了以下验证。模型已经缓存，耗时包括子进程加载和分轨写出；不同设备的速度会有差异。

| 用例 | 输入长度 | 每声道样本数 | 耗时 |
| --- | --- | --- | --- |
| frazer/becruily 短片 | 5 秒 | 240000 | 5.62 秒 |
| frazer/becruily 跨推理窗口及尾块 | 25.3 秒 | 1214400 | 9.66 秒 |
| 默认 MelBand 回归 | 25.3 秒 | 1214400 | 12.16 秒 |

三组输出均为 48 kHz 双声道、有限且非静音，长度与原始样本完全一致。验证前后原库 MDXC 源文件保持不变；默认 MelBand 继续走原库的加载和推理路径。
