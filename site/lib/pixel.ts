/* Meta Pixel — the new ad account's pixel.

   Events on this site:
     PageView         → every page, from the base code in app/layout.tsx
     ViewContent      → product pages (app/products/[handle]/page.tsx)
     AddToCart        → components/AddToCartButton.tsx, components/ProductBuy.tsx
     InitiateCheckout → components/CartView.tsx, when the cart page shows items
     Lead             → components/CartView.tsx, on the WhatsApp handoff
   Purchase is NOT fired here: a WhatsApp message is not a confirmed, paid
   order. That belongs to the backend, once staff mark the order paid.

   Every page is a full page load (plain <a> links, no client-side routing),
   so the base code runs, and PageView fires, exactly once per page. */

export const PIXEL_ID = "1453079580075970";

export const PIXEL_BASE_CODE = `!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}
(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '${PIXEL_ID}');
fbq('track', 'PageView');`;

export const PIXEL_NOSCRIPT_SRC = `https://www.facebook.com/tr?id=${PIXEL_ID}&ev=PageView&noscript=1`;

type Fbq = (command: string, event: string, params?: Record<string, unknown>) => void;

/* A blocked pixel (ad blockers, privacy settings) must never break the cart. */
export function track(event: string, params: Record<string, unknown>, custom = false) {
  const fbq = (window as unknown as { fbq?: Fbq }).fbq;
  if (!fbq) return;
  fbq(custom ? "trackCustom" : "track", event, params);
}
