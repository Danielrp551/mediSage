import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ padding: 32 }}>
      <h2>Página no encontrada</h2>
      <Link href="/dashboard">Volver al inicio</Link>
    </div>
  );
}
