import { useState, type FormEvent } from 'react';
import { ArrowRight, Minus, Plus } from 'lucide-react';
import { isExampleData, type FairShare, type Language, type SnapAnswer } from '../api';
import { ChoiceGroup, ErrorBox, Loading } from '../components';
import { MAX_SIZE, MIN_SIZE, validate, type FieldErrors, type FieldName, type FormState } from '../form';
import type { DaysChoice, Strings, TimeChoice } from '../i18n';

export interface FairShareState {
  loading: boolean;
  data: FairShare | null;
  error: unknown;
  retry: () => void;
}

const FIELD_ORDER: FieldName[] = ['size', 'days', 'time', 'fridge', 'neighborhood', 'phone'];
const FIELD_TARGET: Record<FieldName, string> = {
  size: 'size-more',
  days: 'days-group',
  time: 'time-group',
  fridge: 'fridge-group',
  neighborhood: 'neighborhood',
  phone: 'phone',
};

export function AboutScreen(props: {
  t: Strings;
  form: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  fairShare: FairShareState;
  onReview: () => void;
  onLookup: (code: string) => void;
}) {
  const { t, form, update, fairShare, onReview, onLookup } = props;
  const [errors, setErrors] = useState<FieldErrors>({});
  const [code, setCode] = useState('');

  function submit(e: FormEvent) {
    e.preventDefault();
    const found = validate(form, t);
    setErrors(found);
    const first = FIELD_ORDER.find(name => found[name]);
    if (first) {
      const target = document.getElementById(FIELD_TARGET[first]);
      const focusable = target?.matches('fieldset') ? target.querySelector<HTMLElement>('input') : target;
      focusable?.focus();
      return;
    }
    onReview();
  }

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    update(key, value);
    if (key in errors) setErrors(prev => ({ ...prev, [key]: undefined }));
  };

  const hasErrors = Object.values(errors).some(Boolean);
  const describe = (name: FieldName, hint?: string) => [hint, errors[name] ? `${name}-error` : undefined].filter(Boolean).join(' ') || undefined;

  return (
    <>
      <form onSubmit={submit} className="form" noValidate>
        {hasErrors && (
          <p className="field-error summary" role="alert">
            {t.fixErrors}
          </p>
        )}

        <fieldset aria-describedby={errors.size ? 'size-error' : undefined}>
          <legend>{t.sizeLegend}</legend>
          {errors.size && (
            <p className="field-error" id="size-error">
              {errors.size}
            </p>
          )}
          <div className="counter">
            <button
              type="button"
              aria-label={t.fewer}
              disabled={form.size === null || form.size <= MIN_SIZE}
              onClick={() => form.size !== null && set('size', form.size - 1)}
            >
              <Minus size={22} aria-hidden="true" />
            </button>
            <output aria-live="polite">
              {form.size === null ? <span className="muted">{t.sizeEmpty}</span> : t.people(form.size)}
            </output>
            <button
              type="button"
              id="size-more"
              aria-label={t.more}
              disabled={form.size !== null && form.size >= MAX_SIZE}
              onClick={() => set('size', form.size === null ? MIN_SIZE : form.size + 1)}
            >
              <Plus size={22} aria-hidden="true" />
            </button>
          </div>
          <div className="fair-share" aria-live="polite">
            {form.size !== null && fairShare.loading && <Loading text={t.fairShareLoading} />}
            {form.size !== null && !fairShare.loading && fairShare.error != null && (
              <ErrorBox error={fairShare.error} t={t} onRetry={fairShare.retry} />
            )}
            {form.size !== null && !fairShare.loading && fairShare.data && (
              <>
                <p className="fair-share-wording">{fairShare.data.wording}</p>
                {(isExampleData(fairShare.data) || fairShare.data.is_placeholder) && (
                  <p className="tag-line">
                    {isExampleData(fairShare.data) && <span className="tag">{t.exampleTitle}</span>}
                    {fairShare.data.is_placeholder && <span>{t.placeholderTable}</span>}
                  </p>
                )}
              </>
            )}
          </div>
        </fieldset>

        <ChoiceGroup<DaysChoice>
          name="days"
          legend={t.daysLegend}
          value={form.days}
          onChange={v => set('days', v)}
          error={errors.days}
          options={[
            { value: 'weekdays', label: t.days.weekdays },
            { value: 'weekends', label: t.days.weekends },
            { value: 'any', label: t.days.any },
          ]}
        />

        <ChoiceGroup<TimeChoice>
          name="time"
          legend={t.timeLegend}
          value={form.time}
          onChange={v => set('time', v)}
          error={errors.time}
          stacked
          options={[
            { value: 'morning', label: t.times.morning },
            { value: 'afternoon', label: t.times.afternoon },
            { value: 'evening', label: t.times.evening },
            { value: 'any', label: t.times.any },
          ]}
        />

        <ChoiceGroup<'yes' | 'no'>
          name="fridge"
          legend={t.fridgeLegend}
          value={form.fridge}
          onChange={v => set('fridge', v)}
          error={errors.fridge}
          options={[
            { value: 'yes', label: t.yes },
            { value: 'no', label: t.no },
          ]}
        />

        <div>
          <label htmlFor="neighborhood">{t.neighborhoodLabel}</label>
          <p className="hint" id="neighborhood-hint">
            {t.neighborhoodHint}
          </p>
          {errors.neighborhood && (
            <p className="field-error" id="neighborhood-error">
              {errors.neighborhood}
            </p>
          )}
          <input
            id="neighborhood"
            value={form.neighborhood}
            onChange={e => set('neighborhood', e.target.value)}
            autoComplete="off"
            maxLength={80}
            aria-invalid={errors.neighborhood ? true : undefined}
            aria-describedby={describe('neighborhood', 'neighborhood-hint')}
          />
        </div>

        <div>
          <label htmlFor="cant-eat">{t.cantEatLabel}</label>
          <p className="hint" id="cant-eat-hint">
            {t.cantEatHint}
          </p>
          <textarea id="cant-eat" value={form.cantEat} onChange={e => set('cantEat', e.target.value)} maxLength={300} rows={2} aria-describedby="cant-eat-hint" />
        </div>

        <ChoiceGroup<SnapAnswer>
          name="snap"
          legend={t.snapLegend}
          hint={t.snapHint}
          value={form.snap}
          onChange={v => set('snap', v)}
          stacked
          options={[
            { value: 'yes', label: t.yes },
            { value: 'no', label: t.no },
            { value: 'not_said', label: t.preferNot },
          ]}
        />

        <ChoiceGroup<Language>
          name="language"
          legend={t.languageLegend}
          value={form.language}
          onChange={v => set('language', v)}
          lang={v => v}
          options={[
            { value: 'en', label: 'English' },
            { value: 'es', label: 'Español' },
          ]}
        />

        <div>
          <label htmlFor="phone">{t.phoneLabel}</label>
          <p className="hint" id="phone-hint">
            {t.phoneHint}
          </p>
          {errors.phone && (
            <p className="field-error" id="phone-error">
              {errors.phone}
            </p>
          )}
          <input
            id="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={form.phone}
            onChange={e => set('phone', e.target.value)}
            maxLength={20}
            aria-invalid={errors.phone ? true : undefined}
            aria-describedby={describe('phone', 'phone-hint')}
          />
        </div>

        <button className="primary" type="submit">
          {t.reviewButton}
          <ArrowRight size={21} aria-hidden="true" />
        </button>
      </form>

      <details className="lookup">
        <summary>{t.haveCode}</summary>
        <form
          onSubmit={e => {
            e.preventDefault();
            if (code.trim()) onLookup(code.trim().toUpperCase());
          }}
        >
          <label htmlFor="lookup-code">{t.codeLabel}</label>
          <div className="lookup-row">
            <input id="lookup-code" value={code} onChange={e => setCode(e.target.value)} autoComplete="off" autoCapitalize="characters" maxLength={12} />
            <button type="submit" className="secondary small">
              {t.codeButton}
            </button>
          </div>
        </form>
      </details>
    </>
  );
}
