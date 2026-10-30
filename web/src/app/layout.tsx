import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
export const metadata: Metadata = {
  title: "ASTRAL",
  description: "Human–AI interactive astronomy discovery",
};
export const viewport = { themeColor: "#1F2C7E" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
