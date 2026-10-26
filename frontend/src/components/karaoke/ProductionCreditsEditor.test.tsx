import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderUI } from '@/test/helpers';
import { defaultStyle } from '@/test/style';
import { TooltipProvider } from '@/components/ui';
import { ProductionCreditsEditor } from './ProductionCreditsEditor';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('production credits', () => {
  it('adds editable credits independently of the song card, and saves a combined draft', () => {
    const info = { ...defaultStyle().info, enabled: false };
    const save = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    expect(screen.getByRole('switch', { name: '显示片头署名' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('switch', { name: '显示片头署名' }));
    expect(screen.getByRole('switch', { name: '显示分离模型' })).toBeChecked();
    expect(screen.getByRole('switch', { name: '显示字幕字体' })).toBeChecked();
    fireEvent.change(screen.getByRole('textbox', { name: '视频制作者' }), { target: { value: '自填署名' } });
    fireEvent.change(screen.getByRole('textbox', { name: '分离模型说明' }), { target: { value: 'Karaoke 模型' } });
    fireEvent.change(screen.getByRole('textbox', { name: '字体说明' }), { target: { value: '我的字体' } });
    expect(screen.getByRole('textbox', { name: '视频制作者' })).toHaveValue('自填署名');
    expect(save).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ credits_enabled: true, creator: '自填署名', model_text: 'Karaoke 模型', font_text: '我的字体' });
    expect(info.enabled).toBe(false);
    expect(screen.getByRole('textbox', { name: '视频制作者' })).toHaveAttribute('maxlength', '120');
    expect(screen.getByRole('textbox', { name: '分离模型说明' })).toHaveAttribute('maxlength', '400');
  });

  it('keeps unsaved text when another saved setting arrives, and flushes it when leaving', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, creator: '旧署名' };
    const save = vi.fn();
    const view = renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    fireEvent.change(screen.getByRole('textbox', { name: '视频制作者' }), { target: { value: '新署名' } });
    view.rerender(<TooltipProvider><ProductionCreditsEditor info={{ ...info, duration_ms: 10000 }} onChange={save} /></TooltipProvider>);
    expect(screen.getByRole('textbox', { name: '视频制作者' })).toHaveValue('新署名');
    view.unmount();
    expect(save).toHaveBeenCalledWith({ creator: '新署名' });
  });

  it('offers a top single line without changing existing timing', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, start_ms: 5000, duration_ms: 3000 };
    const save = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    expect(screen.getByRole('radio', { name: '多行信息卡' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: '顶部单行' }));
    expect(screen.getByRole('radio', { name: '顶部单行' })).toBeChecked();
    fireEvent.click(screen.getByText('位置与显示时间'));
    expect(Number((screen.getByRole('textbox', { name: '署名出现时间（输入数值）' }) as HTMLInputElement).value)).toBe(5);
    expect(Number((screen.getByRole('textbox', { name: '署名显示时长（输入数值）' }) as HTMLInputElement).value)).toBe(3);
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenCalledWith({ credits_layout: 'single-line' });
    expect(info.start_ms).toBe(5000);
    expect(info.duration_ms).toBe(3000);
  });

  it('accepts longer times in seconds and saves milliseconds within the expanded limits', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, start_ms: 5000, duration_ms: 3000 };
    const save = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    fireEvent.click(screen.getByText('位置与显示时间'));
    const start = screen.getByRole('textbox', { name: '署名出现时间（输入数值）' });
    const duration = screen.getByRole('textbox', { name: '署名显示时长（输入数值）' });
    const enter = (box: HTMLElement, value: string) => {
      fireEvent.focus(box);
      fireEvent.change(box, { target: { value } });
      fireEvent.blur(box);
    };
    enter(start, '30.2');
    enter(duration, '45.5');
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenLastCalledWith({ start_ms: 30200, duration_ms: 45500 });
    enter(start, '9999');
    enter(duration, '9999');
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenLastCalledWith({ start_ms: 3600000, duration_ms: 600000 });
  });

  it('previews a new draft immediately instead of waiting for its autosave', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, creator: '旧署名' };
    const save = vi.fn();
    const preview = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} onPreview={preview} />);
    fireEvent.change(screen.getByRole('textbox', { name: '视频制作者' }), { target: { value: '新署名' } });
    fireEvent.click(screen.getByRole('button', { name: '预览片头署名' }));
    expect(save).toHaveBeenCalledWith({ creator: '新署名' });
    expect(preview).toHaveBeenCalledWith(expect.objectContaining({ creator: '新署名' }));
  });

  it('saves a top-center position for a single-line credit', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, credits_layout: 'single-line' as const,
      start_ms: 12000, duration_ms: 3000 };
    const save = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    fireEvent.click(screen.getByText('位置与显示时间'));
    expect(screen.getByRole('radio', { name: '靠左' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '靠右' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: '居中' }));
    expect(screen.getByRole('radio', { name: '居中' })).toBeChecked();
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenCalledWith({ position: 'top-center' });
    expect(screen.getByRole('radio', { name: '顶部单行' })).toBeChecked();
    expect(Number((screen.getByRole('textbox', { name: '署名出现时间（输入数值）' }) as HTMLInputElement).value)).toBe(12);
  });

  it('defaults old credits to opaque and saves transparency as opacity without changing other fields', () => {
    const info = { ...defaultStyle().info, credits_enabled: true, creator: '署名', start_ms: 12000, duration_ms: 3000 };
    delete info.opacity;
    const save = vi.fn();
    renderUI(<ProductionCreditsEditor info={info} onChange={save} />);
    const box = screen.getByRole('textbox', { name: '署名透明度（输入数值）' });
    expect(box).toHaveValue('0');
    expect(save).not.toHaveBeenCalled();
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: '35' } });
    fireEvent.blur(box);
    expect(box).toHaveValue('35');
    act(() => vi.advanceTimersByTime(500));
    expect(save).toHaveBeenCalledWith({ opacity: 65 });
    expect(info).toMatchObject({ creator: '署名', start_ms: 12000, duration_ms: 3000 });
  });
});
