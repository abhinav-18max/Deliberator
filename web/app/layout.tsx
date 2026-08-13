import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Delibrator",
  description: "Multi-model deliberation: one answer, and an honest record of how it won.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-5xl items-baseline justify-between px-6 py-4">
            <Link href="/" className="font-mono text-sm font-semibold tracking-wide">
              DELIBRATOR
            </Link>
            <nav className="flex gap-5 text-sm">
              <Link href="/" className="text-muted hover:text-ink">
                New deliberation
              </Link>
              <Link href="/runs" className="text-muted hover:text-ink">
                History
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
