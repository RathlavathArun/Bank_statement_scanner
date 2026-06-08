/**
 * Admin Dashboard
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { listBanks } from "@/lib/bank-service";
import { BarChart3, Settings, Plus } from "lucide-react";

export default function AdminDashboard() {
  const router = useRouter();
  const [stats, setStats] = useState({
    totalBanks: 0,
    activeBanks: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const banks = await listBanks();
        setStats({
          totalBanks: banks.length,
          activeBanks: banks.filter((b) => b.is_active).length,
        });
      } catch (error) {
        console.error("Error loading stats:", error);
      } finally {
        setLoading(false);
      }
    };

    loadStats();
  }, []);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Admin Dashboard</h1>
        <Link href="/">
          <Button variant="outline">Back to Dashboard</Button>
        </Link>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <BarChart3 size={20} className="text-blue-500" />
              Total Banks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{stats.totalBanks}</p>
            <p className="text-sm text-gray-500 mt-1">
              {stats.activeBanks} active
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Settings size={20} className="text-green-500" />
              Configuration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Link href="/admin/banks" className="inline-block">
              <Button className="gap-2">
                <Settings size={16} />
                Manage Banks
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Link href="/admin/banks">
            <Button variant="outline" className="w-full justify-start gap-2">
              <BarChart3 size={18} />
              View All Banks
            </Button>
          </Link>
          <Link href="/admin/banks/upload">
            <Button className="w-full justify-start gap-2">
              <Plus size={18} />
              Upload New Bank Template
            </Button>
          </Link>
          <Link href="/admin/cache">
            <Button variant="outline" className="w-full justify-start gap-2">
              <BarChart3 size={18} />
              Cache Statistics
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
