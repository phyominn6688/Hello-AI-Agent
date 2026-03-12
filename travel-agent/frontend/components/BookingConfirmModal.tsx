"use client";

import { useState } from "react";
import { XIcon, CreditCardIcon, CheckCircleIcon, Loader2Icon } from "lucide-react";
import { confirmBooking } from "@/lib/api";
import type { ItineraryItem } from "@/types";

interface Props {
  item: ItineraryItem;
  priceBreakdown: Record<string, number>;
  currency: string;
  paymentMethodId: string;
  cardLast4?: string;
  onConfirm: (bookingToken: string) => void;
  onCancel: () => void;
}

export default function BookingConfirmModal({
  item,
  priceBreakdown,
  currency,
  paymentMethodId,
  cardLast4,
  onConfirm,
  onCancel,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const total = Object.values(priceBreakdown).reduce((sum, v) => sum + v, 0);
  const currencySymbol = currency === "USD" ? "$" : currency + " ";

  const handleConfirm = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await confirmBooking({
        item_id: item.id,
        payment_method_id: paymentMethodId,
        booking_type: item.type,
        booking_payload: {},
      });
      onConfirm(result.booking_token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Payment setup failed. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">Confirm Booking</h2>
          <button
            onClick={onCancel}
            className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4 space-y-4">
          {/* Item name */}
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide font-medium">Booking</p>
            <p className="font-semibold text-slate-800 mt-0.5">{item.name}</p>
            {item.start_time && (
              <p className="text-sm text-slate-500">{item.start_time.slice(0, 5)}</p>
            )}
          </div>

          {/* Price breakdown */}
          <div className="bg-slate-50 rounded-xl px-4 py-3 space-y-1.5">
            {Object.entries(priceBreakdown).map(([label, amount]) => (
              <div key={label} className="flex justify-between text-sm">
                <span className="text-slate-600 capitalize">{label.replace(/_/g, " ")}</span>
                <span className="text-slate-800">
                  {currencySymbol}{amount.toLocaleString()}
                </span>
              </div>
            ))}
            <div className="border-t border-slate-200 pt-1.5 flex justify-between font-semibold">
              <span className="text-slate-800">Total</span>
              <span className="text-slate-900">
                {currencySymbol}{total.toLocaleString()}
              </span>
            </div>
          </div>

          {/* Payment method */}
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <CreditCardIcon className="w-4 h-4 text-slate-400" />
            {cardLast4 ? (
              <span>Charged to card ending in {cardLast4}</span>
            ) : (
              <span>Charged to saved payment method</span>
            )}
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Actions */}
        <div className="px-5 py-4 border-t border-slate-100 flex gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-4 py-2.5 text-sm font-medium text-slate-700 bg-slate-100 rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-primary-600 rounded-xl hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2Icon className="w-4 h-4 animate-spin" />
                Processing…
              </>
            ) : (
              <>
                <CheckCircleIcon className="w-4 h-4" />
                Confirm & Book
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
