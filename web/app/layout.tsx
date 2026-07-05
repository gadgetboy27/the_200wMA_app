import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "200-Week MA Scan",
  description: "Frontend for the intrinsic-value 200WMA stock scanner.",
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
