"""The optional frazer preset is isolated, hash verified, and safe at chunk boundaries."""

from contextlib import contextmanager
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from kara_align.audio import bs_roformer_karaoke as BS
from kara_align.audio import separation as SEP


def test_preset_and_inference_configuration_preserve_default_model():
    preset = SEP.get_preset("bs-roformer-karaoke-frazer-becruily")
    assert preset.model_filename == BS.MODEL_FILENAME
    assert SEP.get_preset(BS.MODEL_FILENAME) is preset
    assert SEP.PRESETS[0].name == "melband-roformer"
    assert "no explicit weight licence" in preset.license_note
    config = BS.model_config()
    assert config["model"]["stft_hop_length"] == 512 != config["audio"]["hop_length"]
    assert config["inference"]["dim_t"] == 2001
    assert config["model"]["num_stems"] == 1
    assert isinstance(config["model"]["freqs_per_bands"], tuple)
    assert isinstance(config["model"]["multi_stft_resolutions_window_sizes"], tuple)
    assert sum(config["model"]["freqs_per_bands"]) == config["model"]["dim_freqs_in"] == 1025
    assert "mlp_expansion_factor" not in config["model"]
    config["model"]["depth"] = -1
    assert BS.model_config()["model"]["depth"] == 12  # every load gets a fresh copy
    assert BS.MODEL_REVISION in BS.MODEL_URL


def checkpoint_data(monkeypatch):
    data = b"a small simulated checkpoint"
    monkeypatch.setattr(BS, "MODEL_BYTES", len(data))
    monkeypatch.setattr(BS, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
    return data


def test_verified_local_checkpoint_is_used_without_network(tmp_path, monkeypatch):
    data = checkpoint_data(monkeypatch)
    model = tmp_path / BS.MODEL_FILENAME
    model.write_bytes(data)
    monkeypatch.setattr(BS.httpx, "stream", lambda *a, **k: pytest.fail("A verified local checkpoint must stay offline"))
    assert BS.ensure_checkpoint(tmp_path) == model


def test_wrong_local_checkpoint_is_rejected_without_overwriting_it(tmp_path, monkeypatch):
    checkpoint_data(monkeypatch)
    model = tmp_path / BS.MODEL_FILENAME
    model.write_bytes(b"wrong")
    with pytest.raises(RuntimeError, match="模型校验失败"):
        BS.ensure_checkpoint(tmp_path)
    assert model.read_bytes() == b"wrong"


@pytest.mark.parametrize("failure", [None, "checksum", "interrupted", "oversized"])
def test_download_is_atomic_and_bad_or_incomplete_data_never_becomes_a_model(tmp_path, monkeypatch, failure):
    data = checkpoint_data(monkeypatch)
    target = tmp_path / BS.MODEL_FILENAME

    class Response:
        def raise_for_status(self):
            pass

        def iter_bytes(self, _chunk_size):
            assert not target.exists()
            yield data[:5]
            assert not target.exists()
            if failure == "interrupted":
                raise OSError("connection lost")
            if failure == "checksum":
                yield b"X" * (len(data) - 5)
            else:
                yield data[5:]
            if failure == "oversized":
                yield b"unexpected extra bytes"

    @contextmanager
    def stream(method, url, **kwargs):
        assert method == "GET" and url == BS.MODEL_URL
        yield Response()

    monkeypatch.setattr(BS.httpx, "stream", stream)
    if failure:
        with pytest.raises((RuntimeError, OSError)):
            BS.ensure_checkpoint(tmp_path)
        assert not target.exists()
    else:
        assert BS.ensure_checkpoint(tmp_path).read_bytes() == data
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("length,chunk,step", [(5, 40, 20), (40, 40, 20), (70, 40, 30), (85, 40, 20), (120, 40, 32)])
def test_chunk_schedule_covers_short_exact_and_tail_inputs_without_duplicates(length, chunk, step):
    starts = BS.chunk_starts(length, chunk, step)
    assert starts == sorted(set(starts))
    assert starts[0] == 0 and starts[-1] == max(0, length - chunk)
    assert all(start >= 0 for start in starts)
    coverage = np.zeros(length, dtype=int)
    for start in starts:
        coverage[start:start + chunk] += 1
    assert np.all(coverage > 0)


@pytest.mark.parametrize("length", [10, 40, 85])
def test_demix_uses_the_model_hop_and_handles_short_istft_outputs(length):
    torch = pytest.importorskip("torch")
    pytest.importorskip("audio_separator")

    class ShortModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.parameter = torch.nn.Parameter(torch.zeros(1))
            self.lengths = []

        def forward(self, batch):
            self.lengths.append(batch.shape[-1])
            return batch[..., :-2] * 0.25

    model = ShortModel()
    separator = SimpleNamespace(pitch_shift=0, override_model_segment_size=False, overlap=2,
        model_data_cfgdict=SimpleNamespace(
            model=SimpleNamespace(stft_hop_length=4), inference=SimpleNamespace(dim_t=11),
            audio=SimpleNamespace(sample_rate=10, hop_length=3)),
        model_run=model, primary_stem_name="Vocals", secondary_stem_name="Instrumental")
    mix = np.ones((2, length), dtype=np.float32)
    stems = BS.demix_roformer(separator, mix)
    assert model.lengths and max(model.lengths) == min(length, 40)
    assert stems["Vocals"].shape == stems["Instrumental"].shape == mix.shape
    assert np.isfinite(stems["Vocals"]).all()
    assert np.allclose(stems["Vocals"][..., :-2], 0.25)
    assert np.array_equal(stems["Vocals"][..., -2:], np.zeros((2, 2)))
    assert np.allclose(stems["Vocals"] + stems["Instrumental"], mix)
