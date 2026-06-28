"use client";

import { Suspense, useState, useRef, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return email;
  if (local.length <= 1) return `${local}***@${domain}`;
  return `${local[0]}***@${domain}`;
}

import { readApiResponse } from "@/lib/utils";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "";

  const [otp, setOtp] = useState<string[]>(Array(6).fill(""));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleVerify = useCallback(
    async (code: string) => {
      if (loading || success) return;
      setLoading(true);
      setError("");

      try {
        const res = await fetch("/api/v1/auth/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, code }),
        });
        const data = await readApiResponse(res);

        if (res.ok && data.success) {
          if (data.data?.tokens?.access_token) {
            localStorage.setItem("access_token", data.data.tokens.access_token);
          }
          setSuccess(true);
          setTimeout(() => {
            router.push(data.data?.user?.mfa_required ? "/mfa?setup=1" : "/dashboard");
          }, 1500);
        } else {
          setError(data.detail || data.error || data.message || "Invalid or expired code.");
          setOtp(Array(6).fill(""));
          inputRefs.current[0]?.focus();
        }
      } catch {
        setError("An unexpected error occurred.");
      } finally {
        setLoading(false);
      }
    },
    [email, loading, success, router]
  );

  const handleChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);

    // Auto-advance to next input
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all digits filled
    const code = newOtp.join("");
    if (code.length === 6 && newOtp.every((d) => d !== "")) {
      handleVerify(code);
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      const newOtp = [...otp];
      newOtp[index - 1] = "";
      setOtp(newOtp);
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 0) return;

    const newOtp = [...otp];
    for (let i = 0; i < 6; i++) {
      newOtp[i] = pasted[i] || "";
    }
    setOtp(newOtp);

    // Focus on last filled or next empty
    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();

    if (pasted.length === 6) {
      handleVerify(pasted);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setError("");

    try {
      const res = await fetch("/api/v1/auth/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, purpose: "verify_email" }),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        setResendCooldown(60);
      } else {
        setError(data.detail || data.error || data.message || "Failed to resend code.");
      }
    } catch {
      setError("Failed to resend code.");
    }
  };

  if (!email) {
    return (
      <div className="flex items-center justify-center min-h-screen relative overflow-hidden px-4">
        <Card className="w-full max-w-[420px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
          <CardContent className="text-center py-8">
            <p className="text-slate-500 dark:text-slate-400 mb-4">No email address provided.</p>
            <Link href="/login" className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline">
              Back to login
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden px-4">
      <Link
        href="/login"
        className="absolute top-6 left-6 z-20 rounded-xl glass-input px-4 py-2 text-sm font-medium"
      >
        ← Back to Login
      </Link>

      {/* Decorative blurred shapes */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob"></div>
      <div className="absolute top-1/3 right-1/4 w-72 h-72 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000"></div>
      <div className="absolute -bottom-8 left-1/3 w-80 h-80 bg-violet-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-4000"></div>

      <Card className="w-full max-w-[440px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold tracking-tight text-center bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
            {success ? "Verified!" : "Verify your email"}
          </CardTitle>
          <CardDescription className="text-center text-slate-500 dark:text-slate-400">
            {success
              ? "Your email has been verified successfully."
              : `We sent a verification code to ${maskEmail(email)}`}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {success ? (
            <div className="flex flex-col items-center py-6 space-y-4">
              {/* Animated green checkmark */}
              <div className="relative">
                <div className="w-20 h-20 rounded-full bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center animate-[scale-in_0.3s_ease-out]">
                  <svg
                    className="w-10 h-10 text-emerald-600 dark:text-emerald-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                      className="animate-[draw-check_0.4s_ease-out_0.2s_both]"
                      style={{
                        strokeDasharray: 24,
                        strokeDashoffset: 24,
                        animation: "draw-check 0.4s ease-out 0.2s forwards",
                      }}
                    />
                  </svg>
                </div>
              </div>
              <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                Redirecting to dashboard...
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {error && (
                <div
                  role="alert"
                  aria-live="polite"
                  className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md"
                >
                  {error}
                </div>
              )}

              {/* OTP Input Boxes */}
              <div className="flex justify-center gap-3">
                {otp.map((digit, index) => (
                  <input
                    key={index}
                    ref={(el) => {
                      inputRefs.current[index] = el;
                    }}
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleChange(index, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(index, e)}
                    onPaste={index === 0 ? handlePaste : undefined}
                    disabled={loading || success}
                    className={`w-12 h-14 text-center text-2xl font-bold rounded-xl glass-input
                      border-2 border-white/50 dark:border-slate-700/50
                      focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30
                      transition-all duration-200
                      disabled:opacity-50 disabled:cursor-not-allowed
                      text-slate-800 dark:text-white
                      bg-white/40 dark:bg-slate-950/40 backdrop-blur-md`}
                    aria-label={`Digit ${index + 1}`}
                  />
                ))}
              </div>

              {/* Submit button (fallback if auto-submit doesn't trigger) */}
              <Button
                onClick={() => handleVerify(otp.join(""))}
                disabled={loading || otp.some((d) => d === "")}
                className="w-full h-11 bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-700 hover:to-emerald-700 text-white shadow-lg transition-all"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Verifying...
                  </span>
                ) : (
                  "Verify Email"
                )}
              </Button>

              {/* Resend Code */}
              <div className="text-center">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Didn&apos;t receive the code?{" "}
                  {resendCooldown > 0 ? (
                    <span className="font-medium text-slate-400 dark:text-slate-500">
                      Resend in {resendCooldown}s
                    </span>
                  ) : (
                    <button
                      onClick={handleResend}
                      className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline"
                    >
                      Resend Code
                    </button>
                  )}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Inline keyframe for the checkmark draw animation */}
      <style jsx global>{`
        @keyframes draw-check {
          to {
            stroke-dashoffset: 0;
          }
        }
        @keyframes scale-in {
          0% {
            transform: scale(0);
            opacity: 0;
          }
          100% {
            transform: scale(1);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
