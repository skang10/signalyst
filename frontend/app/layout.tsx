import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TemporalAgent",
  description: "Energy market regime detection powered by TabPFN",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
