import { useState } from 'react';
import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock,
  KeyRound,
  MessageSquareWarning,
  Plus,
  Refrigerator,
  Snowflake,
  Trash2,
  Truck,
  Users,
  XCircle,
} from 'lucide-react';
import { api, UserInputError } from '../api';
import { formatDateTime, formatWindow, humanize, isoToLocalInput, lb, localInputToIso, moverText } from '../format';
import type {
  ApprovalRequest,
  Capacity,
  Disagreement,
  Disruption,
  FoodBankDashboard,
  FoodBankStatusInput,
  IncomingOffer,
  PickupConfirmed,
  ReasonCard,
} from '../types';
import { useAction, useLoad } from '../useLoad';
import { ApprovalDecision, ConditionCheck, CounterDialog, findApproval } from './Decisions';
import { EachSidesReason, LotStatus, VersionHistory, disagreementText } from './LotViews';
import { Badge, DataLabel, ErrorNote, Modal, PageHeading, Photo, Section } from './ui';

export function FoodBankPage({ foodBankId }: { foodBankId: string }) {
  const board = useLoad(() => api.getFoodBankDashboard(foodBankId), [foodBankId]);
  const approvals = useLoad(() => api.listApprovals(foodBankId), [foodBankId]);
  const [notice, setNotice] = useState('');

  const refresh = () => {
    void board.reload();
    void approvals.reload();
  };

  return (
    <>
      <PageHeading icon={<Building2 />} title={board.data ? board.data.name : 'Food bank dashboard'} subtitle="Today’s capacity, incoming offers, your households’ fair-share gap as counts, and pickups." />
      {board.loading && !board.data && <p role="status">Loading dashboard…</p>}
      <ErrorNote message={board.error} />
      {board.data && (
        <>
          <DataLabel data={board.data} />
          <p className="notice" role="status">
            {notice}
          </p>
          <CapacityPanel foodBankId={foodBankId} capacity={board.data.capacity} onSaved={(m) => (setNotice(m), refresh())} />
          <GapPanel board={board.data} />
          <Disruptions disruptions={board.data.disruptions ?? []} approvals={approvals.data?.approvals} foodBankId={foodBankId} onChanged={refresh} />
          <IncomingOffers
            board={board.data}
            approvals={approvals.data?.approvals}
            approvalsError={approvals.error}
            onChanged={(m) => (m && setNotice(m), refresh())}
          />
          <Disagreements items={board.data.disagreements} />
          <Arrivals board={board.data} />
          <PickupConfirm foodBankId={foodBankId} />
        </>
      )}
    </>
  );
}

function CapacityPanel({ foodBankId, capacity, onSaved }: { foodBankId: string; capacity: Capacity; onSaved: (message: string) => void }) {
  const [editing, setEditing] = useState(false);
  const storage = capacity.storage ?? [];
  const cooler = capacity.cooler;
  return (
    <Section
      title="Today’s capacity"
      icon={<Refrigerator aria-hidden="true" size={20} />}
      aside={
        <button type="button" className="link-button" onClick={() => setEditing(true)}>
          Update storage, hours, truck
        </button>
      }
    >
      <div className="resource-grid">
        <div className="resource">
          <strong>Storage free</strong>
          {storage.length === 0 && <p className="muted">Not set</p>}
          {storage.map((s, i) => (
            <div key={i} className="resource-lines">
              <p>
                <b>{lb(s.cold_free_lb)}</b> cold · <b>{lb(s.dry_free_lb)}</b> dry
              </p>
              <small>{formatWindow(s.window)}</small>
            </div>
          ))}
        </div>
        <div className="resource">
          <strong>Truck</strong>
          {capacity.truck ? (
            <div className="resource-lines">
              <p>
                <Truck aria-hidden="true" size={18} /> <b>{lb(capacity.truck.capacity_lb)}</b>
                {capacity.truck.refrigerated ? ' · refrigerated' : ' · not refrigerated'}
              </p>
              <small>Free {formatWindow(capacity.truck.window)}</small>
            </div>
          ) : (
            <p className="muted">No truck today</p>
          )}
        </div>
        <div className="resource">
          <strong>Cooler</strong>
          {cooler ? (
            <div className="resource-lines">
              <p>
                <Snowflake aria-hidden="true" size={18} /> <b className={cooler.status === 'failed' ? 'red' : undefined}>{humanize(cooler.status)}</b>
                {cooler.temperature_c !== undefined ? ` · ${cooler.temperature_c} °C` : ''}
              </p>
              <small>
                {cooler.source ? `Reading from ${cooler.source}` : 'Reading source not given'}
                {cooler.synthetic ? ' (synthetic)' : ''}
              </small>
            </div>
          ) : (
            <p className="muted">No reading</p>
          )}
        </div>
      </div>
      <div className="hours">
        <Clock aria-hidden="true" />
        <div>
          <strong>Pickup hours</strong>
          {(capacity.pickup_windows ?? []).length === 0 ? (
            <p>Not set</p>
          ) : (
            (capacity.pickup_windows ?? []).map((w, i) => <p key={i}>{formatWindow(w)}</p>)
          )}
        </div>
      </div>
      {editing && (
        <StatusEditor
          foodBankId={foodBankId}
          capacity={capacity}
          onClose={() => setEditing(false)}
          onSaved={(m) => {
            setEditing(false);
            onSaved(m);
          }}
        />
      )}
    </Section>
  );
}

