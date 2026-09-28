/* Types for products-data.js, which stays plain JavaScript because
   menu/menu-card.html loads it with a <script> tag. */

export interface Nutrition {
  basis: string;
  energy?: string;
  fat?: string;
  satFat?: string;
  carbs?: string;
  fibre?: string;
  sugars?: string;
  protein?: string;
  sodium?: string;
}

export interface Variant {
  sku: string;
  label: string;
  price: number;
  units: number;
}

export interface Product {
  handle: string;
  name: string;
  ko?: string;
  brand: string;
  category: string;
  pack: string;
  heat?: number | null;
  cook?: string;
  badge?: string;
  image: string;
  gallery?: string[];
  short: string;
  long: string;
  serve: string;
  ingredients: string;
  allergens: string;
  nutrition: Nutrition | null;
  variants: Variant[];
}

export const KFOOD_PRODUCTS: Product[];
export const KFOOD_NOODLE_CATEGORIES: string[];
export const KFOOD_WHATSAPP: string;
