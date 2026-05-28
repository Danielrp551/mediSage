"use client";

import {
  Button,
  Input,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { EyeOffRegular, EyeRegular } from "@fluentui/react-icons";
import { useActionState, useState } from "react";

import { loginAction } from "@/actions/auth.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  root: {
    width: "100%",
    maxWidth: "400px",
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXL,
  },
  header: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  title: {
    margin: 0,
    fontSize: "28px",
    lineHeight: 1.2,
    fontWeight: tokens.fontWeightSemibold,
    letterSpacing: "-0.02em",
    color: appTokens.chromeText,
  },
  subtitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
    lineHeight: 1.5,
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
  },
  submit: { marginTop: tokens.spacingVerticalS },
  visibilityBtn: {
    minWidth: "32px",
    padding: 0,
  },
  footnote: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    textAlign: "center",
  },
});

interface Props {
  redirectTo: string;
}

export function LoginForm({ redirectTo }: Props) {
  const styles = useStyles();
  const [state, formAction, pending] = useActionState(loginAction, null);
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Bienvenido de vuelta</h1>
        <p className={styles.subtitle}>
          Inicia sesión para continuar a la consola admin.
        </p>
      </header>

      {state?.error ? (
        <MessageBar intent="error">
          <MessageBarBody>{state.error}</MessageBarBody>
        </MessageBar>
      ) : null}

      <form action={formAction} className={styles.form}>
        <input type="hidden" name="redirect" value={redirectTo} />

        <FormField label="Correo" required error={state?.fieldErrors?.email?.[0]}>
          <Input
            name="email"
            type="email"
            autoComplete="email"
            placeholder="tu@ejemplo.com"
            required
            disabled={pending}
          />
        </FormField>

        <FormField label="Contraseña" required error={state?.fieldErrors?.password?.[0]}>
          <Input
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            placeholder="Tu contraseña"
            required
            disabled={pending}
            contentAfter={
              <Button
                appearance="transparent"
                size="small"
                className={styles.visibilityBtn}
                icon={showPassword ? <EyeOffRegular /> : <EyeRegular />}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                tabIndex={-1}
              />
            }
          />
        </FormField>

        <Button
          type="submit"
          appearance="primary"
          size="large"
          disabled={pending}
          className={styles.submit}
          icon={pending ? <Spinner size="tiny" /> : undefined}
        >
          {pending ? "Iniciando sesión…" : "Iniciar sesión"}
        </Button>
      </form>

      <p className={styles.footnote}>
        ¿Olvidaste tu contraseña? Contacta a tu administrador.
      </p>
    </div>
  );
}
