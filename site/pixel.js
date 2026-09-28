/* ============================================================
   K FOOD — Meta Pixel
   Loaded in the <head> of index.html, cart.html and every
   generated products/<handle>.html (see build.mjs).
   Events fired elsewhere:
     ViewContent      → products/<handle>.html (build.mjs template)
     AddToCart        → cart.js, quick-add handler
     InitiateCheckout → cart.js, cart page render
     Lead             → cart.js, WhatsApp handoff
   Purchase is NOT fired here: a WhatsApp message is not a
   confirmed, paid order. Log those from Events Manager once the
   bank transfer clears.
   ============================================================ */

!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}
(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');

fbq('init', '1453079580075970');
fbq('track', 'PageView');
