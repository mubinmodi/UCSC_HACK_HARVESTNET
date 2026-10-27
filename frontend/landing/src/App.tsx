// The HarvestNet landing page, served at the site root "/". It explains the project and sends each
// kind of visitor to the right app. Honesty rule (ADR 0002): no invented figures. The only number
// on the page comes from the live results API and is labeled synthetic.
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  ArrowRight,
  BarChart3,
  Building2,
  Handshake,
  Home,
  Languages,
  MailCheck,
  Scale,
  ShieldCheck,
  Snowflake,
  Sprout,
  Trash2,
  Users,
  FlaskConical,
  ExternalLink,
} from 'lucide-react';
import { STRINGS, type Language } from './i18n';
import { LoginChooser } from './LoginChooser';
import { loadResultsGlimpse, type ResultsGlimpse } from './results';

const REPO_URL = 'https://github.com/mubinmodi/UCSC_HACK_HARVESTNET';
const PHOTO = {
  title: 'Assorted vegetables on green plastic crate',
  author: 'Ashley Winkler',
  authorUrl: 'https://unsplash.com/@firlefanzski',
  url: 'https://unsplash.com/photos/53f1vbOG7y8',
};
const heroSrc = `${import.meta.env.BASE_URL}hero-produce-market.webp`;

const problemIcons = [Trash2, Users, Scale];
const featureIcons = [Languages, Scale, Handshake, MailCheck, Snowflake, BarChart3];
const whoIcons = [Home, Sprout, Building2];

function initialLanguage(): Language {
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en';
  return nav?.toLowerCase().startsWith('es') ? 'es' : 'en';
}

function Section({ id, title, lead, children, tone }: { id: string; title: string; lead?: string; children: ReactNode; tone?: 'alt' }) {
  return (
    <section className={tone === 'alt' ? 'section section-alt' : 'section'} id={id} aria-labelledby={`${id}-title`}>
      <div className="wrap">
        <header className="section-head">
          <h2 id={`${id}-title`}>{title}</h2>
          {lead && <p className="lead">{lead}</p>}
        </header>
        {children}
      </div>
    </section>
  );
}

