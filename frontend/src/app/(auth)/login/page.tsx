import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth/session";
import { LoginForm } from "./_components/LoginForm";

export const metadata = { title: "Iniciar sesión" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect?: string }>;
}) {
  if (await getAccessToken()) redirect("/dashboard");
  const { redirect: redirectTo } = await searchParams;
  return <LoginForm redirectTo={redirectTo ?? "/dashboard"} />;
}
