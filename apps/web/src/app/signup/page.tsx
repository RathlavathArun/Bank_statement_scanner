"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function SignupPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const formData = new FormData(e.currentTarget);
    const email = formData.get("email");
    const password = formData.get("password");
    const full_name = formData.get("full_name");
    const firm_name = formData.get("firm_name");

    try {
      const res = await fetch("http://localhost:8000/v1/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name, firm_name }),
      });
      const data = await res.json();

      if (data.success) {
        localStorage.setItem("access_token", data.data.tokens.access_token);
        router.push("/dashboard");
      } else {
        setError(data.error || "Signup failed");
      }
    } catch (error) {
      console.error(error);
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen relative overflow-hidden">
      {/* Decorative blurred shapes behind the card */}
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob"></div>
      <div className="absolute bottom-1/4 left-1/4 w-72 h-72 bg-emerald-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000"></div>

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
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
                {error}
              </div>
            )}
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="full_name" className="text-slate-700 dark:text-slate-300">Full Name</Label>
                <Input 
                  id="full_name" 
                  name="full_name" 
                  placeholder="John Doe" 
                  required 
                  className="glass-input h-10"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="firm_name" className="text-slate-700 dark:text-slate-300">Firm Name</Label>
                <Input 
                  id="firm_name" 
                  name="firm_name" 
                  placeholder="Acme Associates" 
                  required 
                  className="glass-input h-10"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email" className="text-slate-700 dark:text-slate-300">Email</Label>
              <Input 
                id="email" 
                name="email" 
                type="email" 
                placeholder="m@example.com" 
                required 
                className="glass-input h-10"
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-700 dark:text-slate-300">Password</Label>
              <Input 
                id="password" 
                name="password" 
                type="password" 
                placeholder="Minimum 8 characters"
                required 
                className="glass-input h-10"
              />
            </div>
            
            <Button 
              className="w-full h-11 bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-700 hover:to-emerald-700 text-white shadow-lg transition-all mt-4" 
              type="submit" 
              disabled={loading}
            >
              {loading ? "Creating account..." : "Sign up"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <div className="text-sm text-center text-slate-500 dark:text-slate-400 w-full">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 underline-offset-4 hover:underline">
              Sign in
            </Link>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
