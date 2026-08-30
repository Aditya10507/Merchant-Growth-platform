/**
 * AuthPage.tsx
 * ------------
 * Signup and login, toggled within one screen (per the decision to
 * skip a separate forgot-password flow and keep auth minimal for MVP).
 */

import { useCallback, useState, type FormEvent } from "react";

import { ApiError } from "../api";
import { useAuth } from "../AuthContext";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { PASSWORD_MIN_LENGTH } from "../constants";

type Mode = "login" | "signup";

interface FormErrors {
  businessName?: string;
  email?: string;
  password?: string;
}

function validate(mode: Mode, businessName: string, email: string, password: string): FormErrors {
  const errors: FormErrors = {};

  if (mode === "signup" && businessName.trim().length < 2) {
    errors.businessName = "Business name must be at least 2 characters.";
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = "Enter a valid email address.";
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    errors.password = `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`;
  } else if (mode === "signup" && !(/[A-Za-z]/.test(password) && /\d/.test(password))) {
    errors.password = "Password must contain at least one letter and one digit.";
  }

  return errors;
}

export function AuthPage() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [businessName, setBusinessName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setSubmitError(null);

      const errors = validate(mode, businessName, email, password);
      setFieldErrors(errors);
      if (Object.keys(errors).length > 0) return;

      setIsSubmitting(true);
      try {
        if (mode === "signup") {
          await signup(businessName.trim(), email.trim(), password);
        } else {
          await login(email.trim(), password);
        }
      } catch (error) {
        setSubmitError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [mode, businessName, email, password, signup, login]
  );

  return (
    <div className="flex min-h-screen items-center justify-center bg-white px-4">
      <div className="w-full max-w-md rounded-md border border-gray-200 bg-white p-8">
        <h1 className="mb-1 text-xl font-semibold text-gray-900">Merchant onboarding copilot</h1>
        <p className="mb-6 text-sm text-gray-500">
          {mode === "login" ? "Log in to continue your onboarding." : "Create an account to get started."}
        </p>

        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          {mode === "signup" && (
            <InputField
              label="Business name"
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              error={fieldErrors.businessName}
              autoComplete="organization"
            />
          )}
          <InputField
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={fieldErrors.email}
            autoComplete="email"
          />
          <InputField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={fieldErrors.password}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
          />

          {submitError && <Alert variant="error">{submitError}</Alert>}

          <Button type="submit" isLoading={isSubmitting}>
            {mode === "login" ? "Log in" : "Sign up"}
          </Button>
        </form>

        <button
          type="button"
          className="mt-4 text-sm text-gray-700 underline-offset-2 hover:text-gray-900 hover:underline"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setFieldErrors({});
            setSubmitError(null);
          }}
        >
          {mode === "login" ? "Need an account? Sign up" : "Already have an account? Log in"}
        </button>

        {/* Demo accounts for quick access to different roles */}
        {mode === "login" && (
          <div className="mt-5 rounded-md border border-gray-200 bg-gray-50 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              Demo Accounts
            </p>
            <div className="flex flex-col gap-2 text-xs text-gray-600">
              <button
                type="button"
                onClick={() => { setEmail("reviewer@example.com"); setPassword("ReviewerPass123"); }}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-left transition-colors duration-150 hover:bg-gray-50"
              >
                <span className="font-medium text-gray-900">Reviewer</span>
                <span className="ml-2 text-gray-400">reviewer@example.com</span>
              </button>
              <button
                type="button"
                onClick={() => { setEmail("admin@example.com"); setPassword("AdminPass123"); }}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-left transition-colors duration-150 hover:bg-gray-50"
              >
                <span className="font-medium text-gray-900">Admin</span>
                <span className="ml-2 text-gray-400">admin@example.com</span>
              </button>
              <button
                type="button"
                onClick={() => { setEmail("speed@test.com"); setPassword("TestPass123"); }}
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-left transition-colors duration-150 hover:bg-gray-50"
              >
                <span className="font-medium text-gray-900">Merchant</span>
                <span className="ml-2 text-gray-400">speed@test.com</span>
              </button>
            </div>
            <p className="mt-2 text-[10px] text-gray-400">Click to auto-fill credentials, then press Log in.</p>
          </div>
        )}
      </div>
    </div>
  );
}
