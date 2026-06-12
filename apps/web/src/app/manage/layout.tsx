/**
 * Admin Layout
 */
"use client";

import Link from "next/link";
import { ReactNode, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Skip verification check on the login and forgot password pages
    if (pathname?.includes('/manage/login') || pathname?.includes('/manage/forgot-password')) {
      return;
    }

    const isVerified = localStorage.getItem("admin_verified");
    if (isVerified !== "true") {
      router.push("/manage/login");
    }
  }, [router, pathname]);
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              Bank Statement Admin
            </h1>
            <div className="flex items-center gap-4">
  <Link
    href="/"
    className="text-gray-600 hover:text-gray-900 text-sm"
  >
    ← Back to App
  </Link>

  <Link
    href="/dashboard"
    className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
  >
    Dashboard
  </Link>
</div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-gray-600">
          <p>Bank Statement Extraction Admin Panel</p>
        </div>
      </footer>
    </div>
  );
}
