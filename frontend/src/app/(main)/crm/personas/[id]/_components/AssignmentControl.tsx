"use client";

import {
  Avatar,
  Button,
  Menu,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { PersonAddRegular, PersonArrowBackRegular, PersonSwapRegular } from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { assignAdvisor, assignAuto, listActiveAdvisors } from "@/actions/lead-assignment.actions";
import { useAuth } from "@/providers/AuthProvider";
import { appTokens } from "@/lib/theme/brand";
import type { UserAuditInfo } from "@/types/audit.types";
import type { AdvisorOption } from "@/types/crm.types";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  row: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS, flexWrap: "wrap" },
  advisor: { display: "inline-flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  advisorName: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  unassigned: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  loadingItem: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
});

interface Props {
  personId: string;
  currentAdvisor: UserAuditInfo | null;
  canWrite: boolean;
}

/**
 * Muestra el asesor asignado + (si canWrite) los controles de asignación:
 * "Asignarme" (al user logueado), "Reasignar" (dropdown de asesores activos) y
 * "Asignar automático" (round-robin). Tras asignar, `router.refresh()` re-pinta
 * el header (la asignación afecta el badge denormalizado).
 */
export function AssignmentControl({ personId, currentAdvisor, canWrite }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { user } = useAuth();

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Asesores para el dropdown de "Reasignar" — se cargan al abrir el menú.
  const [advisors, setAdvisors] = useState<AdvisorOption[] | null>(null);
  const [advisorsLoading, setAdvisorsLoading] = useState(false);

  const loadAdvisors = () => {
    if (advisors !== null || advisorsLoading) return;
    setAdvisorsLoading(true);
    void listActiveAdvisors()
      .then((rows) => setAdvisors(rows))
      .catch(() => setAdvisors([]))
      .finally(() => setAdvisorsLoading(false));
  };

  const runAssign = async (fn: () => Promise<{ ok: boolean; error?: string }>) => {
    setError(null);
    setBusy(true);
    const result = await fn();
    setBusy(false);
    if (result.ok) {
      router.refresh();
    } else {
      setError(result.error ?? "No se pudo completar la asignación.");
    }
  };

  return (
    <div className={styles.root}>
      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.row}>
        {currentAdvisor ? (
          <span className={styles.advisor}>
            <Avatar size={24} name={currentAdvisor.full_name} color="colorful" />
            <span className={styles.advisorName}>{currentAdvisor.full_name}</span>
          </span>
        ) : (
          <span className={styles.unassigned}>Sin asignar</span>
        )}

        {canWrite ? (
          <>
            {user ? (
              <Button
                appearance="secondary"
                size="small"
                icon={<PersonArrowBackRegular />}
                disabled={busy}
                onClick={() =>
                  void runAssign(() => assignAdvisor(personId, { advisor_user_id: user.id }))
                }
              >
                Asignarme
              </Button>
            ) : null}

            <Menu positioning="below-start" onOpenChange={(_, d) => d.open && loadAdvisors()}>
              <MenuTrigger disableButtonEnhancement>
                <Button
                  appearance="secondary"
                  size="small"
                  icon={<PersonSwapRegular />}
                  disabled={busy}
                >
                  Reasignar
                </Button>
              </MenuTrigger>
              <MenuPopover>
                <MenuList>
                  {advisorsLoading ? (
                    <MenuItem disabled>
                      <span className={styles.loadingItem}>
                        <Spinner size="tiny" /> Cargando…
                      </span>
                    </MenuItem>
                  ) : advisors && advisors.length > 0 ? (
                    advisors.map((a) => (
                      <MenuItem
                        key={a.id}
                        onClick={() =>
                          void runAssign(() => assignAdvisor(personId, { advisor_user_id: a.id }))
                        }
                      >
                        {a.full_name}
                      </MenuItem>
                    ))
                  ) : (
                    <MenuItem disabled>No hay asesores activos.</MenuItem>
                  )}
                </MenuList>
              </MenuPopover>
            </Menu>

            <Button
              appearance="secondary"
              size="small"
              icon={<PersonAddRegular />}
              disabled={busy}
              onClick={() => void runAssign(() => assignAuto(personId))}
            >
              Asignar automático
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
