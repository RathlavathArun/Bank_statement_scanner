import { z } from "zod";

// ─── Login ────────────────────────────────────────────────────────────────────
export const LoginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Please enter a valid email address"),
  password: z
    .string()
    .min(1, "Password is required"),
});

export type LoginFormValues = z.infer<typeof LoginSchema>;

// ─── Signup ───────────────────────────────────────────────────────────────────
export const SignupSchema = z.object({
  full_name: z
    .string()
    .min(2, "Full name must be at least 2 characters")
    .max(100, "Full name is too long"),
  firm_name: z
    .string()
    .min(2, "Firm name must be at least 2 characters")
    .max(100, "Firm name is too long"),
  email: z
    .string()
    .min(1, "Email is required")
    .email("Please enter a valid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Za-z]/, "Password must contain at least one letter")
    .regex(/[0-9]/, "Password must contain at least one number"),
});

export type SignupFormValues = z.infer<typeof SignupSchema>;

// ─── Forgot Password (Step 1) ─────────────────────────────────────────────────
export const ForgotPasswordSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Please enter a valid email address"),
});

export type ForgotPasswordFormValues = z.infer<typeof ForgotPasswordSchema>;

// ─── Reset Password (Step 2) ──────────────────────────────────────────────────
export const ResetPasswordSchema = z.object({
  email: z.string().email(),
  code: z.string().length(6, "OTP must be exactly 6 digits"),
  new_password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Za-z]/, "Password must contain at least one letter")
    .regex(/[0-9]/, "Password must contain at least one number"),
  confirm_password: z.string()
}).refine((data) => data.new_password === data.confirm_password, {
  message: "Passwords do not match",
  path: ["confirm_password"],
});

export type ResetPasswordFormValues = z.infer<typeof ResetPasswordSchema>;
