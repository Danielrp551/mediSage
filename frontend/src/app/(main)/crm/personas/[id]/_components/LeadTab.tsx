"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  Textarea,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular, ArrowRightRegular } from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import {
  createLead,
  getLeadHistory,
  getLeadStatus,
  transitionLead,
} from "@/actions/lead-lifecycle.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { LeadStatusHistoryItem, PersonLeadStatusDetail } from "@/types/crm.types";

import { StatusBadge } from "./StatusBadge";
import { TransitionControl } from "./TransitionControl";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "760px",
  },
  section: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  subtitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  metaRow: { display: "flex", gap: tokens.spacingHorizontalL, flexWrap: "wrap" },
  metaLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  metaValue: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  actionsRow: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
    alignItems: "center",
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    minHeight: "200px",
  },
  history: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  historyItem: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  historyTransition: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  historyMeta: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  historyReason: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  arrow: { display: "inline-flex", color: appTokens.chromeTextMuted },
  loading: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
  },
});

interface Props {
  personId: string;
  canWrite: boolean;
  canReadHistory: boolean;
}

/**
 * Tab Lead (F3): estado lead actual + transición (matriz) + history. Carga en
 * cliente al montar (`getLeadStatus` + `getLeadHistory` si canReadHistory).
 *
 * - Sin lead activo (`null`) → estado vacío + "Crear lead" (gated canWrite).
 * - Con lead activo → StatusBadge + entered_status_at + source_campaign_id +
 *   TransitionControl + "Promover a cliente" DESHABILITADO (F4).
 */
export function LeadTab({ personId, canWrite, canReadHistory }: Props) {
  const styles = useStyles();
  const router = useRouter();

  const [lead, setLead] = useState<PersonLeadStatusDetail | null>(null);
  const [history, setHistory] = useState<LeadStatusHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reqIdRef = useRef(0);

  const load = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    const fetchStatus = getLeadStatus(personId);
    const fetchHistory = canReadHistory
      ? getLeadHistory(personId)
      : Promise.resolve<LeadStatusHistoryItem[]>([]);
    void Promise.all([fetchStatus, fetchHistory])
      .then(([status, hist]) => {
        if (reqId !== reqIdRef.current) return;
        setLead(status);
        setHistory(hist);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setError("No se pudo cargar el estado del lead. Intenta de nuevo.");
        setLoading(false);
      });
  }, [personId, canReadHistory]);

  useEffect(() => {
    load();
  }, [load]);

  // Tras crear/transicionar: refetch local del tab + router.refresh() para re-pintar
  // el badge de lead denormalizado del header (RSC), igual que AssignmentControl.
  const refresh = useCallback(() => {
    load();
    router.refresh();
  }, [load, router]);

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spinner size="tiny" />
        Cargando lead…
      </div>
    );
  }

  return (
    <div className={styles.root}>
      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}

      {lead ? (
        <ActiveLead lead={lead} canWrite={canWrite} styles={styles} onChanged={refresh} />
      ) : (
        <NoLead personId={personId} canWrite={canWrite} styles={styles} onCreated={refresh} />
      )}

      {canReadHistory ? <LeadHistory history={history} styles={styles} /> : null}
    </div>
  );
}

type Styles = ReturnType<typeof useStyles>;

