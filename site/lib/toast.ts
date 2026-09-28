/* "Added Shin Ramyun Original (5 Pack) to cart. View cart →"

   One element, created on first use and appended to <body>, outside the
   React tree — every page shows at most one toast and nothing reads it back. */

let timer: ReturnType<typeof setTimeout> | undefined;

export function toast(msg: string, cartHref = "/cart.html") {
  let el = document.getElementById("kf-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "kf-toast";
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = "";
  el.appendChild(document.createTextNode(msg + " "));
  const a = document.createElement("a");
  a.href = cartHref;
  a.textContent = "View cart →";
  el.appendChild(a);
  el.classList.add("toast--show");
  clearTimeout(timer);
  const shown = el;
  timer = setTimeout(() => shown.classList.remove("toast--show"), 3200);
}
