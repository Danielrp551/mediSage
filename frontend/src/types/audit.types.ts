/**
 * Audit info — backend resolves `created_by` / `updated_by` UUIDs to a
 * compact user shape so the UI can show a name instead of an opaque ID.
 *
 * Null when the actor user has been hard-deleted from the DB (the audit
 * column still holds the UUID for trail purposes, but there's no user
 * row to resolve against). Render `"—"` or similar in that case.
 */
export interface UserAuditInfo {
  id: string;
  full_name: string;
  email: string;
}

// Marca explícita de módulo (type-only file under isolatedModules).
export {};