export default function App() {
  const [language, setLanguage] = useState<Language>(initialLanguage);
  const [chooserOpen, setChooserOpen] = useState(false);
  const [glimpse, setGlimpse] = useState<ResultsGlimpse | null>(null);
  const t = STRINGS[language];
  const es = language === 'es';

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = es ? 'HarvestNet · Comida fresca para las familias' : 'HarvestNet · Fresh food for families, not the trash';
  }, [language, es]);

  useEffect(() => {
    let current = true;
    loadResultsGlimpse().then(value => current && setGlimpse(value));
    return () => {
      current = false;
    };
  }, []);

  const closeChooser = useCallback(() => setChooserOpen(false), []);

  return (
    <>
      <a
        className="skip-link"
        href="#main-content"
        onClick={event => {
          event.preventDefault();
          document.getElementById('main-content')?.focus();
        }}
      >
        {t.skip}
      </a>

      <header className="topbar hn-on-deep">
        <a className="hn-wordmark" href="/" aria-label="HarvestNet">
          <Sprout aria-hidden="true" />
          <span>HarvestNet</span>
        </a>
        <nav className="topnav" aria-label={t.navLabel}>
          <a href="#problem">{t.nav.problem}</a>
          <a href="#how">{t.nav.how}</a>
          <a href="#features">{t.nav.features}</a>
          <a href="#who">{t.nav.who}</a>
          <a href="#results">{t.nav.results}</a>
        </nav>
        <div className="topbar-actions">
          <button
            type="button"
            className="lang-toggle"
            lang={es ? 'en' : 'es'}
            aria-label={t.switchLanguageLabel}
            onClick={() => setLanguage(es ? 'en' : 'es')}
          >
            {t.switchLanguage}
          </button>
          <button type="button" className="hn-btn hn-btn--on-deep login" aria-haspopup="dialog" onClick={() => setChooserOpen(true)}>
            {t.login}
          </button>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
      <div className="hero hn-on-deep">
        <img className="hero-img" src={heroSrc} alt="" width={2000} height={1328} fetchPriority="high" decoding="async" />
        <div className="hero-scrim" aria-hidden="true" />

        <div className="wrap hero-body">
          <p className="hero-pill">
            <FlaskConical aria-hidden="true" size={16} />
            {t.heroPill}
          </p>
          <h1>{t.heroTitle}</h1>
          <p className="hero-lead">{t.heroLead}</p>
          <div className="hero-ctas">
            <a className="hn-btn hn-btn--on-deep" href="/household/">
              {t.ctaHousehold}
              <ArrowRight aria-hidden="true" size={20} />
            </a>
            <a className="hn-btn hn-btn--ghost-on-deep" href="/donor-dashboard/">
              {t.ctaStaff}
            </a>
            <a className="hn-btn hn-btn--ghost-on-deep" href="/results-strip/">
              {t.ctaResults}
            </a>
          </div>
          <p className="hero-note">
            <ShieldCheck aria-hidden="true" size={18} />
            {t.heroNote}
          </p>
        </div>
      </div>

        <Section id="problem" title={t.problemTitle} lead={t.problemLead}>
          <ul className="grid grid-3">
            {t.problems.map((item, index) => {
              const Icon = problemIcons[index] ?? Trash2;
              return (
                <li className="card hn-card" key={item.title}>
                  <span className="card-icon berry" aria-hidden="true"><Icon /></span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </li>
              );
            })}
          </ul>
        </Section>

        <Section id="how" title={t.howTitle} lead={t.howLead} tone="alt">
          <ol className="steps">
            {t.steps.map((step, index) => (
              <li className="step hn-card" key={step.title}>
                <span className="step-number" aria-hidden="true">{index + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <aside className="callout cold" aria-labelledby="cooler-title">
            <Snowflake aria-hidden="true" />
            <div>
              <h3 id="cooler-title">{t.coolerTitle}</h3>
              <p>{t.coolerBody}</p>
            </div>
          </aside>
        </Section>

        <Section id="features" title={t.featuresTitle} lead={t.featuresLead}>
          <ul className="grid grid-3">
            {t.features.map((item, index) => {
              const Icon = featureIcons[index] ?? Sprout;
              return (
                <li className="card hn-card" key={item.title}>
                  <span className={`card-icon ${index === 4 ? 'cold' : index === 3 ? 'berry' : 'leaf'}`} aria-hidden="true"><Icon /></span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </li>
              );
            })}
          </ul>
          <h3 className="built-with">{t.sponsorsTitle}</h3>
          <ul className="sponsors">
            {t.sponsors.map(item => (
              <li className="sponsor" key={item.title}>
                <strong>{item.title}</strong>
                <span>{item.body}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="who" title={t.whoTitle} tone="alt">
          <ul className="grid grid-3">
            {t.who.map((item, index) => {
              const Icon = whoIcons[index] ?? Home;
              return (
                <li className="card hn-card who-card" key={item.title}>
                  <span className="card-icon leaf" aria-hidden="true"><Icon /></span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <a className="card-link" href={item.href}>
                    {item.cta}
                    <ArrowRight aria-hidden="true" size={18} />
                  </a>
                </li>
              );
            })}
          </ul>
        </Section>

        <Section id="results" title={t.resultsTitle}>
          <div className="results-grid">
            <div>
              <p className="lead">{t.resultsBody}</p>
              <p>
                <a className="hn-btn hn-btn--secondary" href="/results-strip/">
                  <BarChart3 aria-hidden="true" size={20} />
                  {t.resultsLink}
                </a>
              </p>
            </div>
            {glimpse && (
              <div className="glimpse hn-card" role="group" aria-labelledby="glimpse-title">
                <h3 id="glimpse-title">{t.resultsPanelTitle(glimpse.scenarioId)}</h3>
                <p className="glimpse-lead">{t.resultsPanelLead}</p>
                <dl className="glimpse-rows">
                  <div>
                    <dt>{t.resultsFcfs}</dt>
                    <dd>
                      <b>{glimpse.firstComeFirstServed}</b> {t.resultsHouseholds}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.resultsRules}</dt>
                    <dd>
                      <b>{glimpse.rulesBased}</b> {t.resultsHouseholds}
                    </dd>
                  </div>
                </dl>
                <p className="glimpse-tags">
                  <span className="hn-pill hn-pill--warn">{es ? 'Sintético' : 'Synthetic'}</span>
                  <span className="hn-pill">{t.resultsRunMode(glimpse.runMode)}</span>
                </p>
                {glimpse.example && <p className="glimpse-example">{t.resultsExample}</p>}
              </div>
            )}
          </div>
        </Section>
      </main>

      <footer className="footer">
        <div className="wrap footer-grid">
          <div>
            <a className="hn-wordmark" href="/" aria-label="HarvestNet">
              <Sprout aria-hidden="true" />
              <span>HarvestNet</span>
            </a>
            <p>{t.footerTeam}</p>
            <p>
              <a href={REPO_URL} rel="noopener noreferrer">
                {t.footerRepo}
                <ExternalLink aria-hidden="true" size={14} />
              </a>
            </p>
          </div>
          <div>
            <p>
              {t.footerPhoto(PHOTO.title)}
              {es ? ' de ' : ' by '}
              <a href={PHOTO.authorUrl} rel="noopener noreferrer">{PHOTO.author}</a>
              {es ? ' en ' : ' on '}
              <a href={PHOTO.url} rel="noopener noreferrer">Unsplash</a>
              {es ? ' (Licencia de Unsplash).' : ' (Unsplash License).'}
            </p>
            <p>{t.footerHonest}</p>
          </div>
        </div>
      </footer>

      {chooserOpen && <LoginChooser t={t} onClose={closeChooser} />}
    </>
  );
}
