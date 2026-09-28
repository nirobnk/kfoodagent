"use client";

import { useState } from "react";

/* The product photo, and a thumbnail strip when a product has more than one.
   No product has a gallery yet; the strip appears as soon as one does. */
export default function ProductMedia({ images, alt }: { images: { full: string; thumb: string }[]; alt: string }) {
  const [active, setActive] = useState(0);
  const hero = (
    // eslint-disable-next-line @next/next/no-img-element -- plain <img>: indexed URLs must not change
    <img id="pd-hero" src={images[active].full} alt={alt} width={700} height={700} fetchPriority="high" />
  );
  if (images.length < 2) return <figure className="pd__media">{hero}</figure>;

  return (
    <figure className="pd__media pd__media--gallery">
      {hero}
      <div className="pd__shots">
        {images.map((img, i) => (
          <button
            key={img.full}
            type="button"
            className={i === active ? "pd__shot is-active" : "pd__shot"}
            data-full={img.full}
            aria-current={i === active ? "true" : undefined}
            aria-label={`Show image ${i + 1} of ${images.length}`}
            onClick={() => setActive(i)}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- plain <img>: indexed URLs must not change */}
            <img src={img.thumb} alt="" width={450} height={450} loading="lazy" decoding="async" />
          </button>
        ))}
      </div>
    </figure>
  );
}
