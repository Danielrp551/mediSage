"use client";

/**
 * Init LAZY + CLIENT-ONLY del Firebase Web SDK para los listeners READ-ONLY del
 * hilo de conversaciones (rediseño CQRS, ADR-011). El browser SOLO lee el stream
 * de mensajes de Firestore (`onSnapshot`); jamás escribe (Security Rules
 * `allow write: if false`) — toda escritura va por el backend (server-side).
 *
 * Por qué lazy + singleton:
 * - El `next build` colecciona/pre-renderiza las páginas con envs dummy o
 *   ausentes. Si el `initializeApp` corriera en import-time (módulo) crashearía
 *   la colección de la página. Por eso TODO init se difiere al primer uso en el
 *   browser (`getFirebaseApp()`), nunca en SSR ni en module-eval.
 * - `getApps()` evita un doble `initializeApp` con el HMR de dev.
 *
 * Config PÚBLICA (no secreta) — viene de `NEXT_PUBLIC_FIREBASE_*`. El `apiKey`
 * identifica el proyecto pero NO autoriza por sí solo: la autorización la dan el
 * Custom Token (que minta el backend con el JWT del asesor) + las Security Rules.
 *
 * Solo se importan tres sub-paths del SDK: `firebase/app`, `firebase/auth`,
 * `firebase/firestore`. NO `firebase/storage` (adjuntos = F4, vía GCS server-side).
 */

import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, signInWithCustomToken, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

// Lee la config pública en el momento de uso (no en module-eval) para no leer
// `process.env` en un contexto donde podría no existir. Devuelve null si falta
// la config mínima → el caller cae al fallback server-side (sin real-time).
function readFirebaseConfig(): {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  messagingSenderId?: string;
} | null {
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  const authDomain = process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN;
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  const appId = process.env.NEXT_PUBLIC_FIREBASE_APP_ID;
  if (!apiKey || !authDomain || !projectId || !appId) return null;
  return {
    apiKey,
    authDomain,
    projectId,
    appId,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  };
}

// named DB por entorno (medisage-qa / medisage) — el SDK debe apuntar a la DB
// nombrada, NO a la (default). Brief §1 / ADR-011.
function databaseId(): string | undefined {
  return process.env.NEXT_PUBLIC_FIREBASE_DATABASE_ID || undefined;
}

/**
 * Firebase app singleton — un único `initializeApp` por sesión del browser.
 * Lanza si la config pública no está (el caller lo trata como "sin real-time").
 */
export function getFirebaseApp(): FirebaseApp {
  if (getApps().length > 0) return getApp();
  const config = readFirebaseConfig();
  if (!config) {
    throw new Error(
      "Firebase no está configurado (faltan NEXT_PUBLIC_FIREBASE_*). El hilo usará el fallback server-side.",
    );
  }
  return initializeApp(config);
}

/** Auth del browser (lazy). */
export function getFirebaseAuth(): Auth {
  return getAuth(getFirebaseApp());
}

/** Firestore apuntando a la DB nombrada por entorno (lazy). Sin DATABASE_ID → la (default). */
export function getFirestoreDb(): Firestore {
  const dbId = databaseId();
  return dbId ? getFirestore(getFirebaseApp(), dbId) : getFirestore(getFirebaseApp());
}

/**
 * `signInWithCustomToken` idempotente: la primera llamada autentica con el
 * Custom Token que mintó el backend; las siguientes reusan la promesa (un solo
 * sign-in por sesión del browser). Devuelve la `Firestore` (DB nombrada) lista
 * para abrir listeners READ-ONLY. El ID token resultante dura ~1h y se
 * auto-refresca mientras la sesión de Firebase viva.
 */
let signInPromise: Promise<Firestore> | null = null;

export async function signInWithToken(token: string): Promise<Firestore> {
  if (signInPromise) return signInPromise;
  signInPromise = (async () => {
    try {
      const auth = getFirebaseAuth();
      await signInWithCustomToken(auth, token);
      return getFirestoreDb();
    } catch (e) {
      // NO cachear un sign-in FALLIDO: reseteamos el singleton para que un token válido
      // posterior (cambio de conversación / re-mint en F3) pueda reintentar, en vez de
      // quedar fijado a una promesa rechazada (hilo atascado en fallback toda la sesión).
      signInPromise = null;
      throw e;
    }
  })();
  return signInPromise;
}
