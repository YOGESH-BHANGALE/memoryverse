import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "MemoryVerse AI — Personal Knowledge Management",
  description:
    "AI-powered platform to upload documents, extract structured knowledge, and explore your professional journey through an interactive timeline.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-dark-900 text-white font-sans antialiased">
        <Navbar />
        <div className="flex pt-16">
          <Sidebar />
          <main className="flex-1 lg:ml-64 min-h-screen">
            <div className="max-w-5xl mx-auto px-6 py-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
