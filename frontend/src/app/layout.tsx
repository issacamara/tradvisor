import type { Metadata } from "next";
import { AuthProvider } from "@/features/auth/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tradvisor",
  description: "BRVM research and paper trading workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>;
}
