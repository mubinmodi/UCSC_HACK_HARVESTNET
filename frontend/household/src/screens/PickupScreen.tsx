import { useState } from 'react';
import { CalendarX, Copy, Droplets, Lightbulb, RefreshCw, Store } from 'lucide-react';
import { showablePickups, type Language, type Release, type RequestStatus } from '../api';
import { ErrorBox, Loading } from '../components';
import { formatDay, formatWindow, type Strings } from '../i18n';

export function PickupScreen(props: {
  t: Strings;
  lang: Language;
  status: RequestStatus | null;
  loading: boolean;
  error: unknown;
  retry: () => void;
  waitingMessage: string | null;
  texts: boolean;
  releases: Record<string, Release>;
  releasing: string | null;
  releaseError: { pickupId: string; error: unknown } | null;
  onRelease: (pickupId: string) => void;
}) {
  const { t, lang, status, loading, error, retry, waitingMessage, texts, releases, releasing, releaseError, onRelease } = props;
  const [confirming, setConfirming] = useState<string | null>(null);
  const [copyNote, setCopyNote] = useState('');

  if (loading && !status) return <Loading text={t.loadingPickup} />;
  if (!status) return error != null ? <ErrorBox error={error} t={t} onRetry={retry} /> : null;

  const pickups = showablePickups(status.pickups);
  const code = status.request_code;

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopyNote(t.copied);
    } catch {
      setCopyNote(t.copyFailed(code));
    }
  }

  return (
    <div className="stack">
      <section className="pickup-card" aria-labelledby="pickup-code-title">
        <h2 id="pickup-code-title" className="eyebrow">
          {t.codeIntro}
        </h2>
        <div className="code-area">
          <p className="code">{code}</p>
          <button type="button" onClick={copy}>
            <Copy size={18} aria-hidden="true" />
            {t.copyCode}
          </button>
        </div>
        <p>{t.codeKeep}</p>
        <p className="small-print" role="status">
          {copyNote}
        </p>
        <div className="balance">
          <p>{t.balance(status.received_this_week_lb, status.fair_share_lb)}</p>
        </div>
        {status.expires_at && <p className="small-print">{t.expires(formatDay(status.expires_at, lang))}</p>}
      </section>

      {error != null && <ErrorBox error={error} t={t} onRetry={retry} />}

      {pickups.length === 0 && <p className="waiting">{waitingMessage || (texts ? t.waitingTexts : t.waiting)}</p>}

      {pickups.map(pickup => {
        const released = releases[pickup.pickup_id];
        const titleId = `pickup-${pickup.pickup_id}`;
        return (
          <section key={pickup.pickup_id} className={released ? 'pickup released' : 'pickup'} aria-labelledby={titleId}>
            <p className="eyebrow dark">{released ? t.released : t.readyTitle}</p>
            <h2 id={titleId}>
              <Store size={24} aria-hidden="true" />
              {pickup.food_bank_name}
            </h2>
            <p className="when">{formatWindow(pickup.window, lang)}</p>
            <ul className="produce">
              {pickup.items.map(item => (
                <li key={item.produce_id}>
                  {item.name} · {item.pounds} lb
                </li>
              ))}
            </ul>
            <p className="total">{t.total(pickup.pounds)}</p>
            <p className="api-text">{pickup.wording}</p>
            <p className="wash">
              <Droplets size={18} aria-hidden="true" />
              {t.wash}
            </p>

            {released ? (
              <p className="released-note" role="status">
                {released.message}
              </p>
            ) : confirming === pickup.pickup_id ? (
              <div className="confirm-release" role="group" aria-labelledby={`${titleId}-confirm`}>
                <p id={`${titleId}-confirm`}>{t.confirmRelease}</p>
                {releaseError?.pickupId === pickup.pickup_id && <ErrorBox error={releaseError.error} t={t} />}
                <div className="actions">
                  <button type="button" className="danger" disabled={releasing === pickup.pickup_id} onClick={() => onRelease(pickup.pickup_id)}>
                    {releasing === pickup.pickup_id ? t.releasing : t.confirmReleaseYes}
                  </button>
                  <button type="button" className="secondary" disabled={releasing === pickup.pickup_id} onClick={() => setConfirming(null)}>
                    {t.keepPickup}
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="secondary" onClick={() => setConfirming(pickup.pickup_id)}>
                <CalendarX size={20} aria-hidden="true" />
                {t.cantMakeIt}
              </button>
            )}
          </section>
        );
      })}

      {status.market_match_tip && (
        <p className="tip">
          <Lightbulb size={20} aria-hidden="true" />
          <span>
            <strong>{t.marketTip}:</strong> {status.market_match_tip}
          </span>
        </p>
      )}

      <button type="button" className="secondary" onClick={retry} disabled={loading}>
        <RefreshCw size={19} aria-hidden="true" />
        {loading ? t.loadingPickup : t.refresh}
      </button>
    </div>
  );
}