interface WindowRow {
  start: string;
  end: string;
}
interface StorageRow extends WindowRow {
  cold: string;
  dry: string;
}

function StatusEditor({ foodBankId, capacity, onClose, onSaved }: { foodBankId: string; capacity: Capacity; onClose: () => void; onSaved: (m: string) => void }) {
  const [storage, setStorage] = useState<StorageRow[]>(
    (capacity.storage ?? []).map((s) => ({ start: isoToLocalInput(s.window.start), end: isoToLocalInput(s.window.end), cold: String(s.cold_free_lb), dry: String(s.dry_free_lb) })),
  );
  const [hours, setHours] = useState<WindowRow[]>((capacity.pickup_windows ?? []).map((w) => ({ start: isoToLocalInput(w.start), end: isoToLocalInput(w.end) })));
  const [truck, setTruck] = useState({
    start: isoToLocalInput(capacity.truck?.window.start),
    end: isoToLocalInput(capacity.truck?.window.end),
    refrigerated: capacity.truck?.refrigerated ?? false,
    capacity: capacity.truck ? String(capacity.truck.capacity_lb) : '',
  });
  const { busy, error, perform } = useAction();

  function toWindow(row: WindowRow, what: string) {
    const start = localInputToIso(row.start);
    const end = localInputToIso(row.end);
    if (!start || !end) throw new UserInputError(`Enter a start and end for ${what}.`);
    if (new Date(end) <= new Date(start)) throw new UserInputError(`${humanize(what)} must end after it starts.`);
    return { start, end };
  }
  function pounds(value: string, what: string) {
    const n = Number(value);
    if (value === '' || !Number.isFinite(n) || n < 0) throw new UserInputError(`Enter ${what} in pounds (0 or more).`);
    return n;
  }

  async function save() {
    const saved = await perform(async () => {
      const body: FoodBankStatusInput = {
        storage: storage.map((s) => ({ window: toWindow(s, 'each storage time'), cold_free_lb: pounds(s.cold, 'cold space'), dry_free_lb: pounds(s.dry, 'dry space') })),
        pickup_windows: hours.map((h) => toWindow(h, 'each pickup window')),
        truck: { window: toWindow(truck, 'the truck time'), refrigerated: truck.refrigerated, capacity_lb: pounds(truck.capacity, 'truck capacity') },
      };
      return api.updateFoodBankStatus(foodBankId, body);
    });
    if (saved) onSaved(`${saved.message} (status version ${saved.status_version})`);
  }

  return (
    <Modal title="Update storage, pickup hours, and truck" onClose={onClose} busy={busy}>
      <form
        className="modal-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset>
          <legend>Free storage over time</legend>
          {storage.map((s, i) => (
            <div className="editor-row" key={i}>
              <label>
                From
                <input type="datetime-local" value={s.start} onChange={(e) => setStorage(storage.map((r, j) => (j === i ? { ...r, start: e.target.value } : r)))} required />
              </label>
              <label>
                Until
                <input type="datetime-local" value={s.end} onChange={(e) => setStorage(storage.map((r, j) => (j === i ? { ...r, end: e.target.value } : r)))} required />
              </label>
              <label>
                Cold free (lb)
                <input type="number" min="0" step="any" value={s.cold} onChange={(e) => setStorage(storage.map((r, j) => (j === i ? { ...r, cold: e.target.value } : r)))} required />
              </label>
              <label>
                Dry free (lb)
                <input type="number" min="0" step="any" value={s.dry} onChange={(e) => setStorage(storage.map((r, j) => (j === i ? { ...r, dry: e.target.value } : r)))} required />
              </label>
              <button type="button" className="text-button danger" onClick={() => setStorage(storage.filter((_, j) => j !== i))}>
                <Trash2 size={16} aria-hidden="true" /> Remove storage time {i + 1}
              </button>
            </div>
          ))}
          <button type="button" className="text-button" onClick={() => setStorage([...storage, { start: '', end: '', cold: '', dry: '' }])}>
            <Plus size={16} aria-hidden="true" /> Add a storage time
          </button>
        </fieldset>
        <fieldset>
          <legend>Pickup hours</legend>
          {hours.map((h, i) => (
            <div className="editor-row" key={i}>
              <label>
                From
                <input type="datetime-local" value={h.start} onChange={(e) => setHours(hours.map((r, j) => (j === i ? { ...r, start: e.target.value } : r)))} required />
              </label>
              <label>
                Until
                <input type="datetime-local" value={h.end} onChange={(e) => setHours(hours.map((r, j) => (j === i ? { ...r, end: e.target.value } : r)))} required />
              </label>
              <button type="button" className="text-button danger" onClick={() => setHours(hours.filter((_, j) => j !== i))}>
                <Trash2 size={16} aria-hidden="true" /> Remove pickup window {i + 1}
              </button>
            </div>
          ))}
          <button type="button" className="text-button" onClick={() => setHours([...hours, { start: '', end: '' }])}>
            <Plus size={16} aria-hidden="true" /> Add pickup hours
          </button>
        </fieldset>
        <fieldset>
          <legend>Truck</legend>
          <div className="editor-row">
            <label>
              Free from
              <input type="datetime-local" value={truck.start} onChange={(e) => setTruck({ ...truck, start: e.target.value })} required />
            </label>
            <label>
              Until
              <input type="datetime-local" value={truck.end} onChange={(e) => setTruck({ ...truck, end: e.target.value })} required />
            </label>
            <label>
              Carries (lb)
              <input type="number" min="0" step="any" value={truck.capacity} onChange={(e) => setTruck({ ...truck, capacity: e.target.value })} required />
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={truck.refrigerated} onChange={(e) => setTruck({ ...truck, refrigerated: e.target.checked })} /> Refrigerated
            </label>
          </div>
        </fieldset>
        <p className="subtle">Your organization’s agent uses these limits from now on.</p>
        <ErrorNote message={error} />
        <button className="primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
    </Modal>
  );
}

