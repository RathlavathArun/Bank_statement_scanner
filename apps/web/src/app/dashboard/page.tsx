"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }

    const fetchUser = async () => {
      try {
        const res = await fetch("http://localhost:8000/v1/auth/me", {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        const data = await res.json();
        
        if (data.success) {
          setUser(data.data.user);
        } else {
          localStorage.removeItem("access_token");
          router.push("/login");
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-slate-50 dark:bg-slate-950">
      {/* Mesh background */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-blue-400/20 rounded-full mix-blend-multiply filter blur-[120px] opacity-70 animate-blob pointer-events-none"></div>
      <div className="absolute top-1/4 left-0 w-[600px] h-[600px] bg-purple-400/20 rounded-full mix-blend-multiply filter blur-[120px] opacity-70 animate-blob animation-delay-2000 pointer-events-none"></div>

      {/* Navbar */}
      <header className="sticky top-0 z-50 w-full glass border-b border-white/20 dark:border-slate-800/50">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white font-bold shadow-lg">
              B
            </div>
            <span className="font-semibold text-lg tracking-tight bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
              Bank Extract
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-slate-600 dark:text-slate-300">
              {user?.firm?.name || "My Firm"}
            </span>
            <Button variant="outline" onClick={handleLogout} className="glass-input h-9 text-sm">
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 relative z-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              Welcome back, {user?.full_name?.split(" ")[0] || "User"}
            </h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              Here's an overview of your firm's activity
            </p>
          </div>
          <Button className="bg-blue-600 hover:bg-blue-700 text-white shadow-md transition-all">
            + Upload Statement
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Total Clients</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">12</div>
              <p className="text-xs text-emerald-500 font-medium mt-1">+2 this month</p>
            </CardContent>
          </Card>
          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Statements Processed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">48</div>
              <p className="text-xs text-emerald-500 font-medium mt-1">+14 this week</p>
            </CardContent>
          </Card>
          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">Auto-Categorization Rate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">87%</div>
              <p className="text-xs text-blue-500 font-medium mt-1">Learning from your edits</p>
            </CardContent>
          </Card>
        </div>

        <h2 className="text-xl font-semibold mb-4 text-slate-800 dark:text-slate-200">Recent Statements</h2>
        
        <Card className="glass-card overflow-hidden">
          <div className="divide-y divide-white/20 dark:divide-slate-800/50">
            {/* Empty state for Phase 0 */}
            <div className="p-8 text-center">
              <div className="h-16 w-16 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-slate-900 dark:text-slate-100 mb-1">No statements yet</h3>
              <p className="text-slate-500 dark:text-slate-400 max-w-sm mx-auto mb-4">
                Upload your first bank statement (PDF or Excel) to get started with auto-extraction.
              </p>
              <Button variant="outline" className="glass-input">
                Upload Statement
              </Button>
            </div>
          </div>
        </Card>
      </main>
    </div>
  );
}
