"""A food bank's own cooler watcher: the deployed trigger for Workflow 4 (#23).

Each food bank's organization host runs one of these for its own organization. It polls
its own cooler reading from the organization systems service. When the reading turns
failed, this food bank's agent (and nobody else) runs ``cooler_join.handle_cooler_reading``
against the live core: it records the failed cooler in its own status, reads its committed
holding, asks the other food banks for their own answers, runs Lane B's cooler-failure flow
and proposes the new version. It then asks Lane C's approval bridge to issue review links
and send the review emails. It never approves or commits (ADR 0001, 0004): only each
named organization's human can, on their own review link.

One failure is one *episode*, which starts when the reading turns failed and ends when it
reads working again. Each episode proposes at most once per lot, and a restart in the
middle of one does not repeat it (the state is kept in a small file). When the cooler is
reset to working and fails again, that is a new episode, and it proposes again against the
lot's then-current committed version. If an earlier change is still awaiting approvals the
core refuses a second one (409) and the watcher records that instead of duplicating it.

The review links the bridge returns are never stored, logged or returned: they are the
humans' capabilities, and the watcher is not a human. All data is synthetic.
Interfaces added here are **proposed**, pending ticket #1.
"""
import json
import os
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError

from harvestnet_agents.cooler_failure_flow import read_cooler_signal

from . import cooler_join as join

DEFAULT_INTERVAL_SECONDS = 10.0
# Lot entries that need no further work in this episode.
DONE = ('requested', 'nothing_held', 'no_change', 'conflict', 'declined_earlier', 'refused')
LABEL = 'synthetic'
CoreErrorTypes = (join.CoreError, HTTPError, URLError)


def log(message):
    print(f'cooler-watch: {message} ({LABEL})', flush=True)


class FallbackDirectory:
    """The AGNTCY Directory when it answers; otherwise the labeled local registry.

    The fallback's own ``mode`` ("local_directory_fallback") stays on its result, so the
    dashboard never presents local data as AGNTCY results.
    """

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback

    @property
    def mode(self):
        return self.primary.mode

    def search(self, **query):
        try:
            return self.primary.search(**query)
        except Exception as exc:  # gRPC errors: the Directory is down or refused the call
            result = self.fallback.search(**query)
            result['agntcy_unreachable'] = type(exc).__name__
            return result


