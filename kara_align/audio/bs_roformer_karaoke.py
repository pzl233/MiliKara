"""The frazer/becruily Karaoke checkpoint on the pinned audio-separator 0.30 API.

Only this preset uses the adapter. No dependency files, model registries or
other separator classes are modified. See docs/frazer-becruily.md for the
fixed model source, configuration provenance and upstream MIT attribution.

The MDXC loading/inference adaptation follows python-audio-separator v0.30.2:
https://github.com/nomadkaraoke/python-audio-separator/tree/v0.30.2
Copyright (c) 2023 karaokenerds. MIT licensed; the full notice is distributed
in this package at configs/audio-separator-MIT.txt and in the source tree at
docs/licenses/audio-separator-MIT.txt.
"""

from __future__ import annotations

import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import tempfile

import httpx

MODEL_FILENAME = "bs_roformer_karaoke_frazer_becruily.ckpt"
MODEL_REVISION = "f7849ae934209184dc288d1018cd8a76a7fc8b3c"
MODEL_URL = f"https://huggingface.co/becruily/bs-roformer-karaoke/resolve/{MODEL_REVISION}/{MODEL_FILENAME}"
MODEL_SHA256 = "eb90ee24c1154d83fbcfd27e96182f19e061557cc6e4746953125e08c29389f9"
MODEL_BYTES = 204436907


def model_config() -> dict:
    """A fresh copy of the author's inference configuration, adapted for 0.30.2."""
    data = resources.files(__package__).joinpath("configs", "bs_roformer_karaoke_frazer_becruily.json")
    config = json.loads(data.read_text(encoding="utf-8"))
    # The author's YAML uses !!python/tuple, which the typed BSRoformer
    # constructor requires. JSON stores those two immutable sequences as lists.
    for key in ("freqs_per_bands", "multi_stft_resolutions_window_sizes"):
        config["model"][key] = tuple(config["model"][key])
    return config


def ensure_checkpoint(model_dir: Path) -> Path:
    """Download atomically and verify even a manually supplied checkpoint before loading it."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    target = model_dir / MODEL_FILENAME
    if target.exists():
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if target.stat().st_size != MODEL_BYTES or digest != MODEL_SHA256:
            raise RuntimeError(f"模型校验失败：{target}；请移走该文件，重新下载作者原版模型。")
        return target

    partial = None
    try:
        digest, received = hashlib.sha256(), 0
        with tempfile.NamedTemporaryFile(mode="wb", dir=model_dir, prefix=MODEL_FILENAME + ".", suffix=".part", delete=False) as stream:
            partial = Path(stream.name)
            with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=60.0) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(1024 * 1024):
                    received += len(chunk)
                    if received > MODEL_BYTES:
                        raise RuntimeError("下载的模型大小与作者原版不符。")
                    digest.update(chunk)
                    stream.write(chunk)
        if received != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
            raise RuntimeError("下载的模型校验失败，未将它作为可用模型保存。")
        os.replace(partial, target)
        partial = None
        return target
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def chunk_starts(audio_length: int, chunk_size: int, step: int) -> list[int]:
    """Nonnegative, nonduplicated starts, including a short input or the final full window."""
    if chunk_size <= 0 or step <= 0 or step > chunk_size:
        raise ValueError("Roformer window and overlap step must cover the whole audio")
    starts = []
    for offset in range(0, audio_length, step):
        if offset + chunk_size >= audio_length:
            tail = max(audio_length - chunk_size, 0)
            if not starts or starts[-1] != tail:
                starts.append(tail)
            break
        starts.append(offset)
    return starts


def demix_roformer(separator, mix):
    """The 0.30.2 Roformer inference path with the STFT hop and tail lengths corrected.

    Keep its overlap in seconds and CPU accumulation, rather than changing the
    meaning of settings or increasing GPU/MPS memory use for other presets.
    """
    import numpy as np
    import torch
    from scipy import signal
    from tqdm import tqdm
    from audio_separator.separator.uvr_lib_v5 import spec_utils

    original = mix
    if separator.pitch_shift:
        mix, pitched_rate = spec_utils.change_pitch_semitones(
            mix, separator.sample_rate, semitone_shift=-separator.pitch_shift)
    config = separator.model_data_cfgdict
    segment = separator.segment_size if separator.override_model_segment_size else config.inference.dim_t
    # audio.hop_length is 441 here; the actual model's STFT hop is 512.
    chunk_size = int(config.model.stft_hop_length) * (int(segment) - 1)
    step = int(separator.overlap * config.audio.sample_rate)
    starts = chunk_starts(mix.shape[-1], chunk_size, step)
    window = torch.tensor(signal.windows.hamming(chunk_size), dtype=torch.float32)
    device = next(separator.model_run.parameters()).device
    mix = torch.tensor(mix, dtype=torch.float32)
    result = torch.zeros_like(mix, device="cpu")
    counter = torch.zeros(mix.shape[-1], dtype=torch.float32)
    with torch.no_grad():
        for start in tqdm(starts):
            part = mix[:, start:start + chunk_size].to(device)
            prediction = separator.model_run(part.unsqueeze(0))[0].cpu()
            # istft can reconstruct less than a complete hop at the tail.
            length = min(part.shape[-1], prediction.shape[-1], window.shape[0], result.shape[-1] - start)
            if length > 0:
                result[..., start:start + length] += prediction[..., :length] * window[:length]
                counter[start:start + length] += window[:length]
    vocals = (result / counter.clamp(min=1e-10)).numpy()
    if separator.pitch_shift:
        vocals = separator.pitch_fix(vocals, pitched_rate, original)
    if vocals.shape[-1] != original.shape[-1]:
        vocals = spec_utils.match_array_shapes(vocals, original)
    return {separator.primary_stem_name: vocals, separator.secondary_stem_name: np.asarray(original) - vocals}


def load_model(separator) -> None:
    """Use the library's normal model loader/output pipeline with a model-local demix override."""
    from audio_separator.separator.architectures.mdxc_separator import MDXCSeparator

    class KaraokeBSRoformerSeparator(MDXCSeparator):
        def demix(self, mix):
            return demix_roformer(self, mix)

    checkpoint = ensure_checkpoint(Path(separator.model_file_dir))
    separator.logger.info("Loading verified frazer/becruily Karaoke model...")
    # This is the 0.30.2 Separator.load_model common configuration, without a
    # registry/network lookup or mutations to the installed dependency package.
    keys = ("logger", "log_level", "torch_device", "torch_device_cpu", "torch_device_mps", "onnx_execution_provider",
            "output_format", "output_bitrate", "output_dir", "normalization_threshold", "amplification_threshold",
            "output_single_stem", "invert_using_spec", "sample_rate", "use_soundfile")
    common = {key: getattr(separator, key) for key in keys}
    common.update(model_name=checkpoint.stem, model_path=str(checkpoint), model_data=model_config())
    separator.model_instance = KaraokeBSRoformerSeparator(common_config=common, arch_config=separator.arch_specific_params["MDXC"])