function GapPanel({ board }: { board: FoodBankDashboard }) {
  const gap = board.fair_share_gap;
  const counts: [string, number | undefined, string][] = [
    ['households', gap?.households, 'households below fair share'],
    ['people', gap?.people, 'people in them'],
    ['lb', gap?.below_fair_share_lb, 'lb below fair share this week'],
    ['fridge', gap?.limited_fridge, 'with limited fridge space'],
    ['evening', gap?.evening_only, 'can pick up only in the evening'],
  ];
  return (
    <Section title="Fair-share gap (counts only)" icon={<Users aria-hidden="true" size={20} />}>
      <dl className="counts">
        {counts.map(([key, value, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{value === undefined || value === null ? '—' : value.toLocaleString('en-US')}</dd>
          </div>
        ))}
      </dl>
      <p className="subtle">
        Your households appear only as counts. No names or details are shown.
        {gap?.table_version ? ` Fair-share table ${gap.table_version}.` : ''}
      </p>
    </Section>
  );
}

function IncomingOffers({
  board,
  approvals,
  approvalsError,
  onChanged,
}: {
  board: FoodBankDashboard;
  approvals?: ApprovalRequest[];
  approvalsError: string | null;
  onChanged: (message?: string) => void;
}) {
  return (
    <Section title="Incoming offers" icon={<CalendarClock aria-hidden="true" size={20} />}>
      <ErrorNote message={approvalsError ? `Approval requests: ${approvalsError}` : null} />
      {board.incoming_offers.length === 0 && <p className="muted">No offers right now.</p>}
      <div className="offer-list">
        {board.incoming_offers.map((offer) => (
          <OfferCard key={`${offer.lot_id}:${offer.version}`} offer={offer} foodBankId={board.food_bank_id} approval={findApproval(approvals, offer.lot_id, offer.version)} onChanged={onChanged} />
        ))}
      </div>
    </Section>
  );
}

function OfferCard({ offer, foodBankId, approval, onChanged }: { offer: IncomingOffer; foodBankId: string; approval?: ApprovalRequest; onChanged: (message?: string) => void }) {
  const [countering, setCountering] = useState(false);
  const [open, setOpen] = useState(false);
  const names = (approval?.terms as { names?: Record<string, string> } | undefined)?.names;
  return (
    <article className="incoming-card offer">
      <div className="offer-top">
        <Photo produceId={offer.for_us[0]?.produce_id ?? ''} />
        <div className="card-body">
          <div className="card-heading">
            <h3>
              {offer.for_us.map((i) => `${i.name} ${lb(i.pounds)}`).join(', ')}
            </h3>
            {offer.agent_suggests && <Badge text={`Agent suggests ${offer.agent_suggests}`} tone={offer.agent_suggests === 'accept' ? 'suggested-accept' : 'review'} />}
          </div>
          <p className="muted">
            From {offer.donor_name} · lot {offer.lot_id}, version {offer.version}
          </p>
          {offer.transport && (
            <p className="muted">
              {moverText(offer.transport.mover)}, leaves {formatDateTime(offer.transport.departs_at)}, arrives {formatDateTime(offer.transport.arrives_at)}
            </p>
          )}
        </div>
      </div>
      <p className="recommendation">
        <b>Your agent’s reason:</b> {offer.agent_reason}
      </p>
      {offer.needs_your_approval ? (
        approval ? (
          <ApprovalDecision approval={approval} organizationId={foodBankId} names={names} onRecorded={() => onChanged()} />
        ) : (
          <p className="muted">No approval request for version {offer.version} has reached you yet, so Accept and Decline are not available.</p>
        )
      ) : (
        <p className="inline-status">No decision needed from you on this version.</p>
      )}
      <div className="decision-actions">
        <button type="button" className="outline" onClick={() => setCountering(true)} disabled={!offer.needs_your_approval}>
          Counter
        </button>
        <button type="button" className="outline" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Hide details' : 'Details, versions, condition'}
        </button>
      </div>
      <p className="subtle">Accept records your approval of this exact version. It becomes a commitment only when every named organization approves it.</p>
      {countering && (
        <CounterDialog
          offer={offer}
          organizationId={foodBankId}
          onClose={() => setCountering(false)}
          onQueued={(m) => {
            setCountering(false);
            onChanged(m);
          }}
        />
      )}
      {open && <OfferDetails offer={offer} foodBankId={foodBankId} onChanged={() => onChanged()} />}
    </article>
  );
}

function OfferDetails({ offer, foodBankId, onChanged }: { offer: IncomingOffer; foodBankId: string; onChanged: () => void }) {
  const lot = useLoad(() => api.getLot(offer.lot_id), [offer.lot_id, offer.version]);
  const ours = new Set(offer.for_us.map((i) => i.produce_id));
  return (
    <div className="offer-details">
      {lot.loading && <p role="status">Loading lot…</p>}
      <ErrorNote message={lot.error} />
      {lot.data && (
        <>
          <LotStatus lot={lot.data} />
          {lot.data.status !== 'committed' && (
            <div className="condition-checks">
              {lot.data.items
                .filter((i) => ours.has(i.produce_id))
                .map((i) => (
                  <ConditionCheck
                    key={i.produce_id}
                    lotId={lot.data!.lot_id}
                    version={lot.data!.current_version}
                    produceId={i.produce_id}
                    produceName={i.name}
                    organizationId={foodBankId}
                    doubt={i.condition_doubt ?? lot.data!.draft.items.find((d) => d.produce_id === i.produce_id)?.condition_doubt}
                    onRecorded={() => {
                      void lot.reload();
                      onChanged();
                    }}
                  />
                ))}
            </div>
          )}
          <VersionHistory lotId={offer.lot_id} names={lot.data.draft?.names} />
        </>
      )}
    </div>
  );
}

function Disagreements({ items }: { items: Disagreement[] }) {
  return (
    <Section title="Disagreements" icon={<MessageSquareWarning aria-hidden="true" size={20} />}>
      {items.length === 0 && <p className="muted">No preserved disagreements involve you.</p>}
      {items.map((d, i) => (
        <DisagreementCard key={`${d.lot_id}-${i}`} item={d} />
      ))}
    </Section>
  );
}

function DisagreementCard({ item }: { item: Disagreement }) {
  const versions = useLoad(() => api.listLotVersions(item.lot_id), [item.lot_id]);
  const lot = useLoad(() => api.getLot(item.lot_id), [item.lot_id]);
  return (
    <article className="disagreement-card">
      <h3>Lot {item.lot_id}</h3>
      <p>
        <b>Why it stopped:</b> {disagreementText(item.reason) ?? 'No reason recorded.'}
      </p>
      <p className="muted">Each side’s latest reason:</p>
      <ErrorNote message={versions.error} />
      {versions.data && <EachSidesReason versions={versions.data.versions} names={lot.data?.draft?.names} />}
    </article>
  );
}

function Arrivals({ board }: { board: FoodBankDashboard }) {
  return (
    <Section title="Expected arrivals" icon={<Truck aria-hidden="true" size={20} />}>
      {board.expected_arrivals.length === 0 && <p className="muted">Nothing on the way.</p>}
      <ul className="arrival-list">
        {board.expected_arrivals.map((a) => (
          <li key={`${a.lot_id}:${a.version}`}>
            <div>
              <strong>{formatDateTime(a.arrives_at)}</strong> · lot {a.lot_id}, version {a.version}
              <p className="muted">{a.items.map((i) => `${humanize(i.produce_id)} ${lb(i.pounds)}`).join(', ')}</p>
            </div>
            <Badge text={a.status} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function PickupConfirm({ foodBankId }: { foodBankId: string }) {
  const [code, setCode] = useState('');
  const [result, setResult] = useState<PickupConfirmed | null>(null);
  const { busy, error, perform } = useAction();
  async function confirm() {
    const confirmed = await perform(async () => {
      const value = code.trim().toUpperCase();
      if (!/^[A-Z0-9]{3,12}$/.test(value)) throw new UserInputError('Enter the household’s request code (letters and numbers).');
      return api.confirmPickup({ food_bank_id: foodBankId, request_code: value });
    });
    if (confirmed) {
      setResult(confirmed);
      setCode('');
    }
  }
  return (
    <Section title="Pickup: enter a household’s code" icon={<KeyRound aria-hidden="true" size={20} />}>
      <form
        className="pickup-entry"
        onSubmit={(e) => {
          e.preventDefault();
          void confirm();
        }}
      >
        <label className="grow">
          Request code
          <input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" autoCapitalize="characters" maxLength={12} required />
        </label>
        <button className="primary" disabled={busy}>
          {busy ? 'Checking…' : 'Confirm pickup'}
        </button>
      </form>
      <ErrorNote message={error} />
      {result && (
        <div className="notice-card" role="status">
          <p>
            <CheckCircle2 aria-hidden="true" size={18} /> Code {result.request_code}: {humanize(result.status)} {lb(result.collected_lb)} at{' '}
            {formatDateTime(result.confirmed_at)}.
          </p>
          <p>
            This week: {lb(result.received_this_week_lb)} of {lb(result.fair_share_lb)} fair share received.
          </p>
          <ul>
            {result.items.map((i) => (
              <li key={i.produce_id}>
                {i.name}: {lb(i.pounds)}
              </li>
            ))}
          </ul>
          <DataLabel data={result} />
        </div>
      )}
    </Section>
  );
}

/** Changed plans after a disruption, with a reason card for every candidate food bank. */
function Disruptions({ disruptions, approvals, foodBankId, onChanged }: { disruptions: Disruption[]; approvals?: ApprovalRequest[]; foodBankId: string; onChanged: () => void }) {
  if (disruptions.length === 0) return null;
  return (
    <Section title="Disruptions" icon={<AlertTriangle aria-hidden="true" size={20} />}>
      {disruptions.map((d) => (
        <DisruptionCard key={`${d.lot_id}:${d.version}`} disruption={d} approval={findApproval(approvals, d.lot_id, d.version)} foodBankId={foodBankId} onChanged={onChanged} />
      ))}
    </Section>
  );
}

function DisruptionCard({ disruption, approval, foodBankId, onChanged }: { disruption: Disruption; approval?: ApprovalRequest; foodBankId: string; onChanged: () => void }) {
  const view = disruption.dashboard;
  const cards = [...(view.reason_cards ?? [])].sort((a, b) => Number(b.outcome === 'chosen') - Number(a.outcome === 'chosen'));
  const names: Record<string, string> = Object.fromEntries(cards.map((c) => [c.food_bank_id, c.name]));
  return (
    <article className="disruption-card">
      <div className="card-heading">
        <h3>
          {humanize(disruption.change)} at {names[view.food_bank_id] ?? view.food_bank_id}: lot {disruption.lot_id}, version {disruption.version}
        </h3>
        <Badge text={disruption.status} />
      </div>
      <p className="muted">
        Proposed by {names[disruption.proposer_id] ?? disruption.proposer_id}, based on version {disruption.based_on_version}.{' '}
        {view.synthetic ? 'Synthetic scenario data.' : ''}
      </p>
      {view.items && (
        <div className="moves">
          {view.items.move.length > 0 && (
            <div>
              <h4>Must move</h4>
              <ul>
                {view.items.move.map((i) => (
                  <li key={i.produce_id}>
                    {lb(i.pounds)} {humanize(i.produce_id)}: {i.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {view.items.stay.length > 0 && (
            <div>
              <h4>Can stay</h4>
              <ul>
                {view.items.stay.map((i) => (
                  <li key={i.produce_id}>
                    {lb(i.pounds)} {humanize(i.produce_id)}: {i.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {view.items.human_check.length > 0 && (
            <div>
              <h4>A person must check</h4>
              <ul>
                {view.items.human_check.map((i) => (
                  <li key={i.produce_id}>
                    {lb(i.pounds)} {humanize(i.produce_id)}: {i.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <h4>Every candidate food bank, and why</h4>
      {cards.length === 0 ? <p className="muted">No candidates were assessed.</p> : (
        <ul className="reason-cards">
          {cards.map((c) => (
            <ReasonCardView key={c.food_bank_id} card={c} />
          ))}
        </ul>
      )}
      {(view.fallback ?? []).length > 0 && (
        <div>
          <h4>If no food bank can take it</h4>
          <ul>
            {view.fallback!.map((f, i) => (
              <li key={i}>
                {lb(f.pounds)} {humanize(f.produce_id)} ({humanize(f.kind)}): {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(view.flags ?? []).length > 0 && (
        <details className="flags">
          <summary>Check before approving ({view.flags!.length})</summary>
          <ul>
            {view.flags!.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </details>
      )}
      <p>
        <b>Needs fresh approval from:</b> {disruption.needs_approval_from.map((o) => names[o] ?? o).join(', ')}.{' '}
        <b>Approved:</b> {disruption.approved_by.map((o) => names[o] ?? o).join(', ') || 'nobody yet'}.
        {disruption.declined_by.length > 0 && (
          <>
            {' '}
            <b>Declined:</b> {disruption.declined_by.map((o) => names[o] ?? o).join(', ')}.
          </>
        )}
      </p>
      {disruption.needs_your_approval &&
        (approval ? (
          <ApprovalDecision approval={approval} organizationId={foodBankId} names={names} onRecorded={() => onChanged()} />
        ) : (
          <p className="muted">Your approval is needed, but the approval request for version {disruption.version} hasn’t reached you yet.</p>
        ))}
      <p className="subtle">A changed plan needs every named organization’s fresh approval. Earlier approvals don’t carry over.</p>
    </article>
  );
}

function ReasonCardView({ card }: { card: ReasonCard }) {
  const chosen = card.outcome === 'chosen';
  return (
    <li className={`reason-card ${chosen ? 'chosen' : 'rejected'}`}>
      <div className="card-heading">
        <strong>
          {chosen ? <CheckCircle2 aria-hidden="true" size={18} /> : <XCircle aria-hidden="true" size={18} />} {card.name}
        </strong>
        <span className={`badge ${chosen ? 'delivered' : 'unclaimed'}`}>{chosen ? 'Chosen' : 'Not chosen'}</span>
      </div>
      <p>{card.text}</p>
      {card.reasons.length > 0 && (
        <ul>
          {card.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
