import type { Metadata } from "next";
import { AuthProvider } from "@/features/auth/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tradvisor",
  description: "BRVM investment research workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className="bg-canvas font-sans text-ink antialiased"><AuthProvider>{children}</AuthProvider></body></html>;
}
