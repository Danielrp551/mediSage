import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ padding: 32 }}>
      <h2>Page not found</h2>
      <Link href="/dashboard">Back to dashboard</Link>
    </div>
  );
}
