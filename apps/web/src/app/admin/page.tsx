/**
 * Admin Dashboard
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { listBanks } from "@/lib/bank-service";
import { BarChart3, Plus, Settings } from "lucide-react";

export default function AdminDashboard() {
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
          activeBanks: banks.filter((bank) => bank.is_active).length,
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-950">
            Admin Dashboard
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            Manage bank templates, parser configuration, and cache operations.
          </p>
        </div>

        <Link href="/admin/banks/upload">
          <Button className="gap-2">
            <Plus size={16} />
            Upload Template
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <BarChart3 size={20} className="text-blue-500" />
              Total Banks
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-gray-500">Loading bank stats...</p>
            ) : (
              <>
                <p className="text-3xl font-bold">{stats.totalBanks}</p>
                <p className="mt-1 text-sm text-gray-500">
                  {stats.activeBanks} active
                </p>
              </>
            )}
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
            <p className="mb-4 text-sm text-gray-500">
              Review active banks and update statement parsing templates.
            </p>
            <Link href="/admin/banks" className="inline-block">
              <Button className="gap-2">
                <Settings size={16} />
                Manage Banks
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Link href="/admin/banks" className="block">
            <Button variant="outline" className="w-full justify-start gap-2">
              <BarChart3 size={18} />
              View All Banks
            </Button>
          </Link>

          <Link href="/admin/banks/upload" className="block">
            <Button className="w-full justify-start gap-2">
              <Plus size={18} />
              Upload New Bank Template
            </Button>
          </Link>

          <Link href="/admin/cache" className="block">
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