"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { readApiResponse } from "@/lib/utils";

function MfaForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setupRequired = searchParams.get("setup") === "1";
  const [qrCode, setQrCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!setupRequired) return;
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    fetch("/api/v1/auth/totp/setup", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => ({ response, body: await readApiResponse(response) }))
      .then(({ response, body }) => {
        if (!response.ok || !body.success) throw new Error(body.detail || body.message || "MFA setup failed");
        setQrCode(body.data.qr_code);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "MFA setup failed"));
  }, [router, setupRequired]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const token = localStorage.getItem("access_token");
    const code = new FormData(event.currentTarget).get("code");
    const endpoint = setupRequired ? "/api/v1/auth/totp/confirm" : "/api/v1/auth/totp/validate";
    const payload = setupRequired ? { code } : { code, access_token: token };
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(setupRequired && token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      const body = await readApiResponse(response);
      if (!response.ok || !body.success) throw new Error(body.detail?.message || body.detail || body.message || "Invalid code");
      localStorage.setItem("access_token", body.data.access_token);
      router.replace("/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "MFA verification failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{setupRequired ? "Set up authenticator MFA" : "Authenticator verification"}</CardTitle>
          <CardDescription>
            {setupRequired ? "Scan this QR code, then enter the six-digit code." : "Enter the current six-digit code from your authenticator app."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {qrCode && (
            <Image
              src={qrCode}
              alt="Authenticator setup QR code"
              width={224}
              height={224}
              unoptimized
              className="mx-auto mb-6"
            />
          )}
          {error && <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>}
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="code">Six-digit code</Label>
              <Input id="code" name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required autoComplete="one-time-code" />
            </div>
            <Button className="w-full" disabled={loading || (setupRequired && !qrCode)}>
              {loading ? "Verifying…" : "Verify"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

export default function MfaPage() {
  return (
    <Suspense fallback={<main className="flex min-h-screen items-center justify-center">Loading…</main>}>
      <MfaForm />
    </Suspense>
  );
}
