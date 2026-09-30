import { useCallback, useRef, useState } from "react";

import { paymentService } from "../services/paymentService";

/**
 * Razorpay checkout flow.
 *
 * The sequence, and why each step exists:
 *
 * 1. Ask Django to create the order. The **price comes from the database**, so a
 *    tampered client cannot choose what to pay.
 * 2. Open Razorpay Checkout with the returned public key id.
 * 3. On success, send the three Razorpay identifiers to our backend. The signing
 *    key lives only on the server, which is the only party that can decide
 *    whether the payment actually succeeded.
 *
 * A client-side "success" callback is treated as *unverified input*, never as
 * proof of payment.
 */

function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(true);
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

function idempotencyKey(planSlug) {
  // Scoped to the plan + a short time bucket so an impatient double-click reuses
  // one order instead of charging twice.
  const bucket = Math.floor(Date.now() / 60000);
  return `${planSlug}-${bucket}`;
}

export function useCheckout() {
  const [status, setStatus] = useState("idle"); // idle | creating | checkout | verifying | done | error
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const busyRef = useRef(false);

  const pay = useCallback(async (planSlug) => {
    if (busyRef.current) return null; // guard against double submission
    busyRef.current = true;
    setError(null);
    setResult(null);

    try {
      setStatus("creating");
      const { checkout } = await paymentService.createOrder({
        planSlug,
        idempotencyKey: idempotencyKey(planSlug),
      });

      const loaded = await loadRazorpayScript();
      if (!loaded) {
        throw {
          code: "checkout_unavailable",
          message:
            "Could not load the payment window. Check your connection and retry.",
        };
      }

      setStatus("checkout");

      return await new Promise((resolve, reject) => {
        const instance = new window.Razorpay({
          key: checkout.key_id,
          amount: checkout.amount,
          currency: checkout.currency,
          name: checkout.name,
          description: checkout.description,
          order_id: checkout.order_id,
          prefill: checkout.prefill,
          theme: { color: "#d4af37" },
          // Razorpay's own retry UI is friendlier than anything we could build.
          retry: { enabled: true, max_count: 2 },
          handler: async (response) => {
            setStatus("verifying");
            try {
              // Server-side signature verification — the authoritative step.
              const verified = await paymentService.verifyPayment({
                orderId: response.razorpay_order_id,
                paymentId: response.razorpay_payment_id,
                signature: response.razorpay_signature,
              });
              setStatus("done");
              setResult(verified);
              resolve(verified);
            } catch (caught) {
              setStatus("error");
              setError(caught);
              reject(caught);
            }
          },
          modal: {
            // The student closed the window: not an error, just no payment.
            ondismiss: () => {
              setStatus("idle");
              resolve(null);
            },
          },
        });

        instance.on("payment.failed", (failure) => {
          const reason =
            failure?.error?.description ||
            "The payment was declined by the bank. Please try another method.";
          const caught = { code: "payment_failed", message: reason };
          setStatus("error");
          setError(caught);
          reject(caught);
        });

        instance.open();
      });
    } catch (caught) {
      setStatus("error");
      setError(caught);
      return null;
    } finally {
      busyRef.current = false;
    }
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setError(null);
    setResult(null);
  }, []);

  return {
    pay,
    status,
    error,
    result,
    reset,
    isBusy: ["creating", "checkout", "verifying"].includes(status),
  };
}

export default useCheckout;
