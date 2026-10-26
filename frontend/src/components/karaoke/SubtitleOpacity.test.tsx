import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderUI } from '@/test/helpers';
import { builtinSaved, plainStyle } from '@/test/style';
import { useLibrary } from '@/store/styles';
import { StylePanel } from './StylePanel';

beforeEach(() => useLibrary.setState({ saved: [builtinSaved()] }));
afterEach(cleanup);

describe('subtitle transparency', () => {
  it('shows an old lyric style as opaque and only updates the opacity field', () => {
    const style = plainStyle();
    delete style.text.opacity;
    const save = vi.fn();
    renderUI(<StylePanel style={style} onChange={save} fonts={[]} defaultFont="" defaultSection="text" />);
    const box = screen.getByRole('textbox', { name: '字幕透明度（输入数值）' });
    expect(box).toHaveValue('0');
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: '35' } });
    fireEvent.blur(box);
    expect(save).toHaveBeenLastCalledWith({ ...style, text: { ...style.text, opacity: 65 } });
  });

  it('lets song information use full transparency independently of the lyrics', () => {
    const style = plainStyle();
    style.info.enabled = true;
    delete style.info.opacity;
    const save = vi.fn();
    renderUI(<StylePanel style={style} onChange={save} fonts={[]} defaultFont="" defaultSection="info" />);
    const box = screen.getByRole('textbox', { name: '信息透明度（输入数值）' });
    expect(box).toHaveValue('0');
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: '100' } });
    fireEvent.blur(box);
    expect(save).toHaveBeenLastCalledWith({ ...style, info: { ...style.info, opacity: 0 } });
  });
});
