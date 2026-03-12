"use client";

/**
 * Account / Payment Settings page.
 *
 * Dependencies to add to package.json:
 *   @stripe/stripe-js
 *   @stripe/react-stripe-js
 *
 * npm install @stripe/stripe-js @stripe/react-stripe-js
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeftIcon, CreditCardIcon, PlusIcon, TrashIcon, Loader2Icon } from "lucide-react";
import { createSetupIntent, listPaymentMethods } from "@/lib/api";

interface PaymentMethod {
  id: string;
  brand: string;
  last4: string;
  exp_month: number;
  exp_year: number;
}

/**
 * Stripe card save form component.
 *
 * NOTE: This requires @stripe/stripe-js and @stripe/react-stripe-js.
 * Replace the placeholder below with actual Stripe Elements integration
 * once those packages are installed.
 *
 * Example real implementation:
 *   import { loadStripe } from "@stripe/stripe-js";
 *   import { Elements, CardElement, useStripe, useElements } from "@stripe/react-stripe-js";
 *
 *   const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!);
 *
 *   function CardForm({ clientSecret, onSuccess }) {
 *     const stripe = useStripe();
 *     const elements = useElements();
 *     const handleSubmit = async () => {
 *       const { setupIntent } = await stripe.confirmCardSetup(clientSecret, {
 *         payment_method: { card: elements.getElement(CardElement) }
 *       });
 *       if (setupIntent?.status === "succeeded") onSuccess();
 *     };
 *     return <CardElement />;
 *   }
 */
function AddCardPlaceholder({ onSuccess }: { onSuccess: () => void }) {
  const [loading, setLoading] = useState(false);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const initSetupIntent = async () => {
    setLoading(true);
    setError(null);
    try {
      const { client_secret } = await createSetupIntent();
      setClientSecret(client_secret);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to initialize card setup");
    } finally {
      setLoading(false);
    }
  };

  if (!clientSecret) {
    return (
      <div>
        {error && (
          <p className="text-sm text-red-600 mb-2">{error}</p>
        )}
        <button
          onClick={initSetupIntent}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-700 border border-primary-300 rounded-xl hover:bg-primary-50 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2Icon className="w-4 h-4 animate-spin" /> : <PlusIcon className="w-4 h-4" />}
          Add Card
        </button>
      </div>
    );
  }

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <p className="text-sm text-slate-600 mb-3">
        Enter your card details below. Your card will be saved securely via Stripe.
      </p>
      {/* Stripe Elements CardElement mounts here */}
      <div className="bg-white border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-400 italic">
        [Stripe Card Element — install @stripe/react-stripe-js to enable]
      </div>
      <p className="text-xs text-slate-400 mt-2">
        Client secret: <code className="bg-slate-100 px-1 rounded">{clientSecret.slice(0, 20)}…</code>
      </p>
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => {
            // Placeholder — call stripe.confirmCardSetup(clientSecret, ...) here
            alert("Stripe Elements integration required. See comment in source code.");
          }}
          className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-xl hover:bg-primary-700"
        >
          Save Card
        </button>
        <button
          onClick={() => setClientSecret(null)}
          className="px-4 py-2 text-sm text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function AccountPage() {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loadingMethods, setLoadingMethods] = useState(true);
  const [showAddCard, setShowAddCard] = useState(false);

  const fetchMethods = async () => {
    setLoadingMethods(true);
    try {
      const methods = await listPaymentMethods();
      setPaymentMethods(methods as PaymentMethod[]);
    } catch {
      // Non-fatal — user may not have Stripe configured
    } finally {
      setLoadingMethods(false);
    }
  };

  useEffect(() => {
    fetchMethods();
  }, []);

  const handleCardAdded = () => {
    setShowAddCard(false);
    fetchMethods();
  };

  return (
    <div className="min-h-screen bg-surface">
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200">
        <Link
          href="/"
          className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <ArrowLeftIcon className="w-4 h-4" />
        </Link>
        <h1 className="font-semibold text-slate-800">Account Settings</h1>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
        {/* Payment Methods */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold text-slate-800">Payment Methods</h2>
              <p className="text-sm text-slate-500 mt-0.5">
                Saved cards are used for in-app hotel bookings.
              </p>
            </div>
            {!showAddCard && (
              <button
                onClick={() => setShowAddCard(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-primary-700 border border-primary-200 rounded-xl hover:bg-primary-50 transition-colors"
              >
                <PlusIcon className="w-3.5 h-3.5" />
                Add card
              </button>
            )}
          </div>

          {loadingMethods ? (
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <Loader2Icon className="w-4 h-4 animate-spin" />
              Loading saved cards…
            </div>
          ) : (
            <div className="space-y-2">
              {paymentMethods.map((pm) => (
                <div
                  key={pm.id}
                  className="flex items-center gap-3 px-4 py-3 bg-white rounded-xl border border-slate-200"
                >
                  <CreditCardIcon className="w-5 h-5 text-slate-400 shrink-0" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-slate-800 capitalize">
                      {pm.brand} ending in {pm.last4}
                    </p>
                    <p className="text-xs text-slate-500">
                      Expires {pm.exp_month.toString().padStart(2, "0")}/{pm.exp_year}
                    </p>
                  </div>
                  <button
                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="Remove card"
                    onClick={() => {
                      // Card removal would call Stripe API to detach payment method
                      alert("Card removal: call Stripe PaymentMethod.detach on your backend");
                    }}
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                </div>
              ))}

              {paymentMethods.length === 0 && !showAddCard && (
                <p className="text-sm text-slate-400 italic">
                  No saved cards yet. Add a card to enable in-app hotel bookings.
                </p>
              )}

              {showAddCard && (
                <AddCardPlaceholder onSuccess={handleCardAdded} />
              )}
            </div>
          )}
        </section>

        {/* Note about Stripe packages */}
        <section className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <p className="text-sm text-amber-800 font-medium">Developer Note</p>
          <p className="text-xs text-amber-700 mt-1">
            Full Stripe Elements card UI requires installing:
            <code className="bg-amber-100 px-1 rounded mx-1">@stripe/stripe-js</code> and
            <code className="bg-amber-100 px-1 rounded mx-1">@stripe/react-stripe-js</code>.
            Set <code className="bg-amber-100 px-1 rounded">NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY</code> in your frontend .env.
          </p>
        </section>
      </main>
    </div>
  );
}
