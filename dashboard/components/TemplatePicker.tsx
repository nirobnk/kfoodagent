'use client';

import { useEffect, useState } from 'react';
import { api, explainSendFailure } from '@/lib/api';
import type { Template } from '@/lib/types';

/**
 * Shown when the 24-hour window has closed: the only thing Meta accepts then is
 * an approved template.
 */
export function TemplatePicker({
  contactId,
  onSent,
}: {
  contactId: string;
  onSent: () => void;
}) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);
  const [values, setValues] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listTemplates()
      .then(({ templates: list }) => setTemplates(list.filter((t) => t.approved)))
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load templates'));
  }, []);

  function choose(template: Template) {
    setSelected(template);
    setValues(new Array(template.variables?.length ?? 0).fill(''));
    setError(null);
  }

  async function send() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.sendTemplate(contactId, selected.key, values);
      if (!result.ok) {
        setError(explainSendFailure(result.reason));
      } else {
        setSelected(null);
        setValues([]);
        onSent();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send');
    } finally {
      setBusy(false);
    }
  }

  if (templates.length === 0) {
    return (
      <p className="p-3 text-center text-xs text-soy">
        The 24-hour window is closed and no approved template is available yet. Submit templates in
        Meta Business Manager, then mark them approved in the templates table.
      </p>
    );
  }

  return (
    <div className="space-y-2 p-3">
      <p className="text-xs text-soy">
        The free-reply window has closed. Choose an approved template:
      </p>

      <div className="flex flex-wrap gap-2">
        {templates.map((template) => (
          <button
            key={template.id}
            onClick={() => choose(template)}
            className={`rounded-full border px-3 py-1.5 text-xs transition ${
              selected?.id === template.id
                ? 'border-wa-green bg-ink text-white'
                : 'border-line bg-card hover:bg-paper'
            }`}
          >
            {template.key}
          </button>
        ))}
      </div>

      {selected && (
        <div className="space-y-2 rounded-lg border border-line bg-card p-3">
          {selected.body_preview && (
            <p className="text-xs italic text-soy">{selected.body_preview}</p>
          )}
          {(selected.variables ?? []).map((name, index) => (
            <input
              key={name + index}
              value={values[index] ?? ''}
              onChange={(event) => {
                const next = [...values];
                next[index] = event.target.value;
                setValues(next);
              }}
              placeholder={`{{${index + 1}}} ${name}`}
              className="w-full rounded border border-line px-2 py-1.5 text-sm outline-none focus:border-ink"
            />
          ))}
          <button
            onClick={send}
            disabled={busy || values.some((value) => !value.trim())}
            className="w-full rounded-lg bg-ink py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? 'Sending…' : 'Send template'}
          </button>
        </div>
      )}

      {error && <p className="text-xs text-chilli">{error}</p>}
    </div>
  );
}
