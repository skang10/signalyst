import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Signalyst",
  description: "Energy market regime detection powered by TabPFN",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try {
              var t = localStorage.getItem("signalyst-theme");
              if (t === "gold") document.documentElement.setAttribute("data-theme", "gold");
            } catch (e) {}`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
