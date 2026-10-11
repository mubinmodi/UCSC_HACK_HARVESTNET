// The household page: three screens from docs/MVP_DESIGN.md §10.
//   1. About your household (answers, then read-back and consent)
//   2. Choose your food banks
//   3. Your pickup
// Every number shown comes from the API. Answers live only in memory for this visit.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Leaf, Sprout } from 'lucide-react';
import {
  api,
  isExampleData,
  type ChosenFoodBanks,
  type CreatedRequest,
  type FairShare,
  type FoodBankList,
  type Language,
  type Preview,
  type Release,
  type RequestStatus,
} from './api';
import { ExampleNotice } from './components';
import { emptyForm, toAnswers, toCreateBody, type FormState } from './form';
import { STRINGS } from './i18n';
import { parsePickupLink, type PickupLink } from './pickupLink';
import { AboutScreen } from './screens/AboutScreen';
import { ReviewScreen } from './screens/ReviewScreen';
import { FoodBanksScreen } from './screens/FoodBanksScreen';
import { PickupScreen } from './screens/PickupScreen';

type Screen = 'about' | 'review' | 'not_saved' | 'food_banks' | 'pickup';

const STEP: Record<Screen, 1 | 2 | 3> = { about: 1, review: 1, not_saved: 1, food_banks: 2, pickup: 3 };

interface Load<T> {
  loading: boolean;
  data: T | null;
  error: unknown;
}

const idle = <T,>(): Load<T> => ({ loading: false, data: null, error: null });

function initialLanguage(): Language {
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en';
  return nav?.toLowerCase().startsWith('es') ? 'es' : 'en';
}

function initialPickupLink(): PickupLink | null {
  return typeof window === 'undefined' ? null : parsePickupLink(window.location.hash);
}

