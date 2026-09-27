import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "../src/components/AppShell";
import "../src/styles.css";

export const metadata: Metadata = {
  title: "Smart Document Scanner",
  description: "Document detection, perspective correction, OCR, and structured extraction workbench.",
  icons: {
    icon: "/brand/logo.png",
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
