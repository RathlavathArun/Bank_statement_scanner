/**
 * Admin Banks List Page
 */
"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import BanksList from "@/components/BanksList";
import { ArrowLeft } from "lucide-react";

export default function AdminBanksPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link href="/admin">
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft size={18} />
            Back to Admin
          </Button>
        </Link>
      </div>
      <BanksList />
    </div>
  );
}
