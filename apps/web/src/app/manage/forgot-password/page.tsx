"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { CheckCircle2 } from "lucide-react";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [step, setStep] = useState<"request" | "verify" | "success">("request");

  const handleSendOTP = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/v1/auth/password/forgot/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setStep("verify");
      } else {
        setError(data.detail || data.error || data.message || "Failed to send reset link");
      }
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyAndReset = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const formData = new FormData(e.currentTarget);
    const otp = formData.get("otp");
    const new_password = formData.get("new_password");

    try {
      const res = await fetch("/api/v1/auth/password/forgot/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp, new_password }),
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setStep("success");
      } else {
        setError(data.detail || data.error || data.message || "Failed to reset password");
      }
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden px-4">
      <Link href="/manage/login" aria-label="Go back to login" className="absolute top-6 left-6 text-sm font-medium text-slate-600 hover:text-slate-900 z-50">
        ? Back to Login
      </Link>
      
      {/* Decorative blurred shapes behind the card */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob"></div>
      <div className="absolute top-1/3 right-1/4 w-72 h-72 bg-purple-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000"></div>

      <Card className="w-full max-w-[420px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold tracking-tight text-center bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
            {step === "success" ? "Password Reset" : "Reset Password"}
          </CardTitle>
          <CardDescription className="text-center text-slate-500 dark:text-slate-400">
            {step === "request" && "Enter your email to receive a reset code"}
            {step === "verify" && "Enter the 6-digit code and your new password"}
            {step === "success" && "Your password has been successfully updated"}
          </CardDescription>
        </CardHeader>
        
        <CardContent>
          {error && (
            <div role="alert" className="p-3 mb-4 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
              {error}
            </div>
          )}

          {step === "request" && (
            <form key="request-form" onSubmit={handleSendOTP} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input 
                  id="email" 
                  name="email" 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="m@example.com" 
                  required 
                  className="glass-input h-11" 
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? "Sending..." : "Send Reset Code"}
              </Button>
            </form>
          )}

          {step === "verify" && (
            <form key="verify-form" onSubmit={handleVerifyAndReset} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="otp">Reset Code (OTP)</Label>
                <Input 
                  id="otp" 
                  name="otp" 
                  type="text" 
                  maxLength={10} 
                  required 
                  className="glass-input h-11 tracking-widest text-center text-lg font-mono" 
                  placeholder="123456" 
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new_password">New Password</Label>
                <Input 
                  id="new_password" 
                  name="new_password" 
                  type="password" 
                  required 
                  minLength={8}
                  className="glass-input h-11" 
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? "Resetting..." : "Reset Password"}
              </Button>
            </form>
          )}

          {step === "success" && (
            <div className="flex flex-col items-center justify-center space-y-4 py-4">
              <CheckCircle2 className="w-16 h-16 text-green-500" />
              <Link href="/manage/login" className="w-full">
                <Button className="w-full">Return to Login</Button>
              </Link>
            </div>
          )}
        </CardContent>
        
        {step !== "success" && (
          <CardFooter className="flex justify-center">
            <Link href="/manage/login" className="text-sm font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 hover:underline">
              Back to Sign In
            </Link>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
