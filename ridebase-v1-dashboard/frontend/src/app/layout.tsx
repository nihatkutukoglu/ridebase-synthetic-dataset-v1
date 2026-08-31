import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RideBase V1 Intelligence",
  description:
    "Next-service days & km prediction dashboard for RideBase V1 regression on Synthetic Dataset v1.3.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
