import type { Metadata, Viewport } from "next";
import "./globals.css";

const ICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ff7a1a' stroke-width='2.2' stroke-linecap='round'%3E%3Cpath d='M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2'/%3E%3Ccircle cx='12' cy='9' r='2.4'/%3E%3Cpath d='M8 17c.6-2.6 2.1-4 4-4s3.4 1.4 4 4'/%3E%3C/svg%3E";

export const metadata: Metadata = { title: "Victim Detection · Station", icons: { icon: ICON } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0b0f14" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
