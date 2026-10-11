import { useEffect, useState } from 'react';
import { Package, Plus, Search, Sprout, Trash2, Truck } from 'lucide-react';
import { api, UserInputError } from '../api';
import { lb, localInputToIso } from '../format';
import { recentLots } from '../session';
import type { ProduceProfiles, SurplusOfferCreated, SurplusOfferInput } from '../types';
import { useAction, useLoad } from '../useLoad';
import { ConditionCheck } from './Decisions';
import { LotStatus, VersionHistory } from './LotViews';
import { DataLabel, ErrorNote, PageHeading, Photo, Section } from './ui';

interface ItemRow {
  key: number;
  produce_id: string;
  quantity: string;
  unit: string;
  lb_per_unit: string;
  condition_grade: string;
}

const GRADES = [
  { value: 'good', label: 'Good', hint: 'Fresh, no problems' },
  { value: 'use_soon', label: 'Use soon', hint: 'Fine, but short life' },
];

let nextKey = 1;

export function ReportSurplus({ donorId, onCreated, onShowStatus }: { donorId: string; onCreated: (lotId: string) => void; onShowStatus?: () => void }) {
  const profiles = useLoad(() => api.listProduceProfiles(), []);
  const banks = useLoad(() => api.listFoodBanks(), []);
  const [rows, setRows] = useState<ItemRow[]>([]);
  const [deadline, setDeadline] = useState('');
  const [recall, setRecall] = useState(false);
  const [canDropOff, setCanDropOff] = useState(false);
  const [dropStart, setDropStart] = useState('');
  const [dropEnd, setDropEnd] = useState('');
  const [refrigerated, setRefrigerated] = useState(false);
  const [capacity, setCapacity] = useState('');
  const [dropTo, setDropTo] = useState<string[]>([]);
  const [created, setCreated] = useState<SurplusOfferCreated | null>(null);
  const { busy, error, perform } = useAction();

  const list = profiles.data;
  const items = rows;
  useEffect(() => {
    if (list && rows.length === 0) setRows([blankRow(list)]);
  }, [list, rows.length]);

  function update(key: number, patch: Partial<ItemRow>) {
    setRows(items.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  async function submit() {
    if (!list) return;
    const result = await perform(async () => {
      if (recall) throw new UserInputError('A lot with a recall notice can’t be offered. Resolve the recall first.');
      const deadlineIso = localInputToIso(deadline);
      if (!deadlineIso) throw new UserInputError('Enter when the produce must be gone.');
      const offer: SurplusOfferInput = {
        donor_id: donorId,
        deadline: deadlineIso,
        recall_notice: recall,
        items: items.map((r) => {
          const quantity = Number(r.quantity);
          const profile = list.profiles.find((p) => p.produce_id === r.produce_id);
          if (!profile) throw new UserInputError('Pick each item from the produce list.');
          if (!r.quantity || !Number.isFinite(quantity) || quantity <= 0) throw new UserInputError(`Enter a quantity above 0 for ${profile.name}.`);
          const item: SurplusOfferInput['items'][number] = { produce_id: r.produce_id, quantity, unit: r.unit, condition_grade: r.condition_grade };
          if (needsPackWeight(list, r.produce_id, r.unit)) {
            const perUnit = Number(r.lb_per_unit);
            if (!r.lb_per_unit || !Number.isFinite(perUnit) || perUnit <= 0)
              throw new UserInputError(`Enter the pounds in each ${r.unit} of ${profile.name}.`);
            item.lb_per_unit = perUnit;
          }
          return item;
        }),
        drop_off: canDropOff ? dropOffBody() : { can_drop_off: false },
      };
      return api.createSurplusOffer(offer);
    });
    if (result) {
      setCreated(result);
      recentLots.add(donorId, result.lot_id);
      onCreated(result.lot_id);
    }
  }

  function dropOffBody(): SurplusOfferInput['drop_off'] {
    const start = localInputToIso(dropStart);
    const end = localInputToIso(dropEnd);
    if (!start || !end) throw new UserInputError('Enter when you can drop off.');
    const cap = Number(capacity);
    if (!capacity || !Number.isFinite(cap) || cap <= 0) throw new UserInputError('Enter how many pounds your vehicle can carry.');
    if (!dropTo.length) throw new UserInputError('Choose at least one food bank you can drop off at.');
    return { can_drop_off: true, window: { start, end }, refrigerated, capacity_lb: cap, food_bank_ids: dropTo };
  }

  return (
    <>
      <PageHeading icon={<Sprout />} title="Report surplus produce" subtitle="Offer extra produce to nearby food banks. Nothing is promised until your staff approve a plan." />
      {profiles.loading && <p role="status">Loading the produce list…</p>}
      <ErrorNote message={profiles.error} />
      {list && (
        <form
          className="report-form"
          aria-label="Report surplus produce"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {items.map((row, index) => {
            const profile = list.profiles.find((p) => p.produce_id === row.produce_id);
            const packWeight = needsPackWeight(list, row.produce_id, row.unit);
            return (
              <fieldset key={row.key} className="item-row">
                <legend>Item {index + 1}</legend>
                <div className="item-picker">
                  <Photo produceId={row.produce_id} />
                  <label className="grow">
                    Produce
                    <select
                      value={row.produce_id}
                      onChange={(e) => {
                        const next = list.profiles.find((p) => p.produce_id === e.target.value);
                        update(row.key, { produce_id: e.target.value, unit: next?.units[0] ?? '', lb_per_unit: '' });
                      }}
                    >
                      {list.profiles.map((p) => (
                        <option key={p.produce_id} value={p.produce_id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {profile?.needs_cold && <p className="muted">Needs to stay cold.</p>}
                <div className="quantity-row">
                  <label className="grow">
                    Quantity
                    <input type="number" inputMode="decimal" min="0" step="any" value={row.quantity} onChange={(e) => update(row.key, { quantity: e.target.value })} required />
                  </label>
                  <label>
                    Unit
                    <select value={row.unit} onChange={(e) => update(row.key, { unit: e.target.value, lb_per_unit: '' })}>
                      {(profile?.units ?? []).map((u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {packWeight && (
                  <label>
                    Pounds in each {row.unit}
                    <input type="number" inputMode="decimal" min="0" step="any" value={row.lb_per_unit} onChange={(e) => update(row.key, { lb_per_unit: e.target.value })} required />
                  </label>
                )}
                <fieldset>
                  <legend>Condition grade</legend>
                  <div className="choices">
                    {GRADES.map((g) => (
                      <button type="button" key={g.value} aria-pressed={row.condition_grade === g.value} className={row.condition_grade === g.value ? 'selected' : ''} onClick={() => update(row.key, { condition_grade: g.value })}>
                        {g.label}
                        <small>{g.hint}</small>
                      </button>
                    ))}
                  </div>
                </fieldset>
                {items.length > 1 && (
                  <button type="button" className="text-button danger" onClick={() => setRows(items.filter((r) => r.key !== row.key))}>
                    <Trash2 size={16} aria-hidden="true" /> Remove item {index + 1}
                  </button>
                )}
              </fieldset>
            );
          })}
          <button type="button" className="outline" onClick={() => setRows([...items, blankRow(list)])}>
            <Plus size={18} aria-hidden="true" /> Add another item
          </button>
          <label>
            Must be gone by
            <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} required />
          </label>
          <fieldset>
            <legend>Is there a recall notice for any of it?</legend>
            <div className="choices">
              {[false, true].map((v) => (
                <button type="button" key={String(v)} aria-pressed={recall === v} className={recall === v ? 'selected' : ''} onClick={() => setRecall(v)}>
                  {v ? 'Yes' : 'No'}
                </button>
              ))}
            </div>
            {recall && <p className="warning">Recalled produce is never offered.</p>}
          </fieldset>
          <fieldset>
            <legend>Can you drop it off?</legend>
            <div className="choices transport">
              {[true, false].map((v) => (
                <button type="button" key={String(v)} aria-pressed={canDropOff === v} className={canDropOff === v ? 'selected' : ''} onClick={() => setCanDropOff(v)}>
                  {v ? <Truck aria-hidden="true" /> : <Package aria-hidden="true" />}
                  <span>
                    {v ? 'Yes' : 'No'}
                    <small>{v ? 'I can drop off' : 'A food bank collects'}</small>
                  </span>
                </button>
              ))}
            </div>
          </fieldset>
          {canDropOff && (
            <fieldset className="drop-off">
              <legend>Drop-off details</legend>
              <label>
                Earliest drop-off
                <input type="datetime-local" value={dropStart} onChange={(e) => setDropStart(e.target.value)} required />
              </label>
              <label>
                Latest drop-off
                <input type="datetime-local" value={dropEnd} onChange={(e) => setDropEnd(e.target.value)} required />
              </label>
              <label>
                Vehicle can carry (lb)
                <input type="number" inputMode="decimal" min="0" step="any" value={capacity} onChange={(e) => setCapacity(e.target.value)} required />
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={refrigerated} onChange={(e) => setRefrigerated(e.target.checked)} /> Vehicle is refrigerated
              </label>
              <fieldset>
                <legend>Food banks you can reach</legend>
                <ErrorNote message={banks.error} />
                {banks.data?.food_banks.map((b) => (
                  <label className="checkbox" key={b.food_bank_id}>
                    <input
                      type="checkbox"
                      checked={dropTo.includes(b.food_bank_id)}
                      onChange={(e) => setDropTo(e.target.checked ? [...dropTo, b.food_bank_id] : dropTo.filter((id) => id !== b.food_bank_id))}
                    />{' '}
                    {b.name}
                  </label>
                ))}
              </fieldset>
            </fieldset>
          )}
          <ErrorNote message={error} />
          <button className="primary" disabled={busy || recall}>
            {busy ? 'Sending…' : 'Offer this surplus'}
          </button>
          <DataLabel data={list} />
        </form>
      )}
      {created && (
        <div className="notice-card" role="status">
          <p>
            <b>{created.message}</b>
          </p>
          <p>
            Lot {created.lot_id}, version {created.version}:{' '}
            {created.items.map((i) => `${i.name} ${lb(i.pounds)}`).join(', ')}.
          </p>
          {created.needs_human.length > 0 && (
            <p className="warning">A condition check is needed for: {created.needs_human.join(', ')}.</p>
          )}
          {onShowStatus && (
            <button type="button" className="outline" onClick={onShowStatus}>
              See this lot’s status
            </button>
          )}
          <DataLabel data={created} />
        </div>
      )}
    </>
  );
}

function blankRow(list: ProduceProfiles): ItemRow {
  const first = list.profiles[0];
  return { key: nextKey++, produce_id: first?.produce_id ?? '', quantity: '', unit: first?.units[0] ?? '', lb_per_unit: '', condition_grade: 'good' };
}

function needsPackWeight(list: ProduceProfiles, produceId: string, unit: string) {
  return (list.units_needing_pack_weight[produceId] ?? []).includes(unit);
}

/** Donor's lots: live status item by item, and every version with who proposed what and why. */
export function MyLots({ donorId, initialLot }: { donorId: string; initialLot?: string }) {
  const remembered = recentLots.list(donorId);
  const [lotId, setLotId] = useState(initialLot ?? remembered[0] ?? '');
  const [query, setQuery] = useState(lotId);
  const lot = useLoad(lotId ? () => api.getLot(lotId) : null, [lotId]);

  return (
    <>
      <PageHeading icon={<Package />} title="My lots" subtitle="Each item’s status, who moves it, and every version of the plan with its reason." />
      <form
        className="lookup"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setLotId(query.trim());
        }}
      >
        <label className="grow">
          Lot ID
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="lot-…" />
        </label>
        <button className="primary">
          <Search size={18} aria-hidden="true" /> Show
        </button>
      </form>
      {remembered.length > 0 && (
        <div className="chips" aria-label="Lots you offered in this tab">
          {remembered.map((id) => (
            <button type="button" key={id} className={id === lotId ? 'chip active' : 'chip'} onClick={() => (setQuery(id), setLotId(id))}>
              {id}
            </button>
          ))}
        </div>
      )}
      {!lotId && <p className="muted">Offer surplus, or enter a lot ID to see its status.</p>}
      {lot.loading && <p role="status">Loading lot…</p>}
      <ErrorNote message={lot.error} />
      {lot.data && (
        <>
          <Section title="Status, item by item">
            <LotStatus lot={lot.data} />
            <DataLabel data={lot.data} />
          </Section>
          {lot.data.items.some((i) => i.condition_doubt) && lot.data.status !== 'committed' && (
            <Section title="Condition checks">
              {lot.data.items
                .filter((i) => i.condition_doubt)
                .map((i) => (
                  <ConditionCheck
                    key={i.produce_id}
                    lotId={lot.data!.lot_id}
                    version={lot.data!.current_version}
                    produceId={i.produce_id}
                    produceName={i.name}
                    organizationId={donorId}
                    doubt={i.condition_doubt}
                    onRecorded={() => void lot.reload()}
                  />
                ))}
            </Section>
          )}
          <Section title="Who proposed what, and why">
            <VersionHistory lotId={lot.data.lot_id} names={lot.data.draft?.names} />
          </Section>
        </>
      )}
    </>
  );
}
