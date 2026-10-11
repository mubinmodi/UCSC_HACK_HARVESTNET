// Shapes from the agreed public API contract (docs/contracts/public-api.md and
// docs/contracts/examples/public-api/*.json). Field names are copied, never renamed.
// `disruptions` on the dashboard comes from the core's #23 join (docs/core/README.md),
// which is proposed and not yet in the contract's example.

export type Mode = 'example' | 'live' | 'replay' | 'synthetic' | string;

export interface Labelled {
  mode?: Mode;
  synthetic?: boolean;
}

export interface TimeWindow {
  start: string;
  end: string;
}

export type Mover = 'donor' | 'food_bank' | string;

// list_produce_profiles
export interface ProduceProfile {
  produce_id: string;
  name: string;
  units: string[];
  needs_fridge: boolean;
  needs_cold: boolean;
}
export interface ProduceProfiles extends Labelled {
  profile_set_version: string;
  profiles: ProduceProfile[];
  units_needing_pack_weight: Record<string, string[]>;
}

// list_food_banks (used only to name food banks for the drop-off choice)
export interface FoodBankListing {
  food_bank_id: string;
  name: string;
  area?: string;
  pickup_windows?: unknown;
}
export interface FoodBankList extends Labelled {
  food_banks: FoodBankListing[];
}

// create_surplus_offer
export type ConditionGrade = 'good' | 'use_soon' | 'not_for_people';
export interface SurplusItemInput {
  produce_id: string;
  quantity: number;
  unit: string;
  lb_per_unit?: number;
  condition_grade: ConditionGrade | string;
}
export interface DropOff {
  can_drop_off: boolean;
  window?: TimeWindow;
  refrigerated?: boolean;
  capacity_lb?: number;
  food_bank_ids?: string[];
}
export interface SurplusOfferInput {
  donor_id: string;
  deadline: string;
  recall_notice: boolean;
  items: SurplusItemInput[];
  drop_off: DropOff;
}
export interface SurplusOfferCreated extends Labelled {
  lot_id: string;
  version: number;
  status: string;
  items: { produce_id: string; name: string; pounds: number }[];
  needs_human: string[];
  message: string;
}

// The draft agreement (get_lot.draft, list_approvals.terms)
export interface DraftItem {
  produce_id: string;
  pounds: number;
  condition_grade: string;
  usable_until: string;
  condition_doubt?: string | null;
}
export interface Allocation {
  produce_id: string;
  food_bank_id: string;
  pounds: number;
}
export interface Transport {
  food_bank_id?: string;
  mover: Mover;
  departs_at: string;
  arrives_at: string;
}
export interface Draft {
  lot_id: string;
  version: number;
  based_on_version?: number | null;
  proposer_id: string;
  reason: string;
  donor_id: string;
  deadline: string;
  items: DraftItem[];
  allocations: Allocation[];
  transports: Transport[];
  drop_off_to?: string[];
  drop_off_refrigerated?: boolean;
  names?: Record<string, string>;
}

// get_lot
export interface LotItem {
  produce_id: string;
  name: string;
  pounds: number;
  status: string;
  split?: { food_bank_id: string; pounds: number; mover: Mover }[];
  unclaimed_lb?: number;
  unclaimed_reason?: string;
  households_reached?: number;
  condition_doubt?: string | null;
}
export interface Lot extends Labelled {
  lot_id: string;
  donor_id: string;
  status: string;
  current_version: number;
  deadline: string;
  items: LotItem[];
  draft: Draft;
  approvals: { organization_id: string; version: number; decision: string }[];
  awaiting_approval_from: string[];
  disagreement: unknown;
}

// list_lot_versions
export interface Amendment {
  kind: 'set_pounds' | 'shift_pounds' | 'set_transport' | string;
  produce_id?: string;
  food_bank_id?: string;
  from_food_bank_id?: string;
  to_food_bank_id?: string;
  pounds?: number;
  mover?: Mover;
  departs_at?: string;
  arrives_at?: string;
}
export interface LotVersion {
  version: number;
  proposer_id: string;
  move: string;
  reason: string;
  change: Amendment | null;
}
export interface LotVersions extends Labelled {
  lot_id: string;
  versions: LotVersion[];
  current_version: number;
}

