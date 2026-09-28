/* The catalogue, and the small derivations every page shares.
   Ported one-for-one from the helpers in the old build.mjs — the page
   copy, alt text and structured data are built from these, so a change
   here changes what Google reads. */

import { KFOOD_PRODUCTS, KFOOD_WHATSAPP } from "@/products-data";
import type { Product } from "@/products-data";

export type { Product, Variant, Nutrition } from "@/products-data";

export const SITE = "https://kfoods.lk";
export const PRODUCTS: Product[] = KFOOD_PRODUCTS;
export const WHATSAPP: string = KFOOD_WHATSAPP;

export const DELIVERY_FEE = 400;          /* LKR — flat island-wide courier charge */
export const FREE_DELIVERY_OVER = 5000;   /* LKR — subtotal at which delivery is free */

export function getProduct(handle: string): Product | undefined {
  return PRODUCTS.find((p) => p.handle === handle);
}

export const isNoodle = (p: Product) => p.category !== "Beverages";

/* Brand-qualified product name for SEO copy, alt text and structured data.
   Several beverage names already start with the brand ("OKF Olatte Peach"),
   so prefixing blindly would print "OKF OKF Olatte Peach". */
export const fullName = (p: Product) =>
  p.name.startsWith(p.brand) ? p.name : `${p.brand} ${p.name}`;

/* 450px thumbnails exist for the large product jpegs */
export const thumb = (img: string) =>
  img.startsWith("images/products/") && img.endsWith(".jpeg")
    ? img.replace("images/products/", "images/products/thumbs/")
    : img;

/* every image for a product: the main one first, then any extra gallery shots */
export const shots = (p: Product) => [p.image, ...(p.gallery || [])];

/* "pack" / "cup" / "can" / "bottle" / "carton" — taken from the first variant label */
export const unitWord = (p: Product) =>
  (p.variants[0].label.replace(/^Single\s*/i, "") || "pack").toLowerCase();

/* Products are stored with site-relative image paths ("images/..."). */
export const src = (path: string) => `/${path}`;

/* Related products: same category first, then the rest; 4 fills the mobile 2-up grid. */
export function related(p: Product): Product[] {
  const pool = PRODUCTS.filter((q) => q.handle !== p.handle && q.category === p.category);
  const others = PRODUCTS.filter((q) => q.handle !== p.handle && q.category !== p.category);
  return pool.concat(others).slice(0, 4);
}

/* What the cart needs to know about each SKU — nothing more ships to the browser. */
export interface CartItem {
  sku: string;
  handle: string;
  name: string;
  label: string;
  price: number;
  image: string;
}

export function cartIndex(): Record<string, CartItem> {
  const index: Record<string, CartItem> = {};
  for (const p of PRODUCTS) {
    for (const v of p.variants) {
      index[v.sku] = { sku: v.sku, handle: p.handle, name: p.name, label: v.label, price: v.price, image: p.image };
    }
  }
  return index;
}

export const allSkus = () => PRODUCTS.flatMap((p) => p.variants.map((v) => v.sku));
