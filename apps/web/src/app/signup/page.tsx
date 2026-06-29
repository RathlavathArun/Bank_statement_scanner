"use client";

import { useState } from "react";
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
import { SignupSchema, type SignupFormValues } from "@/lib/schemas";

/** Inline field error */
function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="text-xs text-red-500 mt-1">
      {message}
    </p>
  );
}

export default function SignupPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(SignupSchema),
    mode: "onTouched",
  });

  const onSubmit = async (values: SignupFormValues) => {
    setServerError("");
    try {
      const res = await fetch("/api/v1/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await readApiResponse(res);

      if (res.ok && data.success) {
        localStorage.setItem("access_token", data.data.tokens.access_token);
        router.push(`/verify-email?email=${encodeURIComponent(values.email)}`);
      } else {
        setServerError(data.detail || data.error || data.message || "Signup failed");
      }
    } catch {
      setServerError("An unexpected error occurred.");
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden">
      {/* Decorative blurred shapes */}
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob" />
      <div className="absolute bottom-1/4 left-1/4 w-72 h-72 bg-emerald-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000" />

      <Card className="w-[450px] glass-card border-white/40 shadow-2xl relative z-10 p-2">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold tracking-tight text-center bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
            Create an account
          </CardTitle>
          <CardDescription className="text-center text-slate-500 dark:text-slate-400">
            Enter your details to create your firm workspace
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
            {/* Server-level error banner */}
            {serverError && (
              <div
                role="alert"
                className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md"
              >
                {serverError}
              </div>
            )}

            {/* Full Name + Firm Name */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="full_name" className="text-slate-700 dark:text-slate-300">
                  Full Name
                </Label>
                <Input
                  id="full_name"
                  placeholder="John Doe"
                  autoComplete="name"
                  aria-invalid={!!errors.full_name}
                  aria-describedby={errors.full_name ? "full-name-error" : undefined}
                  className={`glass-input h-10 ${errors.full_name ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                  {...register("full_name")}
                />
                <FieldError id="full-name-error" message={errors.full_name?.message} />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="firm_name" className="text-slate-700 dark:text-slate-300">
                  Firm Name
                </Label>
                <Input
                  id="firm_name"
                  placeholder="Acme Associates"
                  autoComplete="organization"
                  aria-invalid={!!errors.firm_name}
                  aria-describedby={errors.firm_name ? "firm-name-error" : undefined}
                  className={`glass-input h-10 ${errors.firm_name ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                  {...register("firm_name")}
                />
                <FieldError id="firm-name-error" message={errors.firm_name?.message} />
              </div>
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-slate-700 dark:text-slate-300">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="m@example.com"
                autoComplete="email"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-error" : undefined}
                className={`glass-input h-10 ${errors.email ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                {...register("email")}
              />
              <FieldError id="email-error" message={errors.email?.message} />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-slate-700 dark:text-slate-300">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="Min 8 chars with a letter and number"
                autoComplete="new-password"
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
                className={`glass-input h-10 ${errors.password ? "border-red-500 focus-visible:ring-red-500/30" : ""}`}
                {...register("password")}
              />
              <FieldError id="password-error" message={errors.password?.message} />
            </div>

            <Button
              className="w-full h-11 bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-700 hover:to-emerald-700 text-white shadow-lg transition-all mt-4"
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating account...
                </span>
              ) : (
                "Sign up"
              )}
            </Button>
          </form>
        </CardContent>

        <CardFooter className="flex flex-col space-y-4">
          <div className="text-sm text-center text-slate-500 dark:text-slate-400 w-full">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline"
            >
              Sign in
            </Link>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
