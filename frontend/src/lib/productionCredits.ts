import type { AudioAsset, KaraokeStyle } from './types';

/** The preview API uses the original audio timeline; video-frame offsets are handled by the server. */
export function productionCreditsPreview(info: KaraokeStyle['info'], audio: AudioAsset[]) {
  const original = audio.find((a) => a.role === 'original');
  const modelAvailable = audio.some((a) => (a.role === 'vocals' || a.role === 'instrumental') && a.source.model?.trim()
    && (a.source.parent_sha256 == null || a.source.parent_sha256 === original?.sha256));
  let reason: string | null = null;
  if (!info.credits_enabled) reason = '请先开启片头署名。';
  else if (!info.creator?.trim() && !(info.show_fonts ?? true)
    && !((info.show_models ?? true) && (info.model_text?.trim() || modelAvailable))) {
    reason = '请填写制作者，或开启分离模型、字幕字体。';
  }
  const available = original?.duration_ms ? original.duration_ms - info.start_ms : info.duration_ms;
  if (!reason && available <= 0) reason = '署名出现时间已超过音频结尾，请调整出现时间。';
  const duration = Math.max(0, Math.min(info.duration_ms, available));
  // A long card may fade out early to avoid later lyrics: look shortly after its entrance.
  return { reason, tMs: Math.max(0, Math.round(info.start_ms + Math.min(1500, duration / 2))) };
}
