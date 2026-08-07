import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Subscription Agreement — Riseply",
  description: "Riseply's Subscription Agreement — billing, renewal, and cancellation terms for the Riseply Pro plan.",
  alternates: { canonical: "https://riseply.com/subscription-agreement" },
};

export default function SubscriptionAgreementPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Subscription Agreement</h1>
        <p className="muted">Last updated: August 2026</p>

        <p><em>
          This is a starting template, not a substitute for legal advice.
          If you're relying on this for a real product, have a lawyer
          review and adapt it to your situation and jurisdiction,
          including compliance with auto-renewal disclosure laws in the
          states and countries where you have subscribers.
        </em></p>

        <h2>Free plan</h2>
        <p>
          Every account starts on the free plan at no cost. The free plan
          includes limited monthly usage of job matching, resume
          tailoring, interview prep, and Job Buddy chat, capped at one
          active search profile. No payment method or agreement to this
          page is required to use the free plan.
        </p>

        <h2>Riseply Pro</h2>
        <p>
          Riseply Pro is a paid subscription billed at $9.99 per month.
          Pro increases your monthly limits, raises your active search
          profile cap to ten, and gives priority access to new features
          as they ship. Current pricing is always shown on the{" "}
          <Link href="/dashboard/billing">Billing</Link> page before you
          subscribe.
        </p>

        <h2>Billing and renewal</h2>
        <p>
          Subscribing to Pro starts a recurring monthly charge to the
          payment method on file, processed by Stripe. Your subscription
          renews automatically each month on the date you first
          subscribed, at the then-current price, until you cancel. We
          don't store your card details ourselves — Stripe handles
          payment processing and storage.
        </p>

        <h2>Cancellation</h2>
        <p>
          You can cancel anytime from the Billing page, which opens a
          Stripe-hosted billing portal. Cancellation stops future
          renewals but doesn't refund the current billing period — you
          keep Pro access through the end of the period you already paid
          for, then your account reverts to the free plan.
        </p>

        <h2>Refunds</h2>
        <p>
          Charges are generally non-refundable. If you believe you were
          charged in error, contact support and we'll look into it on a
          case-by-case basis.
        </p>

        <h2>Failed payments</h2>
        <p>
          If a renewal charge fails, Stripe will retry it automatically.
          If payment continues to fail, your account may be downgraded
          to the free plan until a valid payment method is added.
        </p>

        <h2>Price changes</h2>
        <p>
          We may change Pro pricing going forward. If we do, we'll notify
          active subscribers in advance, and any change will apply at
          your next renewal, not to the period you've already paid for.
        </p>

        <h2>Changes to this agreement</h2>
        <p>
          We may update this Subscription Agreement as the product
          changes. Continued use of Pro after an update means you accept
          the revised terms.
        </p>

        <p style={{ marginTop: 32 }}>
          See also our <Link href="/terms">Terms of Service</Link> and{" "}
          <Link href="/privacy">Privacy Policy</Link>.
        </p>
      </div>
    </div>
  );
}
