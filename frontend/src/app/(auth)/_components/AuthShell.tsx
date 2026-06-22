"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import type { ReactNode } from "react";

import { appTokens, brandPalette } from "@/lib/theme/brand";

const useStyles = makeStyles({
  root: {
    minHeight: "100vh",
    display: "grid",
    gridTemplateColumns: "1fr",
    "@media (min-width: 960px)": {
      gridTemplateColumns: "1.1fr 1fr",
    },
  },
  hero: {
    display: "none",
    position: "relative",
    padding: tokens.spacingVerticalXXXL,
    color: "#FFFFFF",
    background: `linear-gradient(135deg, ${brandPalette.primary} 0%, ${brandPalette.primaryPressed} 100%)`,
    overflow: "hidden",
    "@media (min-width: 960px)": {
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
    },
  },
  heroMark: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    fontWeight: tokens.fontWeightSemibold,
    fontSize: tokens.fontSizeBase400,
    letterSpacing: "-0.01em",
  },
  heroMarkDot: {
    width: "12px",
    height: "12px",
    borderRadius: "3px",
    backgroundColor: "rgba(255, 255, 255, 0.9)",
  },
  heroBody: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "440px",
  },
  heroHeadline: {
    fontSize: "42px",
    lineHeight: 1.1,
    fontWeight: tokens.fontWeightSemibold,
    letterSpacing: "-0.02em",
    margin: 0,
  },
  heroSubcopy: {
    fontSize: tokens.fontSizeBase400,
    lineHeight: 1.55,
    color: "rgba(255, 255, 255, 0.86)",
    margin: 0,
  },
  heroFooter: {
    fontSize: tokens.fontSizeBase200,
    color: "rgba(255, 255, 255, 0.7)",
  },
  heroDecor: {
    position: "absolute",
    right: "-160px",
    bottom: "-160px",
    width: "440px",
    height: "440px",
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 70%)",
    pointerEvents: "none",
  },
  form: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: tokens.spacingVerticalXXL,
    backgroundColor: appTokens.contentBg,
  },
});

export function AuthShell({ children }: { children: ReactNode }) {
  const styles = useStyles();
  return (
    <main className={styles.root}>
      <aside className={styles.hero} aria-hidden>
        <div className={styles.heroMark}>
          <span className={styles.heroMarkDot} />
          Medisage
        </div>
        <div className={styles.heroBody}>
          <h1 className={styles.heroHeadline}>Atención y reservas, automatizadas.</h1>
          <p className={styles.heroSubcopy}>
            Chatbots conversacionales, gestión de citas y CRM para clínicas
            especializadas, en una sola plataforma.
          </p>
        </div>
        <div className={styles.heroFooter}>© Medisage · Consola interna</div>
        <span className={styles.heroDecor} />
      </aside>

      <section className={styles.form}>{children}</section>
    </main>
  );
}
