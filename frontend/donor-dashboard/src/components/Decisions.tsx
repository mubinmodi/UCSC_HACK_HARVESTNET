import { useRef, useState } from 'react';
import { api, UserInputError } from '../api';
import { formatDateTime, humanize, isoToLocalInput, lb, localInputToIso, nameOf, type Names } from '../format';
import type { Amendment, ApprovalRecorded, ApprovalRequest, ConditionGrade, IncomingOffer } from '../types';
import { useAction } from '../useLoad';
import { ErrorNote, Modal } from './ui';

function newReceiptId() {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `rcpt-${random}`;
}

/**
 * Approve or decline one exact version. A human must click, read the exact version,
 * and confirm. Nothing here approves on its own. A retry reuses the same receipt_id.
 */
export function ApprovalDecision({
  approval,
  organizationId,
  names,
  onRecorded,
}: {
  approval: ApprovalRequest;
  organizationId: string;
  names?: Names;
  onRecorded?: (result: ApprovalRecorded) => void;
}) {
  const [pending, setPending] = useState<'approve' | 'decline' | null>(null);
  const [result, setResult] = useState<ApprovalRecorded | null>(null);
  const receipts = useRef<Record<string, string>>({});
  const { busy, error, perform } = useAction();

  function receiptFor(decision: string) {
    const key = `${approval.lot_id}:${approval.version}:${approval.terms_hash}:${decision}`;
    receipts.current[key] ??= newReceiptId();
    return receipts.current[key];
  }

  async function confirm() {
    if (!pending) return;
    const recorded = await perform(() =>
      api.recordApproval({
        lot_id: approval.lot_id,
        version: approval.version,
        organization_id: organizationId,
        terms_hash: approval.terms_hash,
        decision: pending,
        receipt_id: receiptFor(pending),
      }),
    );
    if (recorded) {
      setResult(recorded);
      setPending(null);
      onRecorded?.(recorded);
    }
  }

  if (result)
    return (
      <div className="inline-status" role="status">
        <p>
          You {result.decision === 'approve' ? 'approved' : 'declined'} version {result.version}.{' '}
          {result.committed
            ? 'Every named organization approved this version, so it is now a commitment.'
            : 'Not committed yet.'}
        </p>
        <p>
          Approved by: {result.approved_by.map((o) => nameOf(names, o)).join(', ') || 'nobody'}. Still waiting for:{' '}
          {result.awaiting_approval_from.map((o) => nameOf(names, o)).join(', ') || 'nobody'}.
        </p>
      </div>
    );

  return (
    <>
      <div className="decision-actions">
        <button type="button" className="primary" onClick={() => setPending('approve')}>
          Approve version {approval.version}
        </button>
        <button type="button" className="outline danger" onClick={() => setPending('decline')}>
          Decline
        </button>
      </div>
      {pending && (
        <Modal title={pending === 'approve' ? `Approve version ${approval.version}?` : `Decline version ${approval.version}?`} onClose={() => setPending(null)} busy={busy}>
          <div className="modal-body">
            <p>
              You are {pending === 'approve' ? 'approving' : 'declining'} <b>version {approval.version}</b> of lot{' '}
              <b>{approval.lot_id}</b> for {nameOf(names, organizationId)}, exactly as written:
            </p>
            <p className="recommendation">{approval.summary}</p>
            <p className="subtle">
              Terms fingerprint <code>{shortHash(approval.terms_hash)}</code>. If the plan changes, this decision no longer counts and you will be asked again.
            </p>
            <ErrorNote message={error} />
            <button type="button" className={pending === 'approve' ? 'primary' : 'primary danger-fill'} disabled={busy} onClick={() => void confirm()}>
              {busy ? 'Saving…' : pending === 'approve' ? `Yes, approve version ${approval.version}` : `Yes, decline version ${approval.version}`}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

export const shortHash = (hash: string) => (hash.length > 20 ? `${hash.slice(0, 15)}…${hash.slice(-6)}` : hash);

/** The approval request, if any, for exactly this lot and version. */
export const findApproval = (approvals: ApprovalRequest[] | undefined, lotId: string, version: number) =>
  approvals?.find((a) => a.lot_id === lotId && a.version === version);

export function ApprovalCard({ approval, organizationId, onRecorded }: { approval: ApprovalRequest; organizationId: string; onRecorded?: () => void }) {
  const terms = approval.terms as Partial<import('../types').Draft>;
  const names = terms.names;
  return (
    <article className="approval-card">
      <div className="card-heading">
        <h3>
          {approval.change ? `${humanize(approval.change)}: ` : ''}
          {approval.lot_id}, version {approval.version}
        </h3>
        <span className="badge review">{humanize(approval.status)}</span>
      </div>
      <p>{approval.summary}</p>
      <p className="muted">
        Why you: {approval.why_you.map(humanize).join(', ')} · Requested {formatDateTime(approval.requested_at)}
        {approval.expires_at ? ` · Expires ${formatDateTime(approval.expires_at)}` : ''}
      </p>
      {Array.isArray(terms.allocations) && terms.allocations.length > 0 && (
        <details className="terms">
          <summary>Exact terms of version {approval.version}</summary>
          <ul>
            {terms.allocations.map((a, i) => (
              <li key={i}>
                {lb(a.pounds)} {humanize(a.produce_id)} to {nameOf(names, a.food_bank_id)}
              </li>
            ))}
          </ul>
          {Array.isArray(terms.transports) && (
            <ul>
              {terms.transports.map((t, i) => (
                <li key={i}>
                  {nameOf(names, t.food_bank_id)}: {t.mover === 'donor' ? 'donor drops off' : 'food bank collects'}, leaves{' '}
                  {formatDateTime(t.departs_at)}, arrives {formatDateTime(t.arrives_at)}
                </li>
              ))}
            </ul>
          )}
          {terms.reason && <p>Reason: “{terms.reason}”</p>}
          <p className="subtle">
            Terms fingerprint <code>{shortHash(approval.terms_hash)}</code>
          </p>
        </details>
      )}
      <ApprovalDecision approval={approval} organizationId={organizationId} names={names} onRecorded={() => onRecorded?.()} />
    </article>
  );
}

/** Counter: one amendment plus a reason, sent as this organization's next move. */
export function CounterDialog({
  offer,
  organizationId,
  onClose,
  onQueued,
}: {
  offer: IncomingOffer;
  organizationId: string;
  onClose: () => void;
  onQueued: (message: string) => void;
}) {
  const [kind, setKind] = useState<'set_pounds' | 'set_transport'>('set_pounds');
  const [produceId, setProduceId] = useState(offer.for_us[0]?.produce_id ?? '');
  const [pounds, setPounds] = useState('');
  const [mover, setMover] = useState<'donor' | 'food_bank'>(offer.transport?.mover === 'donor' ? 'food_bank' : 'donor');
  const [departs, setDeparts] = useState(isoToLocalInput(offer.transport?.departs_at));
  const [arrives, setArrives] = useState(isoToLocalInput(offer.transport?.arrives_at));
  const [reason, setReason] = useState('');
  const { busy, error, perform } = useAction();

  async function submit() {
    const queued = await perform(async () => {
      if (!reason.trim()) throw new UserInputError('Please give a reason for your counter.');
      let amendment: Amendment;
      if (kind === 'set_pounds') {
        const value = Number(pounds);
        if (!pounds || !Number.isFinite(value) || value < 0) throw new UserInputError('Enter the pounds you can take (0 or more).');
        amendment = { kind: 'set_pounds', produce_id: produceId, food_bank_id: organizationId, pounds: value };
      } else {
        const departsAt = localInputToIso(departs);
        const arrivesAt = localInputToIso(arrives);
        if (!departsAt || !arrivesAt) throw new UserInputError('Enter when it leaves and when it arrives.');
        amendment = { kind: 'set_transport', food_bank_id: organizationId, mover, departs_at: departsAt, arrives_at: arrivesAt };
      }
      return api.submitCounter(offer.lot_id, { organization_id: organizationId, version: offer.version, amendment, reason: reason.trim() });
    });
    if (queued) onQueued(queued.message);
  }

  return (
    <Modal title={`Counter version ${offer.version}`} onClose={onClose} busy={busy}>
      <form
        className="modal-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <fieldset>
          <legend>One change</legend>
          <div className="condition-options">
            <label>
              <input type="radio" name="counter-kind" checked={kind === 'set_pounds'} onChange={() => setKind('set_pounds')} />
              Change how many pounds we take
            </label>
            <label>
              <input type="radio" name="counter-kind" checked={kind === 'set_transport'} onChange={() => setKind('set_transport')} />
              Change who moves it, and when
            </label>
          </div>
        </fieldset>
        {kind === 'set_pounds' ? (
          <>
            <label>
              Item
              <select value={produceId} onChange={(e) => setProduceId(e.target.value)}>
                {offer.for_us.map((item) => (
                  <option key={item.produce_id} value={item.produce_id}>
                    {item.name} (offered {lb(item.pounds)})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Pounds we can take
              <input type="number" inputMode="decimal" min="0" step="any" value={pounds} onChange={(e) => setPounds(e.target.value)} required />
            </label>
          </>
        ) : (
          <>
            <label>
              Who moves it
              <select value={mover} onChange={(e) => setMover(e.target.value as 'donor' | 'food_bank')}>
                <option value="donor">Donor drops off</option>
                <option value="food_bank">We collect it</option>
              </select>
            </label>
            <label>
              Leaves at
              <input type="datetime-local" value={departs} onChange={(e) => setDeparts(e.target.value)} required />
            </label>
            <label>
              Arrives at
              <input type="datetime-local" value={arrives} onChange={(e) => setArrives(e.target.value)} required />
            </label>
          </>
        )}
        <label>
          Your reason
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} required placeholder="Explain your organization’s counter" />
        </label>
        <p className="subtle">A counter creates a new version. Approvals of the old version stop counting.</p>
        <ErrorNote message={error} />
        <button className="primary" disabled={busy}>
          {busy ? 'Sending…' : 'Send counter'}
        </button>
      </form>
    </Modal>
  );
}

function endOfToday() {
  const d = new Date();
  d.setHours(23, 59, 0, 0);
  return isoToLocalInput(d.toISOString());
}

/**
 * Condition check: approve as "use today" or decline with a reason.
 * Uses the core's proposed POST /lots/{lot_id}/condition-checks (docs/core/README.md, #9).
 */
export function ConditionCheck({
  lotId,
  version,
  produceId,
  produceName,
  organizationId,
  doubt,
  onRecorded,
}: {
  lotId: string;
  version: number;
  produceId: string;
  produceName: string;
  organizationId: string;
  doubt?: string | null;
  onRecorded?: () => void;
}) {
  const [choice, setChoice] = useState<'use_today' | 'decline'>('use_today');
  const [reason, setReason] = useState('');
  const [useBy, setUseBy] = useState(endOfToday());
  const [saved, setSaved] = useState<string | null>(null);
  const { busy, error, perform } = useAction();
  const name = `condition-${lotId}-${produceId}`;

  async function save() {
    const recorded = await perform(async () => {
      if (!reason.trim()) throw new UserInputError(choice === 'decline' ? 'Please give the reason for declining.' : 'Please note what you checked.');
      const usableUntil = localInputToIso(useBy);
      if (!usableUntil) throw new UserInputError('Enter when it must be used by.');
      const grade: ConditionGrade = choice === 'use_today' ? 'use_soon' : 'not_for_people';
      return api.submitConditionCheck(lotId, {
        organization_id: organizationId,
        version,
        produce_id: produceId,
        condition_grade: grade,
        usable_until: usableUntil,
        reason: reason.trim(),
      });
    });
    if (recorded) {
      setSaved(
        `${produceName}: ${choice === 'use_today' ? 'approved as use today' : 'declined'}. This made version ${recorded.version}; it still needs every approval.`,
      );
      onRecorded?.();
    }
  }

  return (
    <fieldset className="condition-check">
      <legend>
        Condition check: {produceName}
        {doubt ? <span className="warning"> · {doubt}</span> : null}
      </legend>
      <div className="condition-options">
        <label>
          <input type="radio" name={name} checked={choice === 'use_today'} onChange={() => setChoice('use_today')} />
          Approve: use today
        </label>
        <label>
          <input type="radio" name={name} checked={choice === 'decline'} onChange={() => setChoice('decline')} />
          Decline, with a reason
        </label>
      </div>
      <label className="reason-label">
        {choice === 'decline' ? 'Reason for declining' : 'What you checked'}
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} required />
      </label>
      <label className="reason-label">
        Use by
        <input type="datetime-local" value={useBy} onChange={(e) => setUseBy(e.target.value)} required />
      </label>
      <ErrorNote message={error} />
      <button type="button" className="outline" disabled={busy} onClick={() => void save()}>
        {busy ? 'Saving…' : 'Save condition check'}
      </button>
      {saved && (
        <p className="inline-status" role="status">
          {saved}
        </p>
      )}
      <p className="subtle">Proposed route in the core API; the example skeleton does not record condition checks yet.</p>
    </fieldset>
  );
}
