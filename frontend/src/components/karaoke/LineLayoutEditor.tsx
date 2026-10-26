import { ChevronDown, ListChecks } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Button, Card, CardBody, CardHeader, Tip } from '@/components/ui';
import { fmtMs } from '@/lib/format';
import type { Line } from '@/lib/types';

export interface LayoutLine {
  id: string; index: number; text: string; rows: Line['karaoke_rows'];
  start: number | null; end: number | null;
}

/** Select whole lyric lines without changing their text or alignment. */
export function LineLayoutEditor({ lines, defaultRows, onSave, onPreview }: {
  lines: LayoutLine[]; defaultRows: number;
  onSave: (ids: string[], rows: 1 | 2 | null) => Promise<void>;
  onPreview: (line: LayoutLine) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState(true);
  const [busy, setBusy] = useState(false);
  const anchor = useRef<string | null>(null);
  const listId = useId();
  const titleId = useId();
  const idsKey = JSON.stringify(lines.map((l) => l.id));
  useEffect(() => {
    const valid = new Set<string>(JSON.parse(idsKey));
    setSelected((prev) => new Set([...prev].filter((id) => valid.has(id))));
    if (anchor.current && !valid.has(anchor.current)) anchor.current = null;
  }, [idsKey]);

  const chosen = lines.filter((l) => selected.has(l.id));
  const first = chosen[0];
  const previewReason = !first ? '先勾选需要预览的歌词' : first.start === null || first.end === null ? '所选第一句还没有对齐时间' : undefined;
  const toggle = (id: string, checked: boolean, shift: boolean) => {
    const previousAnchor = anchor.current;
    setSelected((prev) => {
      const next = new Set(prev);
      const a = lines.findIndex((l) => l.id === previousAnchor);
      const b = lines.findIndex((l) => l.id === id);
      const range = shift && a >= 0 ? lines.slice(Math.min(a, b), Math.max(a, b) + 1) : lines.slice(b, b + 1);
      for (const l of range) { if (checked) next.add(l.id); else next.delete(l.id); }
      return next;
    });
    anchor.current = id;
  };
  const save = async (rows: 1 | 2 | null) => {
    if (!chosen.length || busy) return;
    setBusy(true);
    try { await onSave(chosen.map((l) => l.id), rows); }
    finally { setBusy(false); }
  };

  return (
    <Card role="region" aria-labelledby={titleId}>
      <CardHeader icon={<ListChecks className="size-4" />} title={<span id={titleId}>分段行数</span>}
        description="勾选歌词后应用行数，一首歌可以混排。两行时上句靠左、下句靠右；一行时固定在单行位置。" />
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="设置所选歌词行数">
          <span className="mr-1 text-[13px] text-muted" aria-live="polite">已选 {chosen.length} 句</span>
          <Button size="sm" disabled={!chosen.length || busy} onClick={() => void save(1)}>一行</Button>
          <Button size="sm" disabled={!chosen.length || busy} onClick={() => void save(2)}>两行（上左下右）</Button>
          <Button size="sm" variant="outline" disabled={!chosen.length || busy} onClick={() => void save(null)}>跟随默认</Button>
          <Tip content={previewReason ?? '跳到所选第一句的字幕画面'}>
            <span className="inline-flex"><Button size="sm" variant="ghost" disabled={busy || !!previewReason}
              onClick={() => first && onPreview(first)}>预览所选第一句</Button></span>
          </Tip>
          {busy && <span role="status" className="text-xs text-muted">保存中…</span>}
        </div>
        <p className="text-xs text-muted">未单独设置的歌词跟随右侧“布局 → 同屏行数”，当前默认 {defaultRows} 行。</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="xs" variant="ghost" disabled={!lines.length || busy} onClick={() => { setSelected(new Set(lines.map((l) => l.id))); anchor.current = null; }}>全选</Button>
          <Button size="xs" variant="ghost" disabled={!chosen.length || busy} onClick={() => { setSelected(new Set()); anchor.current = null; }}>清空选择</Button>
          <span className="flex-1 text-xs text-subtle">按住 Shift 可连续选择</span>
          <Button size="xs" variant="ghost" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded((v) => !v)}
            icon={<ChevronDown className={`size-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />}>
            {expanded ? '收起歌词' : `展开歌词（${lines.length} 句）`}
          </Button>
        </div>
        <div id={listId} hidden={!expanded}>
          {lines.length ? (
            <div className="max-h-80 divide-y divide-line overflow-auto rounded-lg border border-line">
              {lines.map((line) => (
                <label key={line.id} className={`flex cursor-pointer items-start gap-3 px-3 py-2.5 hover:bg-surface-2 ${selected.has(line.id) ? 'bg-accent-soft' : ''}`}>
                  <input type="checkbox" className="mt-1 size-4 shrink-0 accent-[var(--color-accent)]" aria-label={`选择第 ${line.index} 句：${line.text}`}
                    checked={selected.has(line.id)} disabled={busy}
                    onClick={(e) => toggle(line.id, e.currentTarget.checked, e.shiftKey)} onChange={() => {}} />
                  <span className="w-5 shrink-0 pt-0.5 text-right text-xs text-subtle">{line.index}</span>
                  <span className="min-w-0 flex-1 space-y-0.5">
                    <span className="block text-[13px] leading-5">{line.text}</span>
                    <span className="block font-mono text-xs text-subtle">{line.start !== null && line.end !== null ? `${fmtMs(line.start, false)} – ${fmtMs(line.end, false)}` : '未对齐'}</span>
                  </span>
                  <span className="shrink-0 rounded-md bg-surface-2 px-2 py-1 text-xs text-muted">{line.rows == null ? `默认（${defaultRows}行）` : `${line.rows}行`}</span>
                </label>
              ))}
            </div>
          ) : <p className="py-3 text-center text-sm text-muted">还没有可设置的歌词。</p>}
        </div>
      </CardBody>
    </Card>
  );
}
