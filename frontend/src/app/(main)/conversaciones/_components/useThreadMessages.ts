"use client";

/**
 * Hook del listener Firestore real-time del hilo (pieza nueva del rediseño CQRS,
 * ADR-011). Abre `onSnapshot(conversations/{cid}/messages orderBy created_at)`
 * (READ-ONLY) y expone los mensajes indexados por id. Maneja:
 * - el sign-in idempotente (vía `lib/firebase/client.ts`),
 * - el cleanup del listener al cambiar de conversación / desmontar,
 * - la degradación a FALLBACK server-side (`listMessages`) si Firebase no está
 *   disponible o el custom token falla — el hilo nunca queda inutilizable.
 *
 * El cliente JAMÁS escribe Firestore: solo `query`/`collection`/`onSnapshot`
 * (lectura). Toda escritura va por el backend (Composer/handoff = F3).
 */

import {
  collection,
  onSnapshot,
  orderBy,
  query,
  type DocumentData,
  type QueryDocumentSnapshot,
  type QuerySnapshot,
} from "firebase/firestore";
import { useEffect, useRef, useState } from "react";

import { listMessages } from "@/actions/conversation.actions";
import { signInWithToken } from "@/lib/firebase/client";
import type { MessageItem } from "@/types/conversations.types";

export type ThreadStatus = "loading" | "live" | "fallback" | "error";

function indexById(items: MessageItem[]): Record<string, MessageItem> {
  const out: Record<string, MessageItem> = {};
  for (const m of items) out[m.id] = m;
  return out;
}

export function useThreadMessages(conversationId: string, realtimeToken: string | null) {
  const [messages, setMessages] = useState<Record<string, MessageItem>>({});
  const [status, setStatus] = useState<ThreadStatus>("loading");
  // Token monotónico: descarta listeners/fetches viejos al cambiar de conversación
  // rápido (una respuesta vieja no pisa la nueva).
  const reqIdRef = useRef(0);

  useEffect(() => {
    const reqId = ++reqIdRef.current;
    setMessages({}); // reset al cambiar de conversación
    setStatus("loading");
    let unsubscribe: (() => void) | undefined;

    void (async () => {
      // Fallback server-side: sin token (sign-in falló / sin Firebase) leemos
      // Firestore vía Admin SDK por /messages/list. El hilo se ve, sin real-time.
      const fallback = async () => {
        try {
          // El fallback lee Firestore vía Admin SDK; el campo de orden del doc es
          // `created_at` (brief §1), igual que el listener real-time.
          const res = await listMessages(conversationId, {
            pagination: { skip: 0, limit: 100 },
            sorting: { sort_by: "created_at", sort_order: "asc" },
            filters: null,
          });
          if (reqId !== reqIdRef.current) return;
          setMessages(indexById(res.data.items));
          setStatus("fallback");
        } catch {
          if (reqId !== reqIdRef.current) return;
          setStatus("error");
        }
      };

      if (!realtimeToken) {
        await fallback();
        return;
      }

      try {
        const db = await signInWithToken(realtimeToken); // idempotente
        if (reqId !== reqIdRef.current) return;
        // READ-ONLY: subcolección de mensajes del doc de la conversación, orden
        // cronológico por created_at (campo del doc Firestore, brief §1).
        const q = query(
          collection(db, "conversations", conversationId, "messages"),
          orderBy("created_at", "asc"),
        );
        unsubscribe = onSnapshot(
          q,
          (snap: QuerySnapshot<DocumentData>) => {
            if (reqId !== reqIdRef.current) return;
            // Cada doc = un MessageItem (mismo shape snake_case). Indexar por id
            // conserva el merge incremental: las burbujas que no cambiaron
            // mantienen su referencia → React.memo evita re-render.
            const next: Record<string, MessageItem> = {};
            snap.forEach((d: QueryDocumentSnapshot<DocumentData>) => {
              next[d.id] = { ...(d.data() as MessageItem), id: d.id };
            });
            setMessages(next);
            setStatus("live");
          },
          () => {
            // permission-denied (asignación/token) o red → degradar al fallback.
            if (reqId !== reqIdRef.current) return;
            void fallback();
          },
        );
      } catch {
        // sign-in / init de Firebase falló → fallback server-side.
        if (reqId !== reqIdRef.current) return;
        await fallback();
      }
    })();

    return () => {
      unsubscribe?.(); // cleanup del listener anterior al cambiar de conversación
    };
  }, [conversationId, realtimeToken]);

  return { messages, status };
}