// get_food_bank_dashboard
export interface StorageWindow {
  window: TimeWindow;
  cold_free_lb: number;
  dry_free_lb: number;
}
export interface Truck {
  window: TimeWindow;
  refrigerated: boolean;
  capacity_lb: number;
}
export interface Cooler {
  status: string;
  temperature_c?: number;
  source?: string;
  synthetic?: boolean;
}
export interface Capacity {
  storage: StorageWindow[] | null;
  pickup_windows: TimeWindow[] | null;
  truck: Truck | null;
  cooler: Cooler | null;
}
export interface IncomingOffer {
  lot_id: string;
  version: number;
  donor_id: string;
  donor_name: string;
  for_us: { produce_id: string; name: string; pounds: number }[];
  transport: Transport | null;
  agent_suggests: string | null;
  agent_reason: string;
  needs_your_approval: boolean;
}
export interface FairShareGap {
  households: number;
  people: number;
  below_fair_share_lb: number;
  limited_fridge: number;
  evening_only: number;
  table_version?: string;
}
export interface Disagreement {
  lot_id: string;
  reason: unknown;
}
export interface ExpectedArrival {
  lot_id: string;
  version: number;
  arrives_at: string;
  items: { produce_id: string; pounds: number }[];
  status: string;
}

// Disruption reason cards (core #23, Lane B cooler_failure_flow.dashboard())
export interface ReasonCard {
  food_bank_id: string;
  name: string;
  outcome: 'chosen' | 'rejected' | string;
  text: string;
  reasons: string[];
  facts?: Record<string, unknown>;
}
export interface DisruptionItem {
  produce_id: string;
  pounds: number;
  reason: string;
}
export interface DisruptionView {
  food_bank_id: string;
  status: string;
  synthetic?: boolean;
  reading?: Record<string, unknown>;
  flags?: string[];
  profile_set_version?: string;
  items?: { move: DisruptionItem[]; stay: DisruptionItem[]; human_check: DisruptionItem[] };
  reason_cards?: ReasonCard[];
  fallback?: { produce_id: string; pounds: number; kind: string; reason: string }[];
  new_version?: {
    version: number;
    based_on_version: number;
    status: string;
    receiving_food_bank_id: string;
    needs_approval_from: string[];
    terms_hash: string;
    committed: boolean;
  } | null;
}
export interface Disruption {
  lot_id: string;
  version: number;
  based_on_version: number;
  change: string;
  status: string;
  proposer_id: string;
  needs_approval_from: string[];
  approved_by: string[];
  declined_by: string[];
  needs_your_approval: boolean;
  dashboard: DisruptionView;
}

export interface FoodBankDashboard extends Labelled {
  food_bank_id: string;
  name: string;
  capacity: Capacity;
  incoming_offers: IncomingOffer[];
  fair_share_gap: FairShareGap;
  disagreements: Disagreement[];
  expected_arrivals: ExpectedArrival[];
  disruptions?: Disruption[];
}

// update_food_bank_status
export interface FoodBankStatusInput {
  storage: StorageWindow[];
  pickup_windows: TimeWindow[];
  truck: Truck;
}
export interface FoodBankStatusSaved extends Labelled {
  food_bank_id: string;
  status_version: number;
  updated_at: string;
  message: string;
}

// submit_counter
export interface CounterInput {
  organization_id: string;
  version: number;
  amendment: Amendment;
  reason: string;
}
export interface CounterQueued extends Labelled {
  lot_id: string;
  status: string;
  based_on_version: number;
  move: { organization_id: string; version: number; action: string; reason: string; amendment: Amendment };
  message: string;
}

// confirm_pickup
export interface PickupConfirmInput {
  food_bank_id: string;
  request_code: string;
}
export interface PickupConfirmed extends Labelled {
  pickup_id: string;
  request_code: string;
  food_bank_id: string;
  status: string;
  collected_lb: number;
  received_this_week_lb: number;
  fair_share_lb: number;
  confirmed_at: string;
  items: { produce_id: string; name: string; pounds: number }[];
}

// list_approvals
export interface ApprovalRequest {
  lot_id: string;
  version: number;
  terms_hash: string;
  requested_at: string;
  expires_at: string | null;
  why_you: string[];
  summary: string;
  terms: Draft | Record<string, unknown>;
  status: string;
  change?: string;
}
export interface ApprovalList extends Labelled {
  organization_id: string;
  approvals: ApprovalRequest[];
}

// record_approval
export interface ApprovalInput {
  lot_id: string;
  version: number;
  organization_id: string;
  terms_hash: string;
  decision: 'approve' | 'decline';
  receipt_id: string;
}
export interface ApprovalRecorded extends Labelled {
  lot_id: string;
  version: number;
  organization_id: string;
  decision: string;
  receipt_id: string | null;
  status: string;
  change_status?: string;
  committed: boolean;
  approved_by: string[];
  awaiting_approval_from: string[];
}

// Proposed core route (docs/core/README.md #9): POST /lots/{lot_id}/condition-checks.
// Not in the agreed contract yet, and the skeleton does not serve it.
export interface ConditionCheckInput {
  organization_id: string;
  version: number;
  produce_id: string;
  condition_grade: ConditionGrade;
  usable_until: string;
  reason: string;
}
export interface ConditionCheckRecorded extends Labelled {
  lot_id: string;
  version: number;
  status: string;
  committed: boolean;
}
