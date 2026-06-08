"use client";

import {
  getCustomerTransitions,
  listActiveCustomerStatuses,
  setCustomerTransitions,
} from "@/actions/customer-status.actions";
import {
  getLeadTransitions,
  listActiveLeadStatuses,
  setLeadTransitions,
} from "@/actions/lead-status.actions";
import { TransitionMatrixEditor } from "@/components/ui/TransitionMatrixEditor/TransitionMatrixEditor";

interface Props {
  statusId: string;
  kind: "lead" | "customer";
  isFinal?: boolean;
  /** Sin permiso `_WRITE` el multiselect es de solo lectura. */
  canWrite?: boolean;
}

/**
 * Adaptador crm sobre el editor genérico `TransitionMatrixEditor`: enlaza las
 * actions de lead/customer según `kind` (inyección de dependencias) y conserva la
 * firma histórica `{statusId, kind, isFinal, canWrite}` para que los drawers de crm
 * (LeadStatusDrawer / CustomerStatusDrawer) no cambien. La UX es idéntica.
 */
export function StatusMatrixEditor({ statusId, kind, isFinal = false, canWrite = true }: Props) {
  const isLead = kind === "lead";
  return (
    <TransitionMatrixEditor
      statusId={statusId}
      subjectLabel={isLead ? "un lead" : "un cliente"}
      isFinal={isFinal}
      canWrite={canWrite}
      fetchOptions={() => (isLead ? listActiveLeadStatuses() : listActiveCustomerStatuses())}
      fetchSelectedIds={async () => {
        const targets = isLead
          ? await getLeadTransitions(statusId)
          : await getCustomerTransitions(statusId);
        return targets.to.map((o) => o.id);
      }}
      onSave={(toIds) =>
        isLead
          ? setLeadTransitions(statusId, { to_ids: toIds })
          : setCustomerTransitions(statusId, { to_ids: toIds })
      }
    />
  );
}
