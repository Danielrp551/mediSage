"use client";

import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  CalendarLtrRegular,
  CalendarSyncRegular,
  DismissRegular,
  MailRegular,
} from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { startOAuth } from "@/actions/calendar.actions";
import { usePermissions } from "@/hooks/usePermissions";
import { CALENDAR_ERROR_LABELS } from "@/lib/constants/calendar-providers";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { CalendarConnectionItem, CalendarProvider } from "@/types/calendar.types";
import type { BranchOption } from "@/types/clinic.types";

import { ConnectionCard } from "./ConnectionCard";

const ROUTE = "/clinic/calendarios-externos";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "880px",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase600,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  subtitle: {
    margin: `${tokens.spacingVerticalXS} 0 0`,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
    maxWidth: "560px",
  },
  readonlyHint: {
    margin: 0,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontStyle: "italic",
  },
  toolbar: { display: "flex", gap: tokens.spacingHorizontalS, flexWrap: "wrap" },
  list: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXL} ${tokens.spacingHorizontalM}`,
    textAlign: "center",
    border: `1px dashed ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
    color: appTokens.chromeTextMuted,
  },
  emptyIcon: { fontSize: "40px", opacity: 0.7 },
  emptyTitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  emptyMsg: { margin: 0, maxWidth: "420px" },
});

interface Props {
  initialData: ApiPaginated<CalendarConnectionItem>;
  branches: BranchOption[];
  /** ?calendar_error=CODE que el callback público dejó al volver de un OAuth fallido. */
  oauthError: string | null;
}

/**
 * Orquestador de la config de calendarios externos (no es una DataTable: es una lista de
 * cards). Header con "Conectar Google/Outlook" (gated WRITE) → Server Action `startOAuth` que
 * devuelve `{ auth_url }` y el CLIENTE redirige el navegador. Banner del `?calendar_error` (se
 * limpia de la URL tras leerlo). Tras una mutación, `router.refresh()` re-ejecuta el RSC (el
 * tag `calendar:connections` ya se revalidó en el action) y la lista se re-pinta.
 */
export function CalendarConnectionsClient({ initialData, branches, oauthError }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("CALENDAR_CONNECTIONS_WRITE");

  const [errorCode, setErrorCode] = useState<string | null>(oauthError);
  const [actionError, setActionError] = useState<string | null>(null);

  // El 302 del callback llega con ?calendar_error en el primer render del RSC → se limpia de la
  // URL (sin recargar) para que un refresh no lo repita; el banner sigue visible vía estado.
  useEffect(() => {
    if (oauthError) router.replace(ROUTE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = initialData.data.items;

  const onConnect = async (provider: CalendarProvider) => {
    setActionError(null);
    // return_to ABSOLUTO (origin + path): el callback público del backend hace
    // `RedirectResponse(url=return_to)` crudo desde SU host → un path relativo aterrizaría en el
    // backend (404). El origin del navegador es el del frontend (donde el usuario clickeó).
    const res = await startOAuth(provider, `${window.location.origin}${ROUTE}`);
    if (res.ok && res.data) {
      window.location.href = res.data.auth_url; // redirect del navegador al consentimiento
    } else {
      setActionError(res.error ?? "No se pudo iniciar la conexión.");
    }
  };

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Calendarios externos</h1>
          <p className={styles.subtitle}>
            Conecta los calendarios de Google u Outlook de la clínica para ver su ocupación junto a
            la agenda.
          </p>
        </div>
        {canWrite ? (
          <div className={styles.toolbar}>
            <Button
              appearance="primary"
              icon={<CalendarLtrRegular />}
              onClick={() => void onConnect("google")}
            >
              Conectar Google
            </Button>
            <Button
              appearance="secondary"
              icon={<MailRegular />}
              onClick={() => void onConnect("microsoft")}
            >
              Conectar Outlook
            </Button>
          </div>
        ) : null}
      </div>

      {!canWrite ? (
        <p className={styles.readonlyHint}>
          Solo un administrador puede conectar o mapear calendarios.
        </p>
      ) : null}

      {errorCode ? (
        <MessageBar intent="error">
          <MessageBarBody>
            {CALENDAR_ERROR_LABELS[errorCode] ?? "No se pudo completar la conexión."}
          </MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button
                appearance="transparent"
                icon={<DismissRegular />}
                aria-label="Cerrar"
                onClick={() => setErrorCode(null)}
              />
            }
          />
        </MessageBar>
      ) : null}

      {actionError ? (
        <MessageBar intent="error">
          <MessageBarBody>{actionError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {items.length === 0 ? (
        <div className={styles.empty}>
          <CalendarSyncRegular className={styles.emptyIcon} />
          <h2 className={styles.emptyTitle}>Aún no hay calendarios conectados</h2>
          <p className={styles.emptyMsg}>
            Conecta el calendario de Google u Outlook de la clínica para ver su ocupación junto a la
            agenda.
          </p>
        </div>
      ) : (
        <div className={styles.list}>
          {items.map((c) => (
            <ConnectionCard
              key={c.id}
              connection={c}
              branches={branches}
              canWrite={canWrite}
              onChanged={() => router.refresh()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
