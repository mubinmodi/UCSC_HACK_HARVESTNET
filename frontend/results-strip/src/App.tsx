import { useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, Sprout, Trash2, Users } from 'lucide-react';
import { resultsApi, type MethodId, type MethodResult, type Results } from './api';

// The four methods, always in this order. Labels only: every number comes from the API.
const methods: [MethodId, string, string][] = [
  ['first_come_first_served', 'First-come-first-served', 'Primero en llegar'],
  ['nearest_food_bank', 'Nearest food bank', 'Banco de alimentos más cercano'],
  ['rules_based', 'Rules-based negotiators', 'Negociadores con reglas'],
  ['llm', 'LLM negotiators', 'Negociadores con IA'],
];

const modes: Record<string, [string, string]> = {
  live: ['Live', 'En vivo'],
  replay: ['Replay', 'Repetición'],
  synthetic: ['Synthetic', 'Sintético'],
};

const has = (value: number | null | undefined): value is number => value !== null && value !== undefined;

export default function App() {
  const [language, setLanguage] = useState<'en' | 'es'>('en');
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState('');
  const es = language === 'es';
  const t = (en: string, spanish: string) => es ? spanish : en;
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  useEffect(() => { resultsApi.load().then(setResults).catch((e: Error) => setError(e.message)); }, []);

  const example = results ? results.measured !== true || results.synthetic === true : false;
  const mode = results ? modes[results.run_mode] : undefined;
  const headline = new Set(results?.headline ?? []);
  // Display formatting only: the API sends coverage as a share (0.25), shown as a percent.
  const percent = new Intl.NumberFormat(language, { style: 'percent', maximumFractionDigits: 1 });

  const metric = (key: string, icon: ReactNode, label: string, value: number | null | undefined, show: (v: number) => string) =>
    <div className="metric">
      <dt>{icon}{label}{headline.has(key) && <span className="headline-tag">{t('Headline', 'Principal')}</span>}</dt>
      <dd>{has(value) ? show(value) : <span className="missing">{t('Not measured yet', 'Aún sin medir')}</span>}</dd>
    </div>;

  const card = ([id, en, spanish]: [MethodId, string, string], run: MethodResult | undefined) => {
    const notRun = !run || run.status === 'not_run';
    return <article className="run" key={id}>
      <h2>{t(en, spanish)}</h2>
      {notRun
        ? <span className="mode mode-unknown">{t('Not run', 'Sin ejecutar')}</span>
        : <span className={`mode mode-${mode ? results!.run_mode : 'unknown'}`}>{mode ? t(...mode) : t('Mode unknown', 'Modo desconocido')}</span>}
      {notRun && run?.reason && <p className="reason">{run.reason}</p>}
      <dl>
        {metric('produce_wasted_lb', <Trash2 aria-hidden="true"/>, t('Produce wasted', 'Producto desperdiciado'), run?.produce_wasted_lb, v => `${v} lb`)}
        {metric('worst_served_coverage', <Sprout aria-hidden="true"/>, t('Worst-served coverage', 'Cobertura del peor atendido'), run?.worst_served_coverage, v => percent.format(v))}
        {metric('households_reached', <Users aria-hidden="true"/>, t('Households reached', 'Hogares alcanzados'), run?.households_reached, v => String(v))}
      </dl>
      {has(run?.invalid_commitments) && <p className="invalid">{t('Invalid commitments', 'Compromisos inválidos')}: <b>{run!.invalid_commitments}</b></p>}
    </article>;
  };

  return <div className="page">
    <header className="strip-header">
      <div>
        <div className="brand-name"><Sprout aria-hidden="true"/><span>HarvestNet</span></div>
        <h1>{results ? t('Results', 'Resultados') + ' · ' + results.scenario_id : error ? t('Results unavailable', 'Resultados no disponibles') : t('Loading results…', 'Cargando resultados…')}</h1>
      </div>
      <button className="language" onClick={() => setLanguage(es ? 'en' : 'es')}>{es ? 'English' : 'Español'}</button>
    </header>

    {example && <p className="example-banner" role="note"><AlertTriangle aria-hidden="true"/>{t('Example data. These numbers are not measured results.', 'Datos de ejemplo. Estos números no son resultados medidos.')}</p>}
    {error && <p className="error" role="status">{t("Couldn't load results", 'No se pudieron cargar los resultados')} ({error}).</p>}

    {results && <section className="runs" aria-label={t('Results by method', 'Resultados por método')}>
      {methods.map(m => card(m, results.methods.find(r => r.method === m[0])))}
    </section>}

    <footer className="legend">
      <p><b>{t('Produce wasted', 'Producto desperdiciado')}:</b> {t('pounds not collected by the end of the scenario. Lower is better.', 'libras no recogidas al final del escenario. Menos es mejor.')}</p>
      <p><b>{t('Worst-served coverage', 'Cobertura del peor atendido')}:</b> {t('share of the weekly fair share received by the worst-served households. Higher is better.', 'parte de la porción justa semanal que recibieron los hogares peor atendidos. Más es mejor.')}</p>
      <p><b>{t('Households reached', 'Hogares alcanzados')}:</b> {t('counted by pickup confirmations.', 'contados por confirmaciones de recogida.')}</p>
      <p><b>{t('Live', 'En vivo')}</b> {t('ran just now', 'se ejecutó ahora')} · <b>{t('Replay', 'Repetición')}</b> {t('a recorded run played back', 'una ejecución grabada')} · <b>{t('Synthetic', 'Sintético')}</b> {t('made-up inputs for testing', 'datos inventados para pruebas')}</p>
      {results?.note && <p className="source">{results.note}</p>}
      <p className="source">{t('Source', 'Fuente')}: {resultsApi.source}</p>
    </footer>
  </div>;
}
