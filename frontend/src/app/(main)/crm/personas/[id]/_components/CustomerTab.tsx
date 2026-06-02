"use client";

import {
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowRightRegular } from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getCustomerHistory,
  getCustomerStatus,
  transitionCustomer,
} from "@/actions/lead-lifecycle.actions";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { CustomerStatusHistoryItem, PersonCustomerStatusDetail } from "@/types/crm.types";

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
 * Tab Cliente (F4): estado cliente actual + transición (matriz customer) +
 * history. Carga en cliente al montar (`getCustomerStatus` + `getCustomerHistory`
 * si canReadHistory).
 *
 * - Sin ficha de cliente (`null`) → estado vacío que remite al tab Lead (la
 *   promoción NACE desde "Promover a cliente" del tab Lead, no acá).
 * - Con ficha → StatusBadge + became_customer_at + entered_status_at +
 *   TransitionControl (kind="customer").
 */
export function CustomerTab({ personId, canWrite, canReadHistory }: Props) {
  const styles = useStyles();
  const router = useRouter();

  const [customer, setCustomer] = useState<PersonCustomerStatusDetail | null>(null);
  const [history, setHistory] = useState<CustomerStatusHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reqIdRef = useRef(0);

  const load = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    const fetchStatus = getCustomerStatus(personId);
    const fetchHistory = canReadHistory
      ? getCustomerHistory(personId)
      : Promise.resolve<CustomerStatusHistoryItem[]>([]);
    void Promise.all([fetchStatus, fetchHistory])
      .then(([status, hist]) => {
        if (reqId !== reqIdRef.current) return;
        setCustomer(status);
        setHistory(hist);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setError("No se pudo cargar el estado del cliente. Intenta de nuevo.");
        setLoading(false);
      });
  }, [personId, canReadHistory]);

  useEffect(() => {
    load();
  }, [load]);

  // Tras transicionar: refetch local del tab + router.refresh() para re-pintar el
  // badge de cliente denormalizado del header (RSC), igual que LeadTab.
  const refresh = useCallback(() => {
    load();
    router.refresh();
  }, [load, router]);

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spinner size="tiny" />
        Cargando cliente…
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

      {customer ? (
        <ActiveCustomer
          customer={customer}
          canWrite={canWrite}
          styles={styles}
          onChanged={refresh}
        />
      ) : (
        // `history.length > 0` ⇒ fue cliente y se cerró (transición a is_final); de lo
        // contrario nunca fue cliente. (Si no hay permiso de historial, history es []
        // y cae al copy genérico — el usuario no puede ver la traza igual.)
        <NoCustomer wasCustomer={history.length > 0} styles={styles} />
      )}

      {canReadHistory ? <CustomerHistory history={history} styles={styles} /> : null}
    </div>
  );
}

type Styles = ReturnType<typeof useStyles>;

function ActiveCustomer({
  customer,
  canWrite,
  styles,
  onChanged,
}: {
  customer: PersonCustomerStatusDetail;
  canWrite: boolean;
  styles: Styles;
  onChanged: () => void;
}) {
  const [transitionError, setTransitionError] = useState<string | null>(null);

  const handleTransition = async (toId: string, reason?: string | null) => {
    setTransitionError(null);
    const result = await transitionCustomer(customer.person_id, {
      to_customer_status_id: toId,
      reason: reason ?? null,
    });
    if (!result.ok) {
      // 400 CUSTOMER_TRANSITION_NOT_ALLOWED / NOT_A_CUSTOMER en español.
      setTransitionError(result.error ?? "No se pudo cambiar el estado.");
      return;
    }
    onChanged();
  };

  return (
    <div className={styles.section}>
      <h2 className={styles.title}>Estado del cliente</h2>
      <div className={styles.card}>
        <div className={styles.statusRow}>
          <StatusBadge status={customer.customer_status} fallback="Sin cliente" />
        </div>

        <div className={styles.metaRow}>
          <div>
            <div className={styles.metaLabel}>En este estado desde</div>
            <div className={styles.metaValue}>{formatDate(customer.entered_status_at)}</div>
          </div>
          <div>
            <div className={styles.metaLabel}>Cliente desde</div>
            <div className={styles.metaValue}>{formatDate(customer.became_customer_at)}</div>
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
              currentStatusId={customer.customer_status.id}
              kind="customer"
              onTransition={handleTransition}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function NoCustomer({ wasCustomer, styles }: { wasCustomer: boolean; styles: Styles }) {
  return (
    <div className={styles.empty}>
      <span>
        {wasCustomer
          ? "Este contacto ya no es cliente. Revisa el historial debajo."
          : "Este contacto aún no es cliente. Promuévelo desde el tab Lead."}
      </span>
    </div>
  );
}

function CustomerHistory({
  history,
  styles,
}: {
  history: CustomerStatusHistoryItem[];
  styles: Styles;
}) {
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
                {h.from_customer_status ? (
                  <StatusBadge status={h.from_customer_status} />
                ) : (
                  <span className={styles.historyMeta}>(inicial)</span>
                )}
                <span className={styles.arrow}>
                  <ArrowRightRegular />
                </span>
                <StatusBadge status={h.to_customer_status} />
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
