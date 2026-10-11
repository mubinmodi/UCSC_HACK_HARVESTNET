import { History, MessageSquareWarning } from 'lucide-react';
import { api } from '../api';
import { describeChange, formatDateTime, humanize, lb, moverText, nameOf, type Names } from '../format';
import type { Lot, LotItem, LotVersion } from '../types';
import { useLoad } from '../useLoad';
import { Badge, DataLabel, ErrorNote, Photo } from './ui';

/** Every draft version: who proposed it, the move, the change, and the reason. */
export function VersionHistory({ lotId, names }: { lotId: string; names?: Names }) {
  const { data, error, loading } = useLoad(() => api.listLotVersions(lotId), [lotId]);
  return (
    <div className="versions">
      <h3>
        <History aria-hidden="true" size={18} /> Versions of the draft agreement
      </h3>
      {loading && <p role="status">Loading versions…</p>}
      <ErrorNote message={error} />
      {data && (
        <>
          <ol className="version-list">
            {data.versions.map((v) => (
              <li key={v.version} className={v.version === data.current_version ? 'current' : undefined}>
                <div className="version-head">
                  <strong>Version {v.version}</strong>
                  <span>
                    {nameOf(names, v.proposer_id)} · {humanize(v.move)}
                  </span>
                  {v.version === data.current_version && <Badge text="current" />}
                </div>
                <p className="version-change">{describeChange(v.change, names)}</p>
                <p className="version-reason">
                  <span className="sr-only">Reason: </span>“{v.reason}”
                </p>
              </li>
            ))}
          </ol>
          <DataLabel data={data} />
        </>
      )}
    </div>
  );
}

/** The latest reason each organization gave, for a preserved disagreement. */
export function EachSidesReason({ versions, names }: { versions: LotVersion[]; names?: Names }) {
  const latest = new Map<string, LotVersion>();
  for (const v of versions) latest.set(v.proposer_id, v);
  return (
    <ul className="sides">
      {[...latest.values()].map((v) => (
        <li key={v.proposer_id}>
          <strong>{nameOf(names, v.proposer_id)}</strong> (version {v.version}): “{v.reason}”
        </li>
      ))}
    </ul>
  );
}

export function disagreementText(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'object' && value && 'reason' in value && typeof (value as { reason: unknown }).reason === 'string')
    return (value as { reason: string }).reason;
  return JSON.stringify(value);
}

/**
 * Where an item goes and who moves it. Uses the item's `split` (contract); if a server
 * leaves it out, the same facts are read from the current draft's allocations and transports.
 */
function splitOf(lot: Lot, produceId: string, split: LotItem['split']) {
  if (split && split.length > 0) return split;
  const transports = lot.draft?.transports ?? [];
  return (lot.draft?.allocations ?? [])
    .filter((a) => a.produce_id === produceId)
    .map((a) => ({ food_bank_id: a.food_bank_id, pounds: a.pounds, mover: transports.find((t) => t.food_bank_id === a.food_bank_id)?.mover ?? '' }));
}

/** A lot's live status, item by item, with the current draft and approvals. */
export function LotStatus({ lot }: { lot: Lot }) {
  const names = lot.draft?.names;
  const disagreement = disagreementText(lot.disagreement);
  const transports = lot.draft?.transports ?? [];
  return (
    <div className="lot-status">
      <div className="lot-summary">
        <div>
          <h3>{lot.lot_id}</h3>
          <p className="muted">
            Version {lot.current_version} · leave by {formatDateTime(lot.deadline)}
          </p>
        </div>
        <Badge text={lot.status} />
      </div>
      <ul className="item-status-list">
        {lot.items.map((item) => (
          <li key={item.produce_id} className="item-status">
            <Photo produceId={item.produce_id} small />
            <div className="card-body">
              <div className="card-heading">
                <strong>
                  {item.name} · {lb(item.pounds)}
                </strong>
                <Badge text={item.status} />
              </div>
              {splitOf(lot, item.produce_id, item.split).length > 0 ? (
                <ul className="split">
                  {splitOf(lot, item.produce_id, item.split).map((s) => (
                    <li key={s.food_bank_id}>
                      {lb(s.pounds)} to {nameOf(names, s.food_bank_id)} · {moverText(s.mover)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No food bank yet.</p>
              )}
              {item.unclaimed_lb !== undefined && item.unclaimed_lb > 0 && (
                <p className="warning">
                  {lb(item.unclaimed_lb)} unclaimed{item.unclaimed_reason ? `: ${item.unclaimed_reason}` : ''}
                </p>
              )}
              {item.households_reached !== undefined && (
                <p className="muted">Households reached: {item.households_reached}</p>
              )}
              {item.condition_doubt && <p className="warning">Condition check needed: {item.condition_doubt}</p>}
            </div>
          </li>
        ))}
      </ul>
      {transports.length > 0 && (
        <div className="transport-list">
          <h4>Who moves it</h4>
          <ul>
            {transports.map((t, i) => (
              <li key={`${t.food_bank_id}-${i}`}>
                {nameOf(names, t.food_bank_id)}: {moverText(t.mover)}, leaves {formatDateTime(t.departs_at)}, arrives{' '}
                {formatDateTime(t.arrives_at)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {lot.draft?.reason && (
        <p className="recommendation">
          <b>Why this version ({nameOf(names, lot.draft.proposer_id)}):</b> {lot.draft.reason}
        </p>
      )}
      <div className="approval-state">
        <p>
          <b>Approved this version:</b>{' '}
          {lot.approvals.filter((a) => a.decision === 'approve').map((a) => nameOf(names, a.organization_id)).join(', ') || 'nobody yet'}
        </p>
        <p>
          <b>Still waiting for:</b> {lot.awaiting_approval_from.map((o) => nameOf(names, o)).join(', ') || 'nobody'}
        </p>
        <p className="subtle">Nothing is promised until every named organization approves the same version.</p>
      </div>
      {disagreement && (
        <div className="disagreement" role="note">
          <MessageSquareWarning aria-hidden="true" size={18} />
          <p>
            <b>Preserved disagreement:</b> {disagreement}
          </p>
        </div>
      )}
    </div>
  );
}
