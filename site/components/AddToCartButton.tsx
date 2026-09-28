"use client";

import { addToCart } from "@/lib/cart";
import { track } from "@/lib/pixel";
import { toast } from "@/lib/toast";

interface Props {
  sku: string;
  name: string;
  label: string;
  price: number;
  className: string;
  children: React.ReactNode;
}

/* A one-tap add: one of this SKU, a toast, and the pixel's AddToCart. */
export default function AddToCartButton({ sku, name, label, price, className, children }: Props) {
  return (
    <button
      type="button"
      className={className}
      data-add-sku={sku}
      onClick={() => {
        addToCart(sku, 1);
        track("AddToCart", {
          content_ids: [sku],
          content_type: "product",
          content_name: name,
          contents: [{ id: sku, quantity: 1 }],
          value: price,
          currency: "LKR",
        });
        toast(`Added ${name} (${label}) to cart.`);
      }}
    >
      {children}
    </button>
  );
}
