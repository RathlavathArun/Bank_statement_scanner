"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import {
  Card, CardContent, CardDescription, CardFooter,
  CardHeader, CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

import { readApiResponse } from "@/lib/utils";
import {
  ForgotPasswordSchema, type ForgotPasswordFormValues,
  ResetPasswordSchema, type ResetPasswordFormValues
} from "@/lib/schemas";

function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return email;
  if (local.length <= 1) return `${local}***@${domain}`;
  return `${local[0]}***@${domain}`;
}

/** Inline field error */
function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="text-xs text-red-500 mt-1">
      {message}
    </p>
  );
}

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [serverError, setServerError] = useState("");
  const [success, setSuccess] = useState(false);

  // Email state is lifted because step 2 needs it
  const [confirmedEmail, setConfirmedEmail] = useState("");

  // OTP state (for the 6 boxes)
  const [otp, setOtp] = useState<string[]>(Array(6).fill(""));
  const [resendCooldown, setResendCooldown] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Form 1: Email Request
  const step1Form = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(ForgotPasswordSchema),
    mode: "onTouched",
  });

  // Form 2: Reset Password
  const step2Form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(ResetPasswordSchema),
    mode: "onTouched",
  });

  // Cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  // Handle Step 1 Submit
  const onStep1Submit = async (values: ForgotPasswordFormValues) => {
    setServerError("");
    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        setConfirmedEmail(values.email);
        step2Form.setValue("email", values.email);
        setStep(2);
        setResendCooldown(60);
        setTimeout(() => inputRefs.current[0]?.focus(), 100);
      } else {
        setServerError(data.detail || data.error || data.message || "Failed to send reset code.");
      }
    } catch {
      setServerError("An unexpected error occurred.");
    }
  };

  // Handle Step 2 Submit
  const onStep2Submit = async (values: ResetPasswordFormValues) => {
    setServerError("");
    try {
      const res = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: values.email,
          code: values.code,
          new_password: values.new_password,
        }),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        setSuccess(true);
      } else {
        setServerError(data.detail || data.error || data.message || "Failed to reset password.");
      }
    } catch {
      setServerError("An unexpected error occurred.");
    }
  };

  // Keep OTP state in sync with React Hook Form
  const handleOtpChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);
    step2Form.setValue("code", newOtp.join(""), { shouldValidate: true });

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpPaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData("text/plain").replace(/\D/g, "").slice(0, 6);
    if (pastedData) {
      const newOtp = [...otp];
      for (let i = 0; i < pastedData.length; i++) {
        newOtp[i] = pastedData[i];
      }
      setOtp(newOtp);
      step2Form.setValue("code", newOtp.join(""), { shouldValidate: true });
      const nextEmpty = newOtp.findIndex((v) => !v);
      const focusIndex = nextEmpty === -1 ? 5 : nextEmpty;
      inputRefs.current[focusIndex]?.focus();
    }
  };

  // Resend code logic
  const handleResendCode = async () => {
    if (resendCooldown > 0) return;
    setServerError("");
    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: confirmedEmail }),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        setResendCooldown(60);
      } else {
        setServerError(data.detail || data.error || data.message || "Failed to resend code.");
      }
    } catch {
      setServerError("An unexpected error occurred.");
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob" />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-purple-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000" />

      <Card className="w-[420px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold tracking-tight text-center bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
            {success ? "Password Reset" : step === 1 ? "Reset Password" : "Check Your Email"}
          </CardTitle>
          <CardDescription className="text-center text-slate-500 dark:text-slate-400">
            {success
              ? "Your password has been changed successfully"
              : step === 1
              ? "Enter your email to receive a reset code"
              : `We sent a 6-digit code to ${maskEmail(confirmedEmail)}`}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {success ? (
            <div className="flex flex-col items-center py-4 space-y-4">
              <div className="h-16 w-16 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mb-2">
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <Link href="/login" className="w-full">
                <Button className="w-full h-11 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 text-white shadow-lg transition-all">
                  Back to Sign In
                </Button>
              </Link>
            </div>
          ) : step === 1 ? (
            <form onSubmit={step1Form.handleSubmit(onStep1Submit)} noValidate className="space-y-4">
              {serverError && (
                <div role="alert" className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
                  {serverError}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-slate-700 dark:text-slate-300">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  autoComplete="email"
                  aria-invalid={!!step1Form.formState.errors.email}
                  className={`glass-input h-11 ${step1Form.formState.errors.email ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                  {...step1Form.register("email")}
                />
                <FieldError id="email-error" message={step1Form.formState.errors.email?.message} />
              </div>

              <Button
                type="submit"
                className="w-full h-11 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 text-white shadow-lg transition-all mt-4"
                disabled={step1Form.formState.isSubmitting}
              >
                {step1Form.formState.isSubmitting ? "Sending..." : "Send Reset Code"}
              </Button>
            </form>
          ) : (
            <form onSubmit={step2Form.handleSubmit(onStep2Submit)} noValidate className="space-y-4">
              {serverError && (
                <div role="alert" className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
                  {serverError}
                </div>
              )}

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <Label className="text-slate-700 dark:text-slate-300">Verification Code</Label>
                  <button
                    type="button"
                    onClick={handleResendCode}
                    disabled={resendCooldown > 0}
                    className="text-xs font-medium text-blue-600 hover:text-blue-500 disabled:opacity-50 disabled:hover:text-blue-600 transition-colors"
                  >
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend Code"}
                  </button>
                </div>
                
                <div className="flex justify-between gap-2" onPaste={handleOtpPaste}>
                  {otp.map((digit, index) => (
                    <Input
                      key={index}
                      ref={(el) => { inputRefs.current[index] = el; }}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleOtpChange(index, e.target.value)}
                      onKeyDown={(e) => handleOtpKeyDown(index, e)}
                      className="w-12 h-12 text-center text-xl font-bold glass-input border-slate-300 dark:border-slate-700 focus:border-blue-500 focus:ring-blue-500/20 transition-all shadow-sm rounded-lg"
                    />
                  ))}
                </div>
                <FieldError id="code-error" message={step2Form.formState.errors.code?.message} />
              </div>

              <div className="space-y-1.5 mt-4">
                <Label htmlFor="new_password" className="text-slate-700 dark:text-slate-300">New Password</Label>
                <Input
                  id="new_password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={!!step2Form.formState.errors.new_password}
                  className={`glass-input h-11 ${step2Form.formState.errors.new_password ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                  {...step2Form.register("new_password")}
                />
                <FieldError id="new_password-error" message={step2Form.formState.errors.new_password?.message} />
              </div>

              <div className="space-y-1.5 mt-2">
                <Label htmlFor="confirm_password" className="text-slate-700 dark:text-slate-300">Confirm Password</Label>
                <Input
                  id="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={!!step2Form.formState.errors.confirm_password}
                  className={`glass-input h-11 ${step2Form.formState.errors.confirm_password ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                  {...step2Form.register("confirm_password")}
                />
                <FieldError id="confirm_password-error" message={step2Form.formState.errors.confirm_password?.message} />
              </div>

              <Button
                type="submit"
                className="w-full h-11 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 text-white shadow-lg transition-all mt-6"
                disabled={step2Form.formState.isSubmitting}
              >
                {step2Form.formState.isSubmitting ? "Resetting..." : "Reset Password"}
              </Button>
            </form>
          )}
        </CardContent>

        {!success && (
          <CardFooter className="flex flex-col space-y-4 pb-6">
            <div className="text-sm text-center text-slate-500 dark:text-slate-400 w-full">
              Remember your password?{" "}
              <Link href="/login" className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline">
                Sign in
              </Link>
            </div>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