class State:
    """The current failure episode, saved as JSON so a restart does not repeat a proposal."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.data = {'episode': None}
        if self.path and self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                if isinstance(loaded, dict):
                    self.data = {'episode': loaded.get('episode')}
            except (OSError, ValueError):
                pass  # an unreadable state file starts clean; the core still refuses duplicates

    @property
    def episode(self):
        return self.data['episode']

    @episode.setter
    def episode(self, value):
        self.data['episode'] = value
        self.save()

    def save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, sort_keys=True))
        tmp.replace(self.path)


def retryable(exc):
    """A transient failure (outage, timeout, server error) is retried next tick; a refusal is not."""
    if isinstance(exc, join.CoreError):
        return exc.status >= 500
    if isinstance(exc, HTTPError):
        return exc.code >= 500
    return isinstance(exc, (URLError, TimeoutError, OSError))


class CoolerWatcher:
    def __init__(self, *, food_bank_id, systems_url, core_url, approvals_url, core_token, events_token, directory,
                 state_path=None, profiles=None):
        self.food_bank_id = food_bank_id
        self.systems_url, self.core_url, self.approvals_url = systems_url.rstrip('/'), core_url.rstrip('/'), approvals_url.rstrip('/')
        self.core_token, self.events_token = core_token, events_token
        self.directory, self.profiles = directory, profiles
        self.state = State(state_path)
        self.lock = threading.Lock()

    # --- reads -------------------------------------------------------------------------

    def reading(self):
        return read_cooler_signal(join._json(f'{self.systems_url}/systems/{self.food_bank_id}/cooler'), organization_id=self.food_bank_id)

    def dashboard(self):
        return join._json(f'{self.core_url}/food-banks/{self.food_bank_id}/dashboard', token=self.core_token, method='GET')

    @staticmethod
    def committed_lots(dashboard):
        """The lots this food bank holds a committed share of, from its own dashboard."""
        lots = []
        for offer in dashboard.get('incoming_offers', []):
            if offer.get('needs_your_approval') is False and offer['lot_id'] not in lots:
                lots.append(offer['lot_id'])
        return lots

    @staticmethod
    def declined_earlier(dashboard, lot_id):
        """A human already declined the version this failure would propose, and no later one committed.

        The core numbers a change after the last committed version, so proposing again would reuse
        that version number, whose review links the humans already used. Nobody could decide it.
        """
        mine = [d for d in dashboard.get('disruptions', []) if d['lot_id'] == lot_id]
        committed = [d['version'] for d in mine if d['status'] == 'committed']
        return any(d['status'] == 'declined' and d['version'] > max(committed, default=0) for d in mine)

    def names(self):
        try:
            banks = join._json(f'{self.core_url}/food-banks', method='GET')['food_banks']
            return {b['food_bank_id']: b['name'] for b in banks}
        except (CoreErrorTypes, ValueError, KeyError, OSError):
            return {}

    # --- one poll ----------------------------------------------------------------------

    def tick(self):
        """Poll once. Returns a summary with no review links. Safe to call repeatedly."""
        with self.lock:
            signal = self.reading()
            if not signal.failed:
                return self._recovered(signal)
            if self.state.episode is None:
                self.state.episode = {'observed_at': signal.observed_at.isoformat(), 'lots': {}}
                log(f'{self.food_bank_id} cooler reading failed; this food bank starts its cooler-failure flow')
            return self._handle_failure()

    def _recovered(self, signal):
        if self.state.episode is None:
            return {'status': 'working', 'synthetic': True}
        # Reset: the next failure is a new episode and may propose again.
        self.state.episode = None
        reading = signal.reading.summary()
        status = {'status': 'working', 'temperature_c': signal.temperature_c, 'cold_available': True,
                  **{k: reading[k] for k in ('source', 'mode', 'synthetic', 'observed_at')}}
        try:
            join._json(f'{self.core_url}/food-banks/{self.food_bank_id}/status', {'cooler': status}, token=self.core_token, method='PUT')
        except (join.CoreError, URLError, OSError, ValueError) as exc:
            log(f'cooler back to working; could not record it in the core status ({type(exc).__name__})')
        else:
            log(f'{self.food_bank_id} cooler reads working again; episode closed')
        return {'status': 'recovered', 'synthetic': True}

    def _handle_failure(self):
        episode = self.state.episode
        names = None
        dashboard = self.dashboard()
        for lot_id in self.committed_lots(dashboard):
            entry = episode['lots'].get(lot_id)
            if entry and entry['status'] in DONE:
                continue
            try:
                if entry is None:
                    if self.declined_earlier(dashboard, lot_id):
                        log(f'{lot_id}: a human declined the version this failure would propose; not proposing it again. '
                            'Reset the demo data to run the failure again')
                        episode['lots'][lot_id] = {'status': 'declined_earlier'}
                        self.state.save()
                        continue
                    names = names if names is not None else self.names()
                    entry = self._propose(lot_id, names)
                    episode['lots'][lot_id] = entry
                    self.state.save()
                if entry['status'] == 'proposed':
                    entry['status'] = self._request_approvals(entry)
                    self.state.save()
            except Exception as exc:
                if retryable(exc):
                    log(f'{lot_id}: {type(exc).__name__}; will retry')
                    continue
                # A refusal is not retried every tick; a human sees this in the log and on the dashboard.
                log(f'{lot_id}: {type(exc).__name__}: {str(exc)[:160]}; not retried in this episode')
                episode['lots'][lot_id] = {**(entry or {}), 'status': 'refused', 'reason': type(exc).__name__}
                self.state.save()
        return {'status': 'failed', 'synthetic': True,
                'lots': {lot: {k: e.get(k) for k in ('status', 'version', 'terms_hash')} for lot, e in episode['lots'].items()}}

    def _propose(self, lot_id, names):
        try:
            result = join.handle_cooler_reading(
                food_bank_id=self.food_bank_id, lot_id=lot_id, systems_url=self.systems_url, core_url=self.core_url,
                token=self.core_token, directory=self.directory, profiles=self.profiles,
                answer=lambda org: join.candidate_answer(self.systems_url, org, names.get(org, org)))
        except join.CoreError as exc:
            if exc.status == 409:  # nothing held here, or another change is already awaiting approvals
                message = json.dumps(exc.body)[:200]
                log(f'{lot_id}: core refused ({message}); nothing to propose')
                return {'status': 'conflict' if 'awaiting approvals' in message else 'nothing_held'}
            if exc.status < 500:
                log(f'{lot_id}: core refused the request ({exc.status}); not retried in this episode')
                return {'status': 'refused'}
            raise
        change = result['change']
        if result['status'] == 'no_failure':
            return {'status': 'nothing_held'}  # the reading recovered between the poll and the run
        if change is None:
            log(f'{lot_id}: no new version proposed (no candidate fits; a human decides)')
            return {'status': 'no_change'}
        log(f"{lot_id}: proposed version {change['version']} to {', '.join(change['needs_approval_from'])}; nothing is committed")
        return {'status': 'proposed', 'version': change['version'], 'terms_hash': change['terms_hash'],
                'approval_request': change['approval_request']}

    def _request_approvals(self, entry):
        try:
            join.request_approvals(self.approvals_url, self.events_token, entry['approval_request'])
        except join.CoreError as exc:
            # Already issued for this exact version (a retry after an uncertain answer): never reissue automatically.
            if exc.status == 400 and 'already exists' in json.dumps(exc.body):
                log(f"version {entry['version']}: review links already issued")
                return 'requested'
            raise
        log(f"version {entry['version']}: review emails requested from the approval service")
        return 'requested'

    # --- loop --------------------------------------------------------------------------

    def run_forever(self, interval_seconds=DEFAULT_INTERVAL_SECONDS, stop=None):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # keep watching; report and retry next interval
                log(f'poll failed: {type(exc).__name__}: {str(exc)[:160]}')
            stop.wait(interval_seconds)



def directory_from_env(organization, systems, environ=None):
    """The AGNTCY Directory when configured, with the labeled local registry as the fallback."""
    from harvestnet_platform.directory import AgntcyDirectory, LocalDirectory
    from harvestnet_platform.transport import ORGANIZATIONS
    environ = os.environ if environ is None else environ
    endpoints = {org: f'http://{"donor" if org == "market" else org}:8020' for org in ORGANIZATIONS}
    local = LocalDirectory(systems, endpoints)
    address = environ.get('AGNTCY_DIRECTORY_ADDRESS')
    if not address:
        return local
    try:
        return FallbackDirectory(AgntcyDirectory(address), local)
    except Exception as exc:
        log(f'AGNTCY Directory client unavailable ({type(exc).__name__}); using the labeled local registry')
        return local


def watcher_from_env(organization, environ=None):
    """The watcher for ``organization``, or ``None`` (with the reason logged) if it is not configured."""
    from harvestnet_platform.systems import BANKS, organization_systems
    environ = os.environ if environ is None else environ
    if organization not in BANKS:
        log(f'{organization} is not a food bank; no cooler watcher')
        return None
    try:
        # Only this organization's own core credential is kept from the staff-token map.
        token = json.loads(environ.get('HARVESTNET_STAFF_TOKENS') or '{}').get(organization)
    except ValueError:
        token = None
    events, systems_url = environ.get('API_EVENTS_TOKEN'), environ.get('SYSTEMS_URL')
    if not (token and events and systems_url):
        log('needs the organization core token, API_EVENTS_TOKEN and SYSTEMS_URL; not started')
        return None
    return CoolerWatcher(
        food_bank_id=organization, systems_url=systems_url, core_url=environ.get('CORE_API_URL', 'http://core:8000'),
        approvals_url=environ.get('APPROVALS_URL', 'http://approvals:8030'), core_token=token, events_token=events,
        directory=directory_from_env(organization, organization_systems(), environ),
        state_path=environ.get('COOLER_WATCH_STATE', '/app/runtime/cooler-watch.json'))


def start_from_env(organization, environ=None, stop=None):
    """Start the watcher thread for this organization host. Returns the thread, or ``None``."""
    environ = os.environ if environ is None else environ
    watcher = watcher_from_env(organization, environ)
    if watcher is None:
        return None
    try:
        interval = float(environ.get('COOLER_WATCH_INTERVAL_SECONDS') or DEFAULT_INTERVAL_SECONDS)
        if interval <= 0:
            raise ValueError
    except ValueError:
        interval = DEFAULT_INTERVAL_SECONDS
    thread = threading.Thread(target=watcher.run_forever, args=(interval, stop), daemon=True, name=f'cooler-watch-{organization}')
    thread.start()
    log(f'{organization} watches its own cooler every {interval:g}s')
    return thread
