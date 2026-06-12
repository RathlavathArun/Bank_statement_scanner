/**
 * Cache Statistics Dashboard
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, Zap, Trash2, ArrowLeft } from "lucide-react";
import TemplateReloadButton from "@/components/TemplateReloadButton";

interface CacheStats {
  total_cached: number;
  hits: number;
  misses: number;
  reloads: number;
  errors: number;
  hit_rate: number;
  cached_banks: string[];
  last_loaded: Record<string, string>;
}

export default function CacheStatsPage() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const loadStats = async () => {
  useEffect(() => {
    loadStats();
  }, []);

  
    try {
      setLoading(true);
      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

      const response = await fetch("/api/admin/banks/cache/stats", {
        headers,
      });

      if (!response.ok) {
        throw new Error("Failed to load cache stats");
      }

      const data = await response.json();
      setStats(data.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error loading stats");
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = async () => {
    if (!confirm("Clear all cached templates?")) return;

    try {
      setClearing(true);
      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

      const response = await fetch("/api/admin/banks/cache/clear", {
        method: "DELETE",
        headers,
      });

      if (!response.ok) {
        throw new Error("Failed to clear cache");
      }

      // Reload stats
      await loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error clearing cache");
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-gray-200 rounded animate-pulse w-48"></div>
        <div className="grid gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 bg-gray-100 rounded animate-pulse"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-6">
        <Link href="/manage/banks">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft size={18} />
            Back to Banks
          </Button>
        </Link>
      </div>

      <h1 className="text-3xl font-bold">Template Cache Statistics</h1>

      {error && (
        <div className="flex gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-red-900">Error</p>
            <p className="text-sm text-red-800">{error}</p>
          </div>
        </div>
      )}

      {stats && (
        <div className="space-y-6">
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-500">
                  Cached Banks
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{stats.total_cached}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-500">
                  Cache Hits
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{stats.hits}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {stats.hit_rate}% hit rate
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-500">
                  Cache Misses
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{stats.misses}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-500">
                  Reload Count
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{stats.reloads}</p>
              </CardContent>
            </Card>
          </div>

          {/* Cached Banks List */}
          <Card>
            <CardHeader>
              <CardTitle>Cached Banks ({stats.cached_banks.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {stats.cached_banks.length > 0 ? (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {stats.cached_banks.map((bank) => (
                    <div
                      key={bank}
                      className="p-3 bg-blue-50 border border-blue-200 rounded-lg"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Zap size={14} className="text-blue-600" />
                        <span className="font-medium text-blue-900">
                          {bank.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-blue-700">
                        Loaded:{" "}
                        {stats.last_loaded[bank]
                          ? new Date(stats.last_loaded[bank]).toLocaleDateString(
                              "en-IN",
                              {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              }
                            )
                          : "N/A"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">No banks in cache</p>
              )}
            </CardContent>
          </Card>

          {/* Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Cache Management</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="font-medium mb-2">Reload Templates</h4>
                <p className="text-sm text-gray-600 mb-3">
                  Force reload templates from disk. Useful after manually updating
                  template files.
                </p>
                <TemplateReloadButton onSuccess={loadStats} />
              </div>

              <div className="border-t pt-4">
                <h4 className="font-medium mb-2">Clear Cache</h4>
                <p className="text-sm text-gray-600 mb-3">
                  Clear all cached templates. Templates will be reloaded from disk
                  on next access.
                </p>
                <Button
                  onClick={handleClearCache}
                  disabled={clearing}
                  variant="destructive"
                  className="gap-2"
                >
                  <Trash2 size={16} />
                  {clearing ? "Clearing..." : "Clear Cache"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Info */}
          <Card className="bg-blue-50 border-blue-200">
            <CardContent className="pt-6">
              <p className="text-sm text-blue-900">
                <strong>💡 Hot-reload enabled:</strong> Templates are automatically
                monitored for changes. Updates are loaded without restarting the API.
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
