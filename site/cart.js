/* ============================================================
   K FOOD — cart + shop behaviour (no backend, localStorage only)
   Checkout = WhatsApp order message to the shop.
   No order minimum — any cart with at least one item can check out.
   ============================================================ */

(function () {
  "use strict";

  var STORAGE_KEY = "kfood_cart_v1";
  var DELIVERY_FEE = 400;        /* LKR — flat island-wide courier charge */
  var FREE_DELIVERY_OVER = 5000; /* LKR — subtotal at which delivery is free */

  /* ---------- catalogue lookups ---------- */

  function findVariant(sku) {
    for (var i = 0; i < KFOOD_PRODUCTS.length; i++) {
      var p = KFOOD_PRODUCTS[i];
      for (var j = 0; j < p.variants.length; j++) {
        if (p.variants[j].sku === sku) return { product: p, variant: p.variants[j] };
      }
    }
    return null;
  }

  /* ---------- storage ---------- */

  function load() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter(function (l) { return l && findVariant(l.sku) && l.qty > 0; }) : [];
    } catch (e) { return []; }
  }

  function save(lines) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(lines)); } catch (e) {}
    updateBadges();
  }

  /* ---------- cart API ---------- */

  var Cart = {
    lines: function () { return load(); },

    add: function (sku, qty) {
      qty = qty || 1;
      var lines = load();
      var hit = null;
      lines.forEach(function (l) { if (l.sku === sku) hit = l; });
      if (hit) hit.qty += qty; else lines.push({ sku: sku, qty: qty });
      save(lines);
    },

    setQty: function (sku, qty) {
      var lines = load().map(function (l) {
        if (l.sku === sku) l.qty = qty;
        return l;
      }).filter(function (l) { return l.qty > 0; });
      save(lines);
    },

    remove: function (sku) {
      save(load().filter(function (l) { return l.sku !== sku; }));
    },

    clear: function () { save([]); },

    detailed: function () {
      return load().map(function (l) {
        var f = findVariant(l.sku);
        return {
          sku: l.sku,
          qty: l.qty,
          product: f.product,
          variant: f.variant,
          lineTotal: f.variant.price * l.qty
        };
      });
    },

    /* amount = goods subtotal, delivery = courier, total = what the customer pays */
    totals: function () {
      var t = { amount: 0, itemCount: 0 };
      Cart.detailed().forEach(function (d) {
        t.amount += d.lineTotal;
        t.itemCount += d.qty;
      });
      t.delivery = (t.itemCount === 0 || t.amount >= FREE_DELIVERY_OVER) ? 0 : DELIVERY_FEE;
      t.total = t.amount + t.delivery;
      return t;
    },

    canCheckout: function () {
      return Cart.totals().itemCount > 0;
    }
  };

  window.KCart = Cart;

  /* ---------- helpers ---------- */

  function fmt(n) { return "LKR " + n.toLocaleString("en-LK"); }
  window.kfoodFmt = fmt;

  function updateBadges() {
    var t = Cart.totals();
    document.querySelectorAll("[data-cart-count]").forEach(function (el) {
      el.textContent = t.itemCount;
      el.hidden = t.itemCount === 0;
    });
  }

  /* ---------- toast ---------- */

  var toastTimer = null;
  function toast(msg, cartHref) {
    var el = document.getElementById("kf-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "kf-toast";
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.innerHTML = "";
    el.appendChild(document.createTextNode(msg + " "));
    var a = document.createElement("a");
    a.href = cartHref || "cart.html";
    a.textContent = "View cart →";
    el.appendChild(a);
    el.classList.add("toast--show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("toast--show"); }, 3200);
  }

  /* ---------- quick add buttons (data-add-sku) ---------- */

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-add-sku]");
    if (!btn) return;
    ev.preventDefault();
    var sku = btn.getAttribute("data-add-sku");
    var qtyInput = document.getElementById("pd-qty");
    var qty = 1;
    if (btn.hasAttribute("data-use-qty") && qtyInput) {
      qty = Math.max(1, parseInt(qtyInput.value, 10) || 1);
    }
    var f = findVariant(sku);
    if (!f) return;
    Cart.add(sku, qty);
    if (window.fbq) fbq("track", "AddToCart", {
      content_ids: [sku],
      content_type: "product",
      content_name: f.product.name,
      contents: [{ id: sku, quantity: qty }],
      value: f.variant.price * qty,
      currency: "LKR"
    });
    toast("Added " + f.product.name + " (" + f.variant.label + ") to cart.", btn.getAttribute("data-cart-href") || "cart.html");
  });

  /* ---------- category filter tabs (home page) ---------- */

  document.querySelectorAll("[data-filter]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var cat = tab.getAttribute("data-filter");
      document.querySelectorAll("[data-filter]").forEach(function (t) {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      document.querySelectorAll("[data-category]").forEach(function (card) {
        card.hidden = cat !== "all" && card.getAttribute("data-category") !== cat;
      });
    });
  });

  /* ---------- product page: variant picker ---------- */

  var pdPrice = document.getElementById("pd-price");
  if (pdPrice) {
    var radios = document.querySelectorAll("input[name='pd-variant']");
    var addBtn = document.getElementById("pd-add");
    function syncVariant() {
      radios.forEach(function (r) {
        if (r.checked) {
          var f = findVariant(r.value);
          pdPrice.textContent = fmt(f.variant.price);
          addBtn.setAttribute("data-add-sku", r.value);
        }
        r.closest(".pd__variant").classList.toggle("is-active", r.checked);
      });
    }
    radios.forEach(function (r) { r.addEventListener("change", syncVariant); });
    syncVariant();

    var qty = document.getElementById("pd-qty");
    document.querySelectorAll("[data-qty-step]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = Math.max(1, (parseInt(qty.value, 10) || 1) + parseInt(b.getAttribute("data-qty-step"), 10));
        qty.value = v;
      });
    });
  }

  /* ---------- Meta Pixel: InitiateCheckout ---------- */

  function trackInitiateCheckout() {
    if (checkoutTracked || !window.fbq) return;
    var t = Cart.totals();
    if (t.itemCount === 0) return;
    checkoutTracked = true;
    fbq("track", "InitiateCheckout", {
      num_items: t.itemCount,
      value: t.total,
      currency: "LKR",
      content_type: "product",
      contents: Cart.detailed().map(function (d) {
        return { id: d.sku, quantity: d.qty };
      })
    });
  }

  /* ---------- cart page ---------- */

  var cartRoot = document.getElementById("cart-root");
  var checkoutTracked = false;
  if (cartRoot) renderCartPage();

  function renderCartPage() {
    trackInitiateCheckout();
    var listEl = document.getElementById("cart-lines");
    var emptyEl = document.getElementById("cart-empty");
    var summaryEl = document.getElementById("cart-summary");
    var det = Cart.detailed();

    emptyEl.hidden = det.length > 0;
    summaryEl.hidden = det.length === 0;
    listEl.innerHTML = "";

    det.forEach(function (d) {
      var li = document.createElement("li");
      li.className = "cline";
      li.innerHTML =
        '<a class="cline__media" href="products/' + d.product.handle + '.html">' +
        '<img src="' + d.product.image + '" alt="" width="72" height="72" loading="lazy"></a>' +
        '<div class="cline__info">' +
        '<a class="cline__name" href="products/' + d.product.handle + '.html"></a>' +
        '<p class="cline__meta"></p>' +
        '<button class="cline__remove" type="button">Remove</button>' +
        "</div>" +
        '<div class="cline__qty">' +
        '<button type="button" class="qty__btn" data-step="-1" aria-label="Decrease quantity">−</button>' +
        '<span class="qty__num" aria-live="polite"></span>' +
        '<button type="button" class="qty__btn" data-step="1" aria-label="Increase quantity">+</button>' +
        "</div>" +
        '<p class="cline__total"></p>';

      li.querySelector(".cline__name").textContent = d.product.name;
      li.querySelector(".cline__meta").textContent =
        d.variant.label + " · " + fmt(d.variant.price);
      li.querySelector(".qty__num").textContent = d.qty;
      li.querySelector(".cline__total").textContent = fmt(d.lineTotal);
      li.querySelector(".cline__remove").addEventListener("click", function () {
        Cart.remove(d.sku); renderCartPage();
      });
      li.querySelectorAll(".qty__btn").forEach(function (b) {
        b.addEventListener("click", function () {
          Cart.setQty(d.sku, d.qty + parseInt(b.getAttribute("data-step"), 10));
          renderCartPage();
        });
      });
      listEl.appendChild(li);
    });

    var t = Cart.totals();
    document.getElementById("cart-items").textContent =
      "(" + t.itemCount + (t.itemCount === 1 ? " item)" : " items)");
    document.getElementById("cart-subtotal").textContent = fmt(t.amount);
    document.getElementById("cart-total").textContent = fmt(t.total);

    var delEl = document.getElementById("cart-delivery");
    delEl.textContent = t.delivery === 0 ? "Free" : fmt(t.delivery);
    delEl.classList.toggle("is-free", t.delivery === 0);

    var checkoutBtn = document.getElementById("checkout-btn");
    var empty = t.itemCount === 0;
    checkoutBtn.disabled = empty;
    checkoutBtn.setAttribute("aria-disabled", empty ? "true" : "false");

    /* carry the amount on the button, so what you pay sits with what you press */
    var btnTotal = document.getElementById("checkout-btn-total");
    if (btnTotal) btnTotal.textContent = empty ? "" : fmt(t.total);

    /* free delivery note */
    var shipnote = document.getElementById("cart-shipnote");
    if (shipnote) {
      shipnote.textContent = t.delivery === 0
        ? "✓ Free delivery — your order is over " + fmt(FREE_DELIVERY_OVER) + "."
        : "Add " + fmt(FREE_DELIVERY_OVER - t.amount) + " more to get free delivery.";
    }
  }

  /* ---------- checkout form → WhatsApp ---------- */

  var form = document.getElementById("checkout-form");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!Cart.canCheckout()) return;

      var v = function (id) {
        var el = document.getElementById(id);
        return el ? (el.value || "").trim() : "";
      };
      var name = v("f-name"), phone = v("f-phone"), address = v("f-address"),
          city = v("f-city"), district = v("f-district"),
          postal = v("f-postal"), notes = v("f-notes");
      var pay = form.querySelector("input[name='f-pay']:checked");
      pay = pay ? pay.value : "Bank Transfer";

      var t = Cart.totals();
      var msg = "🍜 NEW ORDER — kfoods.lk\n\n";
      Cart.detailed().forEach(function (d, i) {
        msg += (i + 1) + ". " + d.product.name + " — " + d.variant.label +
               " × " + d.qty + " = " + fmt(d.lineTotal) + "\n";
      });
      msg += "\nItems: " + t.itemCount + "\n";
      msg += "Subtotal: " + fmt(t.amount) + "\n";
      msg += t.delivery === 0
        ? "Delivery: FREE (order over " + fmt(FREE_DELIVERY_OVER) + ")\n"
        : "Delivery: " + fmt(t.delivery) + "\n";
      msg += "TOTAL: " + fmt(t.total) + "\n";
      msg += "\n— Delivery details —\n";
      msg += "Name: " + name + "\n";
      msg += "Phone: " + phone + "\n";
      msg += "Address: " + address + ", " + city + "\n";
      msg += "District: " + district + "\n";
      if (postal) msg += "Postal code: " + postal + "\n";
      msg += "Payment: " + pay + "\n";
      if (notes) msg += "Notes: " + notes + "\n";
      msg += "\n(Sent from kfoods.lk online store)";

      if (window.fbq) {
        /* Lead, not Purchase: the order is not confirmed or paid until the
           bank transfer lands. Log real purchases from Events Manager. */
        fbq("track", "Lead", {
          value: t.total,
          currency: "LKR",
          content_name: "WhatsApp order sent"
        });
        fbq("trackCustom", "WhatsAppOrderSubmitted", {
          value: t.total,
          currency: "LKR",
          num_items: t.itemCount
        });
      }

      window.location.href = "https://wa.me/" + KFOOD_WHATSAPP + "?text=" + encodeURIComponent(msg);
    });
  }

  updateBadges();
})();
