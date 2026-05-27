import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth/session";

export default async function RootPage() {
  redirect((await getAccessToken()) ? "/dashboard" : "/login");
}
