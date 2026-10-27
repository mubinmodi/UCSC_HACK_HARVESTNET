import { useState, type ReactNode } from 'react';
import { Building2, ClipboardCheck, Leaf, Package, PlusCircle, Settings, ShieldCheck, Sprout } from 'lucide-react';
import { ApprovalsPage } from './components/ApprovalsPage';
import { MyLots, ReportSurplus } from './components/DonorPage';
import { FoodBankPage } from './components/FoodBankPage';
import { SettingsPage } from './components/SettingsPage';
import { sessionValue } from './session';

type Page = 'report' | 'lots' | 'donor-approvals' | 'dashboard' | 'bank-approvals' | 'settings';

const NAV: { page: Page; label: string; group: 'Donor' | 'Food bank' | 'Settings'; icon: ReactNode }[] = [
  { page: 'report', label: 'Report surplus', group: 'Donor', icon: <PlusCircle aria-hidden="true" /> },
  { page: 'lots', label: 'My lots', group: 'Donor', icon: <Package aria-hidden="true" /> },
  { page: 'donor-approvals', label: 'Donor approvals', group: 'Donor', icon: <ClipboardCheck aria-hidden="true" /> },
  { page: 'dashboard', label: 'Dashboard', group: 'Food bank', icon: <Building2 aria-hidden="true" /> },
  { page: 'bank-approvals', label: 'Food bank approvals', group: 'Food bank', icon: <ClipboardCheck aria-hidden="true" /> },
  { page: 'settings', label: 'Settings', group: 'Settings', icon: <Settings aria-hidden="true" /> },
];

// Example organization IDs from the contract; staff change them in Settings.
const DEFAULT_DONOR = 'market';
const DEFAULT_FOOD_BANK = 'city';

export default function App() {
  const [page, setPage] = useState<Page>(() => (sessionValue.get('page') as Page) || 'report');
  const [donorId, setDonorIdState] = useState(() => sessionValue.get('donor-id') || DEFAULT_DONOR);
  const [foodBankId, setFoodBankIdState] = useState(() => sessionValue.get('food-bank-id') || DEFAULT_FOOD_BANK);
  const [lastLot, setLastLot] = useState<string | undefined>();

  function go(next: Page) {
    setPage(next);
    sessionValue.set('page', next);
    window.scrollTo?.(0, 0);
  }
  const setDonorId = (id: string) => (setDonorIdState(id), sessionValue.set('donor-id', id));
  const setFoodBankId = (id: string) => (setFoodBankIdState(id), sessionValue.set('food-bank-id', id));

  const navButton = (n: (typeof NAV)[number]) => (
    <button key={n.page} type="button" className={page === n.page ? 'active' : ''} aria-current={page === n.page ? 'page' : undefined} onClick={() => go(n.page)}>
      {n.icon}
      <span>{n.label}</span>
    </button>
  );

  return (
    <div className="shell lg:flex">
      <nav className="desktop-sidebar" aria-label="Main">
        <div className="sidebar-brand">
          <a className="hn-wordmark" href="/">
            <Sprout aria-hidden="true" />
            <span>HarvestNet</span>
          </a>
        </div>
        <p className="sidebar-tagline">Surplus produce to households, agreed by every organization.</p>
        {(['Donor', 'Food bank', 'Settings'] as const).map((group) => (
          <div key={group} className="nav-group">
            <div className="workspace-label">{group.toUpperCase()}</div>
            {NAV.filter((n) => n.group === group).map(navButton)}
          </div>
        ))}
        <div className="sidebar-bottom">
          <ShieldCheck size={20} aria-hidden="true" />
          <div>
            Every organization decides for itself
            <small>Nothing is committed until all named organizations approve the same version.</small>
          </div>
        </div>
      </nav>
      <div className="app-area">
        <header className="topbar hn-on-deep">
          <a className="hn-wordmark topbar-brand" href="/">
            <Sprout aria-hidden="true" />
            <span>HarvestNet</span>
          </a>
          <span className="topbar-org">
            Donor <b>{donorId}</b> · Food bank <b>{foodBankId}</b>
          </span>
        </header>
        <main className="main-content">
          {page === 'report' && (
            <ReportSurplus
              donorId={donorId}
              onCreated={(lotId) => setLastLot(lotId)}
              onShowStatus={() => go('lots')}
            />
          )}
          {page === 'lots' && <MyLots key={`${donorId}:${lastLot ?? ''}`} donorId={donorId} initialLot={lastLot} />}
          {page === 'donor-approvals' && <ApprovalsPage key={donorId} organizationId={donorId} roleLabel="donor" />}
          {page === 'dashboard' && <FoodBankPage key={foodBankId} foodBankId={foodBankId} />}
          {page === 'bank-approvals' && <ApprovalsPage key={foodBankId} organizationId={foodBankId} roleLabel="food bank" />}
          {page === 'settings' && <SettingsPage donorId={donorId} foodBankId={foodBankId} onDonorId={setDonorId} onFoodBankId={setFoodBankId} />}
          <p className="footnote">
            <Leaf size={13} aria-hidden="true" />
            Numbers on these pages come from the HarvestNet API. Each section says whether its data is an example, synthetic, or live.
          </p>
        </main>
        <nav className="bottom-nav" aria-label="Main (mobile)">
          {NAV.map(navButton)}
        </nav>
      </div>
    </div>
  );
}
