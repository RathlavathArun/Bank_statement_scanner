"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

import { readApiResponse } from "@/lib/utils";

function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return email;
  if (local.length <= 1) return `${local}***@${domain}`;
  return `${local[0]}***@${domain}`;
}

export default function ForgotPasswordPage() {
  const router = useRouter();

  // Step 1 = email, Step 2 = OTP + new password
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  // Step 2 state
  const [otp, setOtp] = useState<string[]>(Array(6).fill(""));
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

  // Step 1: Send reset code
  const handleSendCode = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        setStep(2);
        setResendCooldown(60);
        setTimeout(() => inputRefs.current[0]?.focus(), 100);
      } else {
        setError(data.detail || data.error || data.message || "Failed to send reset code.");
      }
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Reset password
  const handleResetPassword = useCallback(
    async (code?: string) => {
      const otpCode = code || otp.join("");
      if (otpCode.length !== 6) return;

      if (!newPassword) {
        setError("Please enter a new password.");
        return;
      }
      if (newPassword !== confirmPassword) {
        setError("Passwords do not match.");
        return;
      }
      if (newPassword.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }

      setLoading(true);
      setError("");

      try {
        const res = await fetch("/api/v1/auth/reset-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, code: otpCode, new_password: newPassword }),
        });
        const data = await readApiResponse(res);

        if (res.ok && data.success) {
          setSuccess(true);
          setTimeout(() => {
            router.push("/login");
          }, 2000);
        } else {
          setError(data.detail || data.error || data.message || "Failed to reset password.");
          setOtp(Array(6).fill(""));
          inputRefs.current[0]?.focus();
        }
      } catch {
        setError("An unexpected error occurred.");
      } finally {
        setLoading(false);
      }
    },
    [otp, email, newPassword, confirmPassword, router]
  );

  const handleOtpChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      const newOtp = [...otp];
      newOtp[index - 1] = "";
      setOtp(newOtp);
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 0) return;

    const newOtp = [...otp];
    for (let i = 0; i < 6; i++) {
      newOtp[i] = pasted[i] || "";
    }
    setOtp(newOtp);

    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setError("");

    try {
      const res = await fetch("/api/v1/auth/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, purpose: "reset_password" }),
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

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden px-4">
      <Link
        href="/login"
        className="absolute top-6 left-6 z-20 rounded-xl glass-input px-4 py-2 text-sm font-medium"
      >
        ← Back to Login
      </Link>

      {/* Decorative blurred shapes */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-amber-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob"></div>
      <div className="absolute top-1/3 right-1/4 w-72 h-72 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000"></div>
      <div className="absolute -bottom-8 left-1/3 w-80 h-80 bg-rose-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-4000"></div>

      <Card className="w-full max-w-[440px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold tracking-tight text-center bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
            {success
              ? "Password Reset!"
              : step === 1
                ? "Forgot password?"
                : "Reset your password"}
          </CardTitle>
          <CardDescription className="text-center text-slate-500 dark:text-slate-400">
            {success
              ? "Your password has been reset successfully."
              : step === 1
                ? "Enter your email and we'll send you a reset code"
                : `Enter the code sent to ${maskEmail(email)}`}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {success ? (
            <div className="flex flex-col items-center py-6 space-y-4">
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
                    style={{
                      strokeDasharray: 24,
                      strokeDashoffset: 24,
                      animation: "draw-check 0.4s ease-out 0.2s forwards",
                    }}
                  />
                </svg>
              </div>
              <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                Redirecting to login...
              </p>
            </div>
          ) : step === 1 ? (
            <form onSubmit={handleSendCode} className="space-y-4">
              {error && (
                <div
                  role="alert"
                  aria-live="polite"
                  className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md"
                >
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email" className="text-slate-700 dark:text-slate-300">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="m@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="glass-input h-11"
                />
              </div>

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 text-white shadow-lg transition-all"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Sending...
                  </span>
                ) : (
                  "Send Reset Code"
                )}
              </Button>
            </form>
          ) : (
            <div className="space-y-5">
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
                    onChange={(e) => handleOtpChange(index, e.target.value)}
                    onKeyDown={(e) => handleOtpKeyDown(index, e)}
                    onPaste={index === 0 ? handleOtpPaste : undefined}
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

              {/* New Password */}
              <div className="space-y-2">
                <Label htmlFor="new-password" className="text-slate-700 dark:text-slate-300">New Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  placeholder="Minimum 8 characters"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="glass-input h-11"
                />
              </div>

              {/* Confirm Password */}
              <div className="space-y-2">
                <Label htmlFor="confirm-password" className="text-slate-700 dark:text-slate-300">Confirm Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  placeholder="Re-enter your password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="glass-input h-11"
                />
                {confirmPassword && newPassword !== confirmPassword && (
                  <p className="text-xs text-red-500 mt-1">Passwords do not match</p>
                )}
              </div>

              {/* Reset Button */}
              <Button
                onClick={() => handleResetPassword()}
                disabled={loading || otp.some((d) => d === "") || !newPassword || newPassword !== confirmPassword}
                className="w-full h-11 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 text-white shadow-lg transition-all"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Resetting...
                  </span>
                ) : (
                  "Reset Password"
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

        <CardFooter className="flex flex-col space-y-4">
          <div className="text-sm text-center text-slate-500 dark:text-slate-400 w-full">
            Remember your password?{" "}
            <Link href="/login" className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline">
              Sign in
            </Link>
          </div>
        </CardFooter>
      </Card>

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