function ActiveLead({
  lead,
  canWrite,
  styles,
  onChanged,
}: {
  lead: PersonLeadStatusDetail;
  canWrite: boolean;
  styles: Styles;
  onChanged: () => void;
}) {
  const [transitionError, setTransitionError] = useState<string | null>(null);

  const handleTransition = async (toId: string, reason?: string | null) => {
    setTransitionError(null);
    const result = await transitionLead(lead.person_id, {
      to_lead_status_id: toId,
      reason: reason ?? null,
    });
    if (!result.ok) {
      // 400 LEAD_TRANSITION_NOT_ALLOWED / NO_ACTIVE_LEAD en español.
      setTransitionError(result.error ?? "No se pudo cambiar el estado.");
      return;
    }
    onChanged();
  };

  return (
    <div className={styles.section}>
      <h2 className={styles.title}>Estado del lead</h2>
      <div className={styles.card}>
        <div className={styles.statusRow}>
          <StatusBadge status={lead.lead_status} fallback="Sin lead" />
        </div>

        <div className={styles.metaRow}>
          <div>
            <div className={styles.metaLabel}>En este estado desde</div>
            <div className={styles.metaValue}>{formatDate(lead.entered_status_at)}</div>
          </div>
          <div>
            <div className={styles.metaLabel}>Origen (campaña)</div>
            <div className={styles.metaValue}>{lead.source_campaign_id ?? "—"}</div>
          </div>
        </div>

        {transitionError ? (
          <MessageBar intent="error">
            <MessageBarBody>{transitionError}</MessageBarBody>
          </MessageBar>
        ) : null}

        {canWrite ? (
          <div className={styles.actionsRow}>
            <TransitionControl
              currentStatusId={lead.lead_status.id}
              kind="lead"
              onTransition={handleTransition}
            />
            {/* "Promover a cliente" llega en F4 (el endpoint de backend no existe en F3). */}
            <Tooltip content="Disponible en la fase Cliente" relationship="label" withArrow>
              <span>
                <Button appearance="secondary" icon={<ArrowRightRegular />} disabled>
                  Promover a cliente
                </Button>
              </span>
            </Tooltip>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function NoLead({
  personId,
  canWrite,
  styles,
  onCreated,
}: {
  personId: string;
  canWrite: boolean;
  styles: Styles;
  onCreated: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [reason, setReason] = useState("");
  const [sourceCampaignId, setSourceCampaignId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const handleCreate = () => {
    setError(null);
    startTransition(async () => {
      const result = await createLead(personId, {
        reason: reason.trim() ? reason.trim() : null,
        source_campaign_id: sourceCampaignId.trim() ? sourceCampaignId.trim() : null,
      });
      if (!result.ok) {
        // 400 NO_INITIAL_LEAD_STATUS / 409 ALREADY_HAS_ACTIVE_LEAD en español.
        setError(result.error ?? "No se pudo crear el lead.");
        return;
      }
      setCreating(false);
      setReason("");
      setSourceCampaignId("");
      onCreated();
    });
  };

  if (creating) {
    return (
      <div className={styles.section}>
        <h2 className={styles.title}>Crear lead</h2>
        <div className={styles.card}>
          {error ? (
            <MessageBar intent="error">
              <MessageBarBody>{error}</MessageBarBody>
            </MessageBar>
          ) : null}
          <FormField label="Origen (campaña)">
            <Textarea
              value={sourceCampaignId}
              onChange={(_, d) => setSourceCampaignId(d.value)}
              rows={1}
              placeholder="ID de campaña (opcional)"
              disabled={pending}
            />
          </FormField>
          <FormField label="Motivo (opcional)">
            <Textarea
              value={reason}
              onChange={(_, d) => setReason(d.value)}
              rows={3}
              placeholder="Anota por qué creas el lead…"
              disabled={pending}
            />
          </FormField>
          <div className={styles.actionsRow}>
            <Button appearance="secondary" disabled={pending} onClick={() => setCreating(false)}>
              Cancelar
            </Button>
            <Button appearance="primary" disabled={pending} onClick={handleCreate}>
              {pending ? "Creando…" : "Crear lead"}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.empty}>
      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}
      <span>Esta persona no tiene un lead activo.</span>
      {canWrite ? (
        <Button appearance="primary" icon={<AddRegular />} onClick={() => setCreating(true)}>
          Crear lead
        </Button>
      ) : null}
    </div>
  );
}

function LeadHistory({ history, styles }: { history: LeadStatusHistoryItem[]; styles: Styles }) {
  return (
    <div className={styles.section}>
      <h3 className={styles.subtitle}>Historial de estados</h3>
      {history.length === 0 ? (
        <p className={styles.historyMeta}>Aún no hay cambios de estado.</p>
      ) : (
        <div className={styles.history}>
          {history.map((h) => (
            <div key={h.id} className={styles.historyItem}>
              <div className={styles.historyTransition}>
                {h.from_lead_status ? (
                  <StatusBadge status={h.from_lead_status} />
                ) : (
                  <span className={styles.historyMeta}>(inicial)</span>
                )}
                <span className={styles.arrow}>
                  <ArrowRightRegular />
                </span>
                <StatusBadge status={h.to_lead_status} />
              </div>
              <div className={styles.historyMeta}>
                {(h.changed_by_user?.full_name ?? "Sistema") + " · " + formatDate(h.changed_at)}
              </div>
              {h.reason ? <div className={styles.historyReason}>{h.reason}</div> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
