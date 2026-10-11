import { useState } from 'react';
import { ArrowRight, Check, Clock3, MapPin, X } from 'lucide-react';
import type { CreatedRequest, FairShare, FoodBankList } from '../api';
import { ErrorBox, Loading } from '../components';
import { badgeLabel, formatDay, formatWindow, type Strings } from '../i18n';
import type { Language } from '../api';

export function CodeCard({ t, code, expiresAt, lang }: { t: Strings; code: string; expiresAt?: string; lang: Language }) {
  return (
    <section className="code-card" aria-labelledby="code-title">
      <h2 id="code-title" className="eyebrow">
        {t.codeIntro}
      </h2>
      <p className="code" aria-describedby="code-keep">
        {code}
      </p>
      <p id="code-keep">{t.codeKeep}</p>
      {expiresAt && <p className="small-print">{t.expires(formatDay(expiresAt, lang))}</p>}
    </section>
  );
}

export function FoodBanksScreen(props: {
  t: Strings;
  lang: Language;
  created: CreatedRequest;
  fairShare: FairShare | null;
  list: FoodBankList | null;
  loading: boolean;
  error: unknown;
  retry: () => void;
  saving: boolean;
  saveError: unknown;
  onChoose: (ids: string[]) => void;
}) {
  const { t, lang, created, fairShare, list, loading, error, retry, saving, saveError, onChoose } = props;
  const [chosen, setChosen] = useState<string[]>(created.chosen_food_bank_ids ?? []);
  const [chooseError, setChooseError] = useState(false);

  const toggle = (id: string) => {
    setChooseError(false);
    setChosen(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));
  };

  return (
    <div className="stack">
      <CodeCard t={t} code={created.request_code} expiresAt={created.expires_at} lang={lang} />

      {fairShare && fairShare.household_size === created.household_size ? (
        <p className="fair-share-wording boxed">{fairShare.wording}</p>
      ) : (
        <p className="fair-share-wording boxed">{t.balance(created.received_this_week_lb, created.fair_share_lb)}</p>
      )}

      {loading && <Loading text={t.loadingFoodBanks} />}
      {!loading && error != null && <ErrorBox error={error} t={t} onRetry={retry} />}
      {!loading && list && list.food_banks.length === 0 && <p>{t.noFoodBanks}</p>}

      {!loading && list && list.food_banks.length > 0 && (
        <form
          className="stack"
          onSubmit={e => {
            e.preventDefault();
            if (chosen.length === 0) {
              setChooseError(true);
              document.querySelector<HTMLInputElement>('.bank-card input')?.focus();
              return;
            }
            onChoose(list.food_banks.map(b => b.food_bank_id).filter(id => chosen.includes(id)));
          }}
        >
          <fieldset className="bank-list" aria-describedby={chooseError ? 'choose-error' : undefined}>
            <legend className="sr-only">{t.foodBanksTitle}</legend>
            {chooseError && (
              <p className="field-error" id="choose-error" role="alert">
                {t.chooseError}
              </p>
            )}
            {list.food_banks.map(bank => {
              const isChosen = chosen.includes(bank.food_bank_id);
              const titleId = `bank-${bank.food_bank_id}`;
              return (
                <div key={bank.food_bank_id} className={isChosen ? 'bank-card chosen' : 'bank-card'}>
                  <label className="bank-head">
                    <input type="checkbox" checked={isChosen} onChange={() => toggle(bank.food_bank_id)} aria-describedby={`${titleId}-details`} />
                    <span className="bank-name" id={titleId}>
                      {bank.name}
                    </span>
                  </label>
                  <div id={`${titleId}-details`}>
                    <p className="meta">
                      <MapPin size={18} aria-hidden="true" />
                      {bank.area}
                    </p>
                    <p className={bank.fits_your_pickup_times ? 'fit yes' : 'fit no'}>
                      {bank.fits_your_pickup_times ? <Check size={18} aria-hidden="true" /> : <X size={18} aria-hidden="true" />}
                      {bank.fits_your_pickup_times ? t.fitsYes : t.fitsNo}
                    </p>
                    <h3>{t.pickupHours}</h3>
                    <ul className="windows">
                      {bank.pickup_windows.map(w => (
                        <li key={w.start}>
                          <Clock3 size={17} aria-hidden="true" />
                          {formatWindow(w, lang)}
                        </li>
                      ))}
                    </ul>
                    <h3>{t.committedHere}</h3>
                    {bank.committed_now.length === 0 ? (
                      <p className="muted">{t.nothingCommitted}</p>
                    ) : (
                      <ul className="produce">
                        {bank.committed_now.map(item => (
                          <li key={item.produce_id}>
                            <span>
                              {item.name} · {item.pounds} lb
                            </span>
                            {item.badges.length > 0 && (
                              <span className="tags">
                                {item.badges.map(b => (
                                  <span key={b} className="tag">
                                    {badgeLabel(b, t)}
                                  </span>
                                ))}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              );
            })}
          </fieldset>
          {saveError != null && <ErrorBox error={saveError} t={t} />}
          <button type="submit" className="primary" disabled={saving}>
            {saving ? t.saving : t.continue}
            <ArrowRight size={21} aria-hidden="true" />
          </button>
        </form>
      )}
    </div>
  );
}
