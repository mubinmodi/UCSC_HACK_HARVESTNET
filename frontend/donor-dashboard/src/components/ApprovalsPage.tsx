import { ClipboardCheck } from 'lucide-react';
import { api } from '../api';
import { useLoad } from '../useLoad';
import { ApprovalCard } from './Decisions';
import { DataLabel, ErrorNote, PageHeading } from './ui';

/** Approval requests waiting for one organization's human. Each needs an explicit decision. */
export function ApprovalsPage({ organizationId, roleLabel }: { organizationId: string; roleLabel: string }) {
  const list = useLoad(() => api.listApprovals(organizationId), [organizationId]);
  return (
    <>
      <PageHeading
        icon={<ClipboardCheck />}
        title="Approvals"
        subtitle={`Plans waiting for a decision from ${roleLabel} staff. Each decision covers one exact version. No reply means no approval.`}
      />
      {list.loading && <p role="status">Loading approval requests…</p>}
      <ErrorNote message={list.error} />
      {list.data && (
        <>
          <DataLabel data={list.data} />
          {list.data.approvals.length === 0 && <p className="muted empty">Nothing is waiting for you.</p>}
          <div className="offer-list">
            {list.data.approvals.map((a) => (
              <ApprovalCard key={`${a.lot_id}:${a.version}:${a.terms_hash}`} approval={a} organizationId={organizationId} />
            ))}
          </div>
        </>
      )}
    </>
  );
}
