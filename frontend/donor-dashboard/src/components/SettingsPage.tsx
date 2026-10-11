import { useState } from 'react';
import { KeyRound, Settings } from 'lucide-react';
import { api, API_BASE_URL } from '../api';
import { staffToken } from '../session';
import { useLoad } from '../useLoad';
import { PageHeading, Section } from './ui';

export function SettingsPage({
  donorId,
  foodBankId,
  onDonorId,
  onFoodBankId,
}: {
  donorId: string;
  foodBankId: string;
  onDonorId: (id: string) => void;
  onFoodBankId: (id: string) => void;
}) {
  const banks = useLoad(() => api.listFoodBanks(), []);
  const [donorDraft, setDonorDraft] = useState(donorId);
  return (
    <>
      <PageHeading icon={<Settings />} title="Settings" subtitle="Which organization you work for, and your staff sign-in for this browser tab." />
      <Section title="Your organizations">
        <form
          className="settings-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (donorDraft.trim()) onDonorId(donorDraft.trim());
          }}
        >
          <label>
            Donor organization ID
            <input value={donorDraft} onChange={(e) => setDonorDraft(e.target.value)} autoComplete="organization" />
          </label>
          <button className="outline">Use this donor ID</button>
        </form>
        <label>
          Food bank
          <select value={foodBankId} onChange={(e) => onFoodBankId(e.target.value)}>
            {!banks.data?.food_banks.some((b) => b.food_bank_id === foodBankId) && <option value={foodBankId}>{foodBankId}</option>}
            {banks.data?.food_banks.map((b) => (
              <option key={b.food_bank_id} value={b.food_bank_id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
      </Section>
      <Section title="Staff sign-in" icon={<KeyRound aria-hidden="true" size={20} />}>
        <p className="muted">
          Dashboards, offers, counters, approvals, and pickup confirmations need your organization’s staff token. It stays in this browser tab only and is
          cleared when you close it. It is sent only to the HarvestNet API as your sign-in, never put in a link, saved to a file, or logged.
        </p>
        <TokenField key={`d-${donorId}`} organizationId={donorId} label="Donor staff token" />
        <TokenField key={`f-${foodBankId}`} organizationId={foodBankId} label="Food bank staff token" />
      </Section>
      <Section title="API">
        <p className="muted">
          Calling <code>{API_BASE_URL}</code>. Set <code>VITE_API_BASE_URL</code> to use another address.
        </p>
      </Section>
    </>
  );
}

function TokenField({ organizationId, label }: { organizationId: string; label: string }) {
  const [value, setValue] = useState('');
  const [saved, setSaved] = useState(Boolean(staffToken.get(organizationId)));
  return (
    <form
      className="token-form"
      onSubmit={(e) => {
        e.preventDefault();
        staffToken.set(organizationId, value);
        setSaved(Boolean(value.trim()));
        setValue('');
      }}
    >
      <label className="grow">
        {label} for <b>{organizationId}</b>
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} />
      </label>
      <div className="decision-actions">
        <button className="primary" disabled={!value.trim()}>
          Save for this tab
        </button>
        <button
          type="button"
          className="outline"
          disabled={!saved}
          onClick={() => {
            staffToken.clear(organizationId);
            setSaved(false);
          }}
        >
          Forget
        </button>
      </div>
      <p className="subtle" role="status">
        {saved ? `A token is set for ${organizationId} in this tab.` : `No token set for ${organizationId}.`}
      </p>
    </form>
  );
}
