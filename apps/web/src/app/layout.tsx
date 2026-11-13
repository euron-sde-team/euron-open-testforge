import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

import type { Metadata, Viewport } from "next";

import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  applicationName: "Euron Open TestForge",
  title: { default: "TestForge", template: "%s | TestForge" },
  description: "Euron Open TestForge: import your code, generate real tests with real assertions, run them in a sandbox with no network and no credentials, and read coverage and failures in plain language.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  // Meta tags cannot read CSS variables: these mirror --background in globals.css.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6f3" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0e0c" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