export default function App() {
  const [linkedPickup, setLinkedPickup] = useState<PickupLink | null>(initialPickupLink);
  const [form, setForm] = useState<FormState>(() => emptyForm(linkedPickup?.language ?? initialLanguage()));
  const [screen, setScreen] = useState<Screen>(linkedPickup ? 'pickup' : 'about');
  const [fairShare, setFairShare] = useState<Load<FairShare>>(idle);
  const [preview, setPreview] = useState<Load<Preview>>(idle);
  const [creating, setCreating] = useState<Load<CreatedRequest>>(idle);
  const [foodBanks, setFoodBanks] = useState<Load<FoodBankList>>(idle);
  const [choosing, setChoosing] = useState<Load<ChosenFoodBanks>>(idle);
  const [status, setStatus] = useState<Load<RequestStatus>>(idle);
  const [requestCode, setRequestCode] = useState<string | null>(linkedPickup?.requestCode ?? null);
  const [releases, setReleases] = useState<Record<string, Release>>({});
  const [releasing, setReleasing] = useState<string | null>(null);
  const [releaseError, setReleaseError] = useState<{ pickupId: string; error: unknown } | null>(null);
  const [exampleSeen, setExampleSeen] = useState(false);
  const [fairShareTick, setFairShareTick] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  const lang = form.language;
  const t = STRINGS[lang];
  const step = STEP[screen];

  const note = useCallback(<T extends object>(body: T): T => {
    if (isExampleData(body as { mode: string })) setExampleSeen(true);
    return body;
  }, []);

  const update = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => setForm(f => ({ ...f, [key]: value })), []);

  // A pickup email opens this page on one pickup. Reading the link only loads its status;
  // releasing it still takes an explicit button tap and confirmation.
  useEffect(() => {
    const openLink = () => {
      const link = parsePickupLink(window.location.hash);
      if (!link) return;
      setLinkedPickup(link);
      setForm(f => ({ ...f, language: link.language }));
      setRequestCode(link.requestCode);
      setStatus(idle);
      setReleases({});
      setScreen('pickup');
    };
    window.addEventListener('hashchange', openLink);
    return () => window.removeEventListener('hashchange', openLink);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = lang === 'es' ? 'HarvestNet · Su hogar' : 'HarvestNet · Your household';
  }, [lang]);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo?.(0, 0);
    headingRef.current?.focus();
  }, [screen]);

  // Fair share for the chosen size, from the API (never calculated here).
  useEffect(() => {
    if (form.size === null) {
      setFairShare(idle);
      return;
    }
    let current = true;
    setFairShare(s => ({ ...s, loading: true, error: null }));
    const timer = setTimeout(() => {
      api.getFairShare(form.size as number, lang).then(
        body => current && setFairShare({ loading: false, data: note(body), error: null }),
        error => current && setFairShare({ loading: false, data: null, error }),
      );
    }, 300);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [form.size, lang, fairShareTick, note]);

  const runPreview = useCallback(() => {
    setPreview({ loading: true, data: null, error: null });
    api.previewRequest(toAnswers(form)).then(
      body => setPreview({ loading: false, data: note(body), error: null }),
      error => setPreview({ loading: false, data: null, error }),
    );
  }, [form, note]);

  const loadFoodBanks = useCallback(
    (code: string) => {
      setFoodBanks({ loading: true, data: null, error: null });
      api.listFoodBanks(form.neighborhood.trim(), code).then(
        body => setFoodBanks({ loading: false, data: note(body), error: null }),
        error => setFoodBanks({ loading: false, data: null, error }),
      );
    },
    [form.neighborhood, note],
  );

  const loadStatus = useCallback(
    (code: string, language: Language) => {
      setStatus(s => ({ ...s, loading: true, error: null }));
      api.getRequest(code, language).then(
        body => setStatus({ loading: false, data: note(body), error: null }),
        error => setStatus(s => ({ loading: false, data: s.data, error })),
      );
    },
    [note],
  );

  // The pickup screen's wording comes from the API in the household's language.
  useEffect(() => {
    if (screen === 'pickup' && requestCode) loadStatus(requestCode, lang);
  }, [screen, requestCode, lang, linkedPickup?.pickupId, loadStatus]);

  // Switching language on the review screen asks again, so the read-back matches.
  const screenRef = useRef(screen);
  screenRef.current = screen;
  const previewRef = useRef(runPreview);
  previewRef.current = runPreview;
  useEffect(() => {
    if (screenRef.current === 'review') previewRef.current();
  }, [lang]);

  function review() {
    setScreen('review');
    runPreview();
  }

  function consent(yes: boolean) {
    if (!yes) {
      setForm(f => ({ ...f, email: '' }));
      setScreen('not_saved');
      return;
    }
    setCreating({ loading: true, data: null, error: null });
    api.createRequest(toCreateBody(form)).then(
      body => {
        note(body);
        setCreating({ loading: false, data: body, error: null });
        setForm(f => ({ ...f, email: '' })); // write-only: not kept once sent
        setRequestCode(body.request_code);
        setScreen('food_banks');
        loadFoodBanks(body.request_code);
      },
      error => setCreating({ loading: false, data: null, error }),
    );
  }

  function choose(ids: string[]) {
    if (!requestCode) return;
    setChoosing({ loading: true, data: null, error: null });
    api.chooseFoodBanks(requestCode, ids).then(
      body => {
        setChoosing({ loading: false, data: note(body), error: null });
        setScreen('pickup');
      },
      error => setChoosing({ loading: false, data: null, error }),
    );
  }

  function release(pickupId: string) {
    if (!requestCode) return;
    setReleasing(pickupId);
    setReleaseError(null);
    api.releasePickup(pickupId, requestCode).then(
      body => {
        note(body);
        setReleases(r => ({ ...r, [pickupId]: body }));
        setReleasing(null);
      },
      error => {
        setReleaseError({ pickupId, error });
        setReleasing(null);
      },
    );
  }

  function lookup(code: string) {
    setLinkedPickup(null);
    setRequestCode(code);
    setStatus(idle);
    setScreen('pickup');
  }

  function startOver() {
    if (linkedPickup) window.history.replaceState(null, '', window.location.pathname + window.location.search);
    setLinkedPickup(null);
    setForm(emptyForm(lang));
    setPreview(idle);
    setCreating(idle);
    setFoodBanks(idle);
    setChoosing(idle);
    setStatus(idle);
    setRequestCode(null);
    setReleases({});
    setScreen('about');
  }

  const titles: Record<Screen, string> = {
    about: t.aboutTitle,
    review: t.reviewTitle,
    not_saved: t.notSavedTitle,
    food_banks: t.foodBanksTitle,
    pickup: t.pickupTitle,
  };
  const intros: Record<Screen, string> = {
    about: `${t.aboutIntro} ${t.noPersonalInfo}`,
    review: t.reviewIntro,
    not_saved: t.notSavedBody,
    food_banks: t.foodBanksIntro,
    pickup: '',
  };

  return (
    <div className="page">
      <a className="skip-link" href="#main-content" onClick={event => {
        // Keep an emailed pickup's fragment in the URL while moving keyboard focus.
        if (linkedPickup) {
          event.preventDefault();
          document.getElementById('main-content')?.focus();
        }
      }}>
        {lang === 'es' ? 'Saltar al contenido' : 'Skip to content'}
      </a>
      <div className="shell">
        <header className="brand">
          <div>
            <p className="brand-name">
              <Sprout aria-hidden="true" />
              <span>HarvestNet</span>
            </p>
            <p className="tagline">{t.tagline}</p>
          </div>
          <button
            type="button"
            className="language"
            lang={lang === 'es' ? 'en' : 'es'}
            aria-label={t.switchLanguageLabel}
            onClick={() => update('language', lang === 'es' ? 'en' : 'es')}
          >
            {t.switchLanguage}
          </button>
        </header>
        <main className="content" id="main-content" tabIndex={-1}>
          <div className="step-label">
            <span>{t.step(step)}</span>
            <span>{t.stepNames[step - 1]}</span>
          </div>
          <div
            className="progress"
            role="progressbar"
            aria-valuemin={1}
            aria-valuemax={3}
            aria-valuenow={step}
            aria-valuetext={`${t.step(step)}: ${t.stepNames[step - 1]}`}
            aria-label={t.step(step)}
          >
            {[1, 2, 3].map(n => (
              <span key={n} className={n <= step ? 'active' : ''} />
            ))}
          </div>
          <h1 ref={headingRef} tabIndex={-1}>
            {titles[screen]}
          </h1>
          {intros[screen] && <p className="intro">{intros[screen]}</p>}

          {exampleSeen && <ExampleNotice t={t} />}

          {screen === 'about' && (
            <AboutScreen
              t={t}
              form={form}
              update={update}
              fairShare={{ ...fairShare, retry: () => setFairShareTick(n => n + 1) }}
              onReview={review}
              onLookup={lookup}
            />
          )}

          {screen === 'review' && (
            <ReviewScreen
              t={t}
              form={form}
              preview={preview.data}
              loading={preview.loading}
              error={preview.error}
              retry={runPreview}
              saving={creating.loading}
              saveError={creating.error}
              onEdit={() => setScreen('about')}
              onConsent={consent}
            />
          )}

          {screen === 'not_saved' && (
            <div className="stack">
              <button type="button" className="secondary" onClick={() => setScreen('about')}>
                {t.editAnswers}
              </button>
              <button type="button" className="secondary" onClick={startOver}>
                {t.startOver}
              </button>
            </div>
          )}

          {screen === 'food_banks' && creating.data && (
            <FoodBanksScreen
              t={t}
              lang={lang}
              created={creating.data}
              fairShare={fairShare.data}
              list={foodBanks.data}
              loading={foodBanks.loading}
              error={foodBanks.error}
              retry={() => requestCode && loadFoodBanks(requestCode)}
              saving={choosing.loading}
              saveError={choosing.error}
              onChoose={choose}
            />
          )}

          {screen === 'pickup' && requestCode && (
            <>
              <PickupScreen
                t={t}
                lang={lang}
                status={status.data}
                loading={status.loading}
                error={status.error}
                retry={() => loadStatus(requestCode, lang)}
                emails={creating.data?.emails ?? false}
                targetPickupId={linkedPickup?.pickupId ?? null}
                releases={releases}
                releasing={releasing}
                releaseError={releaseError}
                onRelease={release}
                onChangeCode={startOver}
              />
              {creating.data && (
                <button type="button" className="secondary back" onClick={() => setScreen('food_banks')}>
                  {t.back}
                </button>
              )}
            </>
          )}

          <p className="preview-note">
            <Leaf size={14} aria-hidden="true" />
            {t.noPersonalInfo}
          </p>
        </main>
      </div>
      <footer>{t.footer}</footer>
    </div>
  );
}
