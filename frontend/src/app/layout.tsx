import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Studio Ops",
  description: "Game-dev studio visualizer for Claude Code sessions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
