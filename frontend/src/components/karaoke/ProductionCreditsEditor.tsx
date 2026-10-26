import { useEffect, useRef, useState } from 'react';
import type { KaraokeStyle } from '@/lib/types';
import { Button, Field, Input, Segmented, SliderField, Switch, Textarea, Tip } from '@/components/ui';

type Info = KaraokeStyle['info'];
type InfoPatch = Partial<Info>;

/** Shared by the new-task defaults and the open project's subtitle style. */
export function ProductionCreditsEditor({ info, onChange, onPreview, previewDisabledReason }: {
  info: Info; onChange: (patch: InfoPatch) => void;
  onPreview?: (info: Info) => void; previewDisabledReason?: (info: Info) => string | null;
}) {
  const [draft, setDraft] = useState(info);
  const pending = useRef<InfoPatch>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const save = useRef(onChange);
  save.current = onChange;

  // A save or another style edit may return while someone is still typing.
  // Keep unsaved fields, and follow the latest saved values for everything else.
  useEffect(() => setDraft({ ...info, ...pending.current }), [info]);
  const flush = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (!Object.keys(pending.current).length) return;
    const patch = pending.current;
    pending.current = {};
    save.current(patch);
  };
  useEffect(() => () => flush(), []); // save a final edit when leaving this panel

  const change = (patch: InfoPatch) => {
    pending.current = { ...pending.current, ...patch };
    setDraft((current) => ({ ...current, ...patch }));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, 500);
  };
  const on = draft.credits_enabled ?? false;
  const previewReason = previewDisabledReason?.(draft) ?? null;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Switch checked={on} onChange={(v) => change({ credits_enabled: v })} label="显示片头署名" />
        <p className="text-xs text-muted">在视频开头显示制作者、分离模型和字幕字体；只填写或开启需要显示的内容。</p>
        {onPreview && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Tip content={previewReason ?? '跳到片头署名显示期间，查看当前设置'}>
              <Button size="sm" variant="secondary" disabled={!!previewReason}
                onClick={() => { flush(); onPreview(draft); }}>预览片头署名</Button>
            </Tip>
            {previewReason && <span className="text-xs text-muted">{previewReason}</span>}
          </div>
        )}
      </div>
      {on && (
        <>
          <Field label="排列方式" group
            hint={draft.credits_layout === 'single-line' ? '制作信息在顶部排成一整行，过长时自动缩小。' : '制作者、分离模型和字体分行显示。'}>
            <Segmented label="署名排列方式" value={draft.credits_layout ?? 'card'} onChange={(v) => change({ credits_layout: v })}
              options={[{ value: 'card', label: '多行信息卡' }, { value: 'single-line', label: '顶部单行' }]} />
          </Field>
          <Field label="署名透明度" group hint="0% 完全不透明，100% 完全透明；歌曲信息也使用这个透明度。">
            <SliderField name="署名透明度" value={100 - (draft.opacity ?? 100)} min={0} max={100} step={1} unit="%"
              onChange={(v) => change({ opacity: 100 - v })} />
          </Field>
          <Field label="视频制作者" hint="填写你的名字、昵称或制作团队，留空不显示。">
            <Input aria-label="视频制作者" value={draft.creator ?? ''} maxLength={120} placeholder="例如：你的昵称 / 制作团队"
              onChange={(e) => change({ creator: e.target.value })} />
          </Field>
          <div className="space-y-2.5">
            <Switch checked={draft.show_models ?? true} onChange={(v) => change({ show_models: v })} label="显示分离模型" />
            {(draft.show_models ?? true) && (
              <Field label="分离模型说明（可选）" hint="留空自动显示这首歌实际使用的分离模型；也可以自己填写。">
                <Textarea aria-label="分离模型说明" rows={2} maxLength={400} value={draft.model_text ?? ''}
                  placeholder="自动读取实际使用的分离模型" onChange={(e) => change({ model_text: e.target.value })} />
              </Field>
            )}
          </div>
          <div className="space-y-2.5">
            <Switch checked={draft.show_fonts ?? true} onChange={(v) => change({ show_fonts: v })} label="显示字幕字体" />
            {(draft.show_fonts ?? true) && (
              <Field label="字体说明（可选）" hint="留空自动显示实际使用的歌词、注音和翻译字体；相同字体只列一次。">
                <Textarea aria-label="字体说明" rows={2} maxLength={400} value={draft.font_text ?? ''}
                  placeholder="自动读取字幕字体" onChange={(e) => change({ font_text: e.target.value })} />
              </Field>
            )}
          </div>
          <details className="rounded-xl border border-line p-3">
            <summary className="focus-ring cursor-pointer rounded text-[13px] font-medium">位置与显示时间</summary>
            <div className="mt-4 space-y-4">
              <Field label="片头位置" group>
                <Segmented label="片头位置" value={draft.position} onChange={(v) => change({ position: v })}
                  options={[{ value: 'top-left', label: '靠左' }, { value: 'top-center', label: '居中' }, { value: 'top-right', label: '靠右' }]} />
              </Field>
              <Field label="出现时间" group hint="最多 60 分钟；点击数值可直接输入秒数。">
                <SliderField name="署名出现时间" value={draft.start_ms / 1000} min={0} max={3600} step={0.1} unit="秒"
                  onChange={(v) => change({ start_ms: Math.round(v * 1000) })} />
              </Field>
              <Field label="显示时长" group hint="最多 10 分钟；可直接输入秒数。">
                <SliderField name="署名显示时长" value={draft.duration_ms / 1000} min={1} max={600} step={0.5} unit="秒"
                  onChange={(v) => change({ duration_ms: Math.round(v * 1000) })} />
              </Field>
              <Field label="标题字号" group>
                <SliderField name="署名标题字号" value={draft.size} min={20} max={120} step={1} unit="px"
                  onChange={(v) => change({ size: v })} />
              </Field>
              <Field label="画面边距" group>
                <SliderField name="署名画面边距" value={draft.margin} min={0} max={200} step={1} unit="px"
                  onChange={(v) => change({ margin: v })} />
              </Field>
              <p className="text-xs text-muted">与歌曲信息共用位置、字号和时间；会避让歌词和翻译。</p>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
