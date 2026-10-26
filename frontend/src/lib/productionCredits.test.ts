import { describe, expect, it } from 'vitest';
import { fixturePV } from '@/test/helpers';
import { defaultStyle } from '@/test/style';
import { productionCreditsPreview } from './productionCredits';

describe('production credits preview target', () => {
  it('uses the audio timeline and stays near the entrance for a long card', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, start_ms: 12000, duration_ms: 3000 };
    expect(productionCreditsPreview(info, []).tMs).toBe(13500);
    expect(productionCreditsPreview({ ...info, duration_ms: 300000 }, []).tMs).toBe(13500);
    expect(productionCreditsPreview({ ...info, duration_ms: 1000 }, []).tMs).toBe(12500);
  });

  it('avoids seeking past the original audio and explains disabled or empty credits', () => {
    const audio = fixturePV().project.audio;
    const original = audio.find((a) => a.role === 'original')!;
    original.duration_ms = 14000;
    const info = { ...defaultStyle().info, credits_enabled: true, start_ms: 13000, duration_ms: 3000 };
    expect(productionCreditsPreview(info, audio)).toEqual({ reason: null, tMs: 13500 });
    expect(productionCreditsPreview({ ...info, start_ms: 14000 }, audio).reason).toContain('音频结尾');
    expect(productionCreditsPreview({ ...info, credits_enabled: false }, audio).reason).toContain('开启片头署名');
    expect(productionCreditsPreview({ ...info, creator: '', show_models: false, show_fonts: false }, audio).reason).toContain('填写制作者');
  });
});
