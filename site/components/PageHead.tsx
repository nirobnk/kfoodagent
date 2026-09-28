/* The per-page <head> tags, written as elements rather than through the
   Metadata API. React 19 hoists <title>, <meta> and <link> into <head>, and
   writing them out keeps each page's tags exactly as the static site had
   them — the Metadata API has no og:type "product", and it fills in
   twitter:title and twitter:description on pages that never had them.

   No image preload here: React already emits one for any <img> marked
   fetchPriority="high" (the home hero, each product photo). */

interface Props {
  title: string;
  description: string;
  canonical: string;
  robots: string;
  og?: {
    type: string;
    title: string;
    description: string;
    url: string;
    image: string;
    imageWidth?: number;
    imageHeight?: number;
    imageType?: string;
    locale?: string;
  };
  twitter?: { title?: string; description?: string; image?: string };
  appleIcon?: boolean;
}

export default function PageHead({ title, description, canonical, robots, og, twitter, appleIcon = true }: Props) {
  return (
    <>
      <title>{title}</title>
      <meta name="description" content={description} />
      <meta name="robots" content={robots} />
      <link rel="canonical" href={canonical} />
      {og && (
        <>
          <meta property="og:type" content={og.type} />
          <meta property="og:site_name" content="K FOOD Sri Lanka" />
          <meta property="og:title" content={og.title} />
          <meta property="og:description" content={og.description} />
          <meta property="og:url" content={og.url} />
          <meta property="og:image" content={og.image} />
          {og.imageWidth && <meta property="og:image:width" content={String(og.imageWidth)} />}
          {og.imageHeight && <meta property="og:image:height" content={String(og.imageHeight)} />}
          {og.imageType && <meta property="og:image:type" content={og.imageType} />}
          {og.locale && <meta property="og:locale" content={og.locale} />}
        </>
      )}
      {og && <meta name="twitter:card" content="summary_large_image" />}
      {twitter?.title && <meta name="twitter:title" content={twitter.title} />}
      {twitter?.description && <meta name="twitter:description" content={twitter.description} />}
      {twitter?.image && <meta name="twitter:image" content={twitter.image} />}
      {appleIcon && <link rel="apple-touch-icon" href="/images/touch-icon.png" />}
    </>
  );
}
