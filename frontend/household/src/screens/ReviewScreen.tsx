import { Pencil, ShieldCheck } from 'lucide-react';
import { isExampleData, type Preview } from '../api';
import { ErrorBox, ExampleNotice, Loading } from '../components';
import { cantEatList, type FormState } from '../form';
import type { Strings } from '../i18n';

export function ReviewScreen(props: {
  t: Strings;
  form: FormState;
  preview: Preview | null;
  loading: boolean;
  error: unknown;
  retry: () => void;
  saving: boolean;
  saveError: unknown;
  onEdit: () => void;
  onConsent: (yes: boolean) => void;
}) {
  const { t, form, preview, loading, error, retry, saving, saveError, onEdit, onConsent } = props;
  const cantEat = cantEatList(form.cantEat);
  const rows: [string, string][] = [
    [t.labels.size, form.size === null ? t.notSet : t.people(form.size)],
    [t.labels.days, form.days ? t.days[form.days] : t.notSet],
    [t.labels.time, form.time ? t.times[form.time] : t.notSet],
    [t.labels.fridge, form.fridge === 'yes' ? t.yes : form.fridge === 'no' ? t.no : t.notSet],
    [t.labels.neighborhood, form.neighborhood.trim() || t.notSet],
    [t.labels.cantEat, cantEat.length ? cantEat.join(', ') : t.none],
    [t.labels.snap, form.snap === 'yes' ? t.yes : form.snap === 'no' ? t.no : t.preferNot],
    [t.labels.language, form.language === 'es' ? 'Español' : 'English'],
    [t.labels.phone, form.phone.trim() || t.notSet],
  ];
  const example = isExampleData(preview);

  return (
    <div className="stack">
      <section aria-labelledby="your-answers">
        <h2 id="your-answers" className="section-title">
          {t.yourAnswers}
        </h2>
        <dl className="review">
          {rows.map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <button type="button" className="secondary" onClick={onEdit} disabled={saving}>
          <Pencil size={19} aria-hidden="true" />
          {t.editAnswers}
        </button>
      </section>

      {loading && <Loading text={t.checking} />}
      {!loading && error != null && <ErrorBox error={error} t={t} onRetry={retry} />}

      {!loading && preview && (
        <>
          <section className="read-back" aria-labelledby="heard">
            <h2 id="heard" className="section-title">
              {t.heard}
            </h2>
            {example && <ExampleNotice t={t}>{t.exampleReadBack}</ExampleNotice>}
            <p className="api-text">{preview.read_back}</p>
          </section>

          {!preview.complete && (
            <section className="missing" aria-labelledby="missing">
              <h2 id="missing" className="section-title">
                {t.missingTitle}
              </h2>
              <ul>
                {preview.missing_questions.map(q => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </section>
          )}

          {preview.complete && (
            <section className="consent" aria-labelledby="consent-title">
              <h2 id="consent-title">
                <ShieldCheck size={36} aria-hidden="true" />
                {t.consentTitle}
              </h2>
              <p className="api-text" id="consent-question">
                {preview.consent_question || t.consentFallback}
              </p>
              {saveError != null && <ErrorBox error={saveError} t={t} />}
              <div className="consent-actions" role="group" aria-labelledby="consent-title" aria-describedby="consent-question">
                <button type="button" className="primary" onClick={() => onConsent(true)} disabled={saving}>
                  {saving ? t.saving : t.consentYes}
                </button>
                <button type="button" className="secondary" onClick={() => onConsent(false)} disabled={saving}>
                  {t.consentNo}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
