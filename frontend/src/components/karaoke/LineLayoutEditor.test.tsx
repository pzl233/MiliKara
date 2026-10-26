import { act, fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui';
import { renderUI } from '@/test/helpers';
import { LineLayoutEditor, type LayoutLine } from './LineLayoutEditor';

const fixtureLines = (): LayoutLine[] => [
  { id: 'first', index: 1, text: '第一句歌词', rows: undefined, start: 5000, end: 8000 },
  { id: 'second', index: 2, text: '第二句歌词', rows: null, start: 9000, end: 12000 },
  { id: 'third', index: 3, text: '第三句歌词', rows: 1, start: 13000, end: 16000 },
  { id: 'fourth', index: 4, text: '第四句歌词', rows: 2, start: null, end: null },
];

function setup(lines = fixtureLines(), defaultRows: 1 | 2 = 1) {
  const save = vi.fn<(ids: string[], rows: 1 | 2 | null) => Promise<void>>().mockResolvedValue(undefined);
  const preview = vi.fn();
  const view = renderUI(<LineLayoutEditor lines={lines} defaultRows={defaultRows} onSave={save} onPreview={preview} />);
  const checkbox = (n: number) => screen.getByRole('checkbox', { name: `选择第 ${n} 句：${lines[n - 1].text}` });
  const button = (name: string) => screen.getByRole('button', { name });
  const clickSave = async (name: string) => { await act(async () => { fireEvent.click(button(name)); }); };
  return { ...view, save, preview, checkbox, button, clickSave };
}

describe('per-line karaoke layout', () => {
  it('shows legacy lines following the global default and keeps explicit settings', () => {
    const { checkbox, rerender, save, preview } = setup();
    expect(screen.getByRole('region', { name: '分段行数' })).toBeInTheDocument();
    expect(within(checkbox(1).closest('label')!).getByText('默认（1行）')).toBeVisible();
    expect(within(checkbox(2).closest('label')!).getByText('默认（1行）')).toBeVisible();
    expect(within(checkbox(3).closest('label')!).getByText('1行')).toBeVisible();
    expect(within(checkbox(4).closest('label')!).getByText('2行')).toBeVisible();
    expect(checkbox(1).closest('label')).toHaveTextContent('0:05 – 0:08');
    expect(checkbox(4).closest('label')).toHaveTextContent('未对齐');
    rerender(<TooltipProvider><LineLayoutEditor lines={fixtureLines()} defaultRows={2} onSave={save} onPreview={preview} /></TooltipProvider>);
    expect(within(checkbox(1).closest('label')!).getByText('默认（2行）')).toBeVisible();
    expect(within(checkbox(3).closest('label')!).getByText('1行')).toBeVisible();
    expect(save).not.toHaveBeenCalled();
  });

  it('selects and deselects a contiguous range with Shift, then saves one atomic operation', async () => {
    const lines = fixtureLines();
    const before = structuredClone(lines);
    const { checkbox, clickSave, save } = setup(lines);
    fireEvent.click(checkbox(1));
    fireEvent.click(checkbox(3), { shiftKey: true });
    expect([1, 2, 3].map((n) => (checkbox(n) as HTMLInputElement).checked)).toEqual([true, true, true]);
    expect(checkbox(4)).not.toBeChecked();
    expect(screen.getByText('已选 3 句')).toBeVisible();
    await clickSave('两行（上左下右）');
    expect(save).toHaveBeenCalledExactlyOnceWith(['first', 'second', 'third'], 2);
    expect(lines).toEqual(before);
    fireEvent.click(checkbox(1), { shiftKey: true });
    expect(screen.getByText('已选 0 句')).toBeVisible();
    expect(screen.getAllByRole('checkbox').every((c) => !(c as HTMLInputElement).checked)).toBe(true);
  });

  it('applies one line and restores selected lines to the default using null', async () => {
    const { checkbox, clickSave, save } = setup();
    fireEvent.click(checkbox(4));
    fireEvent.click(checkbox(2));
    await clickSave('一行');
    expect(save).toHaveBeenLastCalledWith(['second', 'fourth'], 1);
    await clickSave('跟随默认');
    expect(save).toHaveBeenLastCalledWith(['second', 'fourth'], null);
    expect(save).toHaveBeenCalledTimes(2);
  });

  it('selects all and clears without changing any line or saving automatically', () => {
    const lines = fixtureLines();
    const before = structuredClone(lines);
    const { button, save } = setup(lines);
    expect(button('一行')).toBeDisabled();
    fireEvent.click(button('全选'));
    expect(screen.getByText('已选 4 句')).toBeVisible();
    expect(screen.getAllByRole('checkbox').every((c) => (c as HTMLInputElement).checked)).toBe(true);
    fireEvent.click(button('清空选择'));
    expect(screen.getByText('已选 0 句')).toBeVisible();
    expect(button('一行')).toBeDisabled();
    expect(button('两行（上左下右）')).toBeDisabled();
    expect(button('跟随默认')).toBeDisabled();
    expect(save).not.toHaveBeenCalled();
    expect(lines).toEqual(before);
  });

  it('previews the first selected lyric in song order and disables preview for unaligned lyrics', () => {
    const { checkbox, button, preview } = setup();
    expect(button('预览所选第一句')).toBeDisabled();
    fireEvent.click(checkbox(4));
    expect(button('预览所选第一句')).toBeDisabled();
    fireEvent.click(checkbox(3));
    fireEvent.click(checkbox(1));
    fireEvent.click(button('预览所选第一句'));
    expect(preview).toHaveBeenCalledExactlyOnceWith(fixtureLines()[0]);
  });

  it('keeps the apply tools visible when the lyric list is collapsed', async () => {
    const { checkbox, button, save, clickSave } = setup();
    fireEvent.click(checkbox(2));
    fireEvent.click(button('收起歌词'));
    expect(screen.getByRole('heading', { name: '分段行数' })).toBeVisible();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(button('两行（上左下右）')).toBeVisible();
    expect(button('预览所选第一句')).toBeEnabled();
    await clickSave('两行（上左下右）');
    expect(save).toHaveBeenCalledExactlyOnceWith(['second'], 2);
    fireEvent.click(button('展开歌词（4 句）'));
    expect(checkbox(2)).toBeChecked();
  });

  it('prevents repeated saves and edits while a batch is being saved', async () => {
    let finish!: () => void;
    const save = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    renderUI(<LineLayoutEditor lines={fixtureLines()} defaultRows={1} onSave={save} onPreview={vi.fn()} />);
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: '一行' }));
    expect(screen.getByRole('status')).toHaveTextContent('保存中');
    expect(screen.getAllByRole('checkbox').every((c) => (c as HTMLInputElement).disabled)).toBe(true);
    expect(screen.getByRole('button', { name: '两行（上左下右）' })).toBeDisabled();
    await act(async () => { finish(); });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')[0]).toBeEnabled();
    expect(save).toHaveBeenCalledExactlyOnceWith(['first'], 1);
  });
});
