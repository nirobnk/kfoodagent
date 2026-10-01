"""Real conversations from Sept 30, 2026, and what a good reply must do.

Each case replays what a customer actually sent (names and numbers left out).
A turn is a burst: the messages that arrived together and get one reply.
The checks are what a good shop assistant would do with the facts in
snapshot.json — not what the agent happened to say on the day, which is how
several of these were found wanting.

Check keys (all optional):
  answered_by    "code" or "model"
  has_price      a "Rs. 650"-style price is in the reply
  contains       every one of these, case-insensitive
  contains_any   at least one of these
  not_contains   none of these
  tools          each of these tools was called
  no_tools       none of these was called
  script         "sinhala": the reply has Sinhala script; "latin": it has none
  max_chars      the reply is no longer than this
At the end of a case, "orders" is how many orders exist and "order_total" the
total of the last one.

An item in a turn is a string (a text message), or a dict:
  {"image": "<what the photo shows>", "caption": "..."}
  {"voice": "<the transcript>"}
"""

from __future__ import annotations

OPENER = "Hi! I want to order Korean ramen 🍜"
FREE = ["free", "FREE", "නොමිලේ", "fri", "free delivery"]
ASKS_ADDRESS = ["address", "ලිපිනය", "lipinaya", "addres", "ලිපිනයයි"]

CASES: list[dict] = [
    # --- the ad opener and bare price questions: answered by code ---------------
    {
        "id": "opener-only",
        "source": "26 customers sent only this and never wrote again",
        "turns": [{"say": [OPENER], "expect": {
            "answered_by": "code", "has_price": True,
            "contains": ["Shin Ramyun Original — *Rs. 650*"], "not_contains": ["Banana"],
        }}],
    },
    {
        "id": "opener-with-emoji",
        "turns": [{"say": ["Hi! I want to order Korean ramen 🍜  👍🤙"], "expect": {"answered_by": "code"}}],
    },
    {
        "id": "price-singlish",
        "turns": [{"say": ["Kiyada"], "expect": {
            "answered_by": "code", "contains": ["Bacchus Energy Drink", "select karala"],
        }}],
    },
    {
        "id": "price-sinhala",
        "turns": [{"say": ["මිල ගනන්"], "expect": {"answered_by": "code", "script": "sinhala"}}],
    },
    {
        "id": "price-list-plz",
        "turns": [{"say": ["price list plz"], "expect": {"answered_by": "code", "has_price": True}}],
    },
    {
        "id": "send-all-prices",
        "source": "the full list was cut off at 900 characters on the day",
        "turns": [{"say": ["Send me all prices"], "expect": {
            "answered_by": "code", "contains": ["OKF Oncup Watermelon", "Bacchus Energy Drink"],
        }}],
    },
    {
        "id": "opener-and-price-together",
        "turns": [{"say": [OPENER, "Price"], "expect": {"answered_by": "code", "contains": ["Bacchus"]}}],
    },
    {
        "id": "opener-with-sinhala-price",
        "turns": [{"say": ["Hi! I want to order Korean ramen 🍜කීයද"], "expect": {
            "answered_by": "code", "script": "sinhala",
        }}],
    },
    # --- spice answers ------------------------------------------------------------
    {
        "id": "medium-spice",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Medium"], "expect": {
                "answered_by": "model", "has_price": True, "tools": ["suggest_products"],
                "contains_any": ["Shin Ramyun Black", "Hot Dak Carbo", "Spicy Chicken", "Kimchi", "Toomba"],
                "script": "latin",
            }},
        ],
    },
    {
        "id": "fire-spice",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Fire"], "expect": {
                "has_price": True,
                "contains_any": ["Hot Dak Stir-Fry Ramen Original", "Red Super Spicy"],
            }},
        ],
    },
    {
        "id": "fire-wants-new-flavour",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Fire"]},
            {"say": ["Had those, looking for a new flavor"], "expect": {"has_price": True}},
        ],
    },
    # --- delivery and payment -----------------------------------------------------
    {
        "id": "delivery-kurunegala",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Deliver kurunegala"], "expect": {"contains": ["400", "5,000"]}},
        ],
    },
    {
        "id": "delivery-kirialla-singlish",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Kiriallata  diliwari  karanawad"], "expect": {"contains": ["400"]}},
        ],
    },
    {
        "id": "delivery-charge-sinhala-nothing-chosen",
        "turns": [
            {"say": [OPENER]},
            {"say": ["මේක dilawari gasthuth ekka kiyada"], "expect": {"contains": ["400"]}},
        ],
    },
    {
        "id": "cash-on-delivery-sinhala",
        "turns": [
            {"say": [OPENER]},
            {"say": ["කැශ් ඔන් ඩිලවරි"], "expect": {
                "contains_any": ["bank transfer", "Bank transfer", "බැංකු", "transfer"],
                "script": "sinhala", "no_tools": ["create_order"],
            }},
        ],
    },
    {
        "id": "minimum-order",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Any minimum order"], "expect": {"contains_any": ["no minimum", "No minimum"]}},
        ],
    },
    {
        "id": "asks-for-bank-details",
        "turns": [{"say": ["Account number eka ewanna"], "expect": {
            "tools": ["payment_details"], "contains": ["123020163895"],
        }}],
    },
    {
        "id": "branch-visit",
        "source": "customer offered to visit a Kurunegala branch; there is none",
        "turns": [
            {"say": ["How much a Korean ramen 🍜 ?"]},
            {"say": ["Medium"]},
            {"say": ["I'll visit your branch in Kurunegala.\nThanks."], "expect": {
                "contains_any": ["online", "walk-in", "courier", "deliver"],
            }},
        ],
    },
    # --- choosing products --------------------------------------------------------
    {
        "id": "carbo-and-cheese",
        "source": "the agent said Hot Dak Cheese was not on the shelf; 1,000 were",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Both"]},
            {"say": ["Carbo and cheese"], "expect": {
                "contains": ["Carbo", "Cheese"],
                "not_contains": ["couldn't find", "could not find", "not available", "out of stock",
                                 "shelf eke na", "don't have", "do not have"],
            }},
            {"say": ["How much is 5 pack of carbo and deliver charge to kadawatha"], "expect": {
                "contains": ["3,750", "400"],
            }},
        ],
    },
    {
        "id": "shin-price-singlish",
        "turns": [{"say": ["Shin ramen noodles price kohomada"], "expect": {
            "answered_by": "model", "contains": ["650"],
        }}],
    },
    {
        "id": "shin-5-pack-price",
        "turns": [{"say": ["5packs price shin Ramyun"], "expect": {"contains": ["3,250"]}}],
    },
    {
        "id": "what-are-the-stocks-then-other-foods",
        "turns": [
            {"say": [OPENER]},
            # They have just been sent the priced list, so "all of those are in
            # stock" is a good answer; repeating every price is not needed.
            {"say": ["What are the stocks"], "expect": {"no_tools": ["create_order"], "max_chars": 700}},
            {"say": ["Any other foods"], "expect": {"contains_any": ["Binggrae", "OKF", "Bacchus", "Banana"]}},
        ],
    },
    {
        "id": "is-this-all",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Almost everything 👍"]},
            {"say": ["Is this all you have"], "expect": {"no_tools": ["create_order"]}},
        ],
    },
    {
        "id": "hi-alone",
        "turns": [{"say": ["Hi"], "expect": {"answered_by": "model", "has_price": True}}],
    },
    {
        "id": "opener-and-sinhala-one-pack-price",
        "turns": [{"say": ["Hi! I want to order Korean ramen 🍜\nපැ 1මිල කීයද"], "expect": {
            "answered_by": "model", "has_price": True,
        }}],
    },
    {
        "id": "noodles-after-price-question",
        "turns": [
            {"say": ["මිල ගනන්"]},
            {"say": ["🍜  noodles"], "expect": {"has_price": True}},
        ],
    },
    {
        "id": "send-what-you-have-sinhala",
        "turns": [
            {"say": [OPENER]},
            {"say": ["මට දානවද තියෙන ඒවා ටික"], "expect": {"has_price": True}},
        ],
    },
    {
        "id": "does-not-understand",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Mata pahadili na"], "expect": {"answered_by": "model", "no_tools": ["create_order"]}},
        ],
    },
    {
        "id": "singlish-short-answers-no-5-pack",
        "source": "Oct 1: 5 Pack prices nobody asked for, descriptions repeated, Sinhala "
                  "script to a customer writing Singlish",
        "turns": [
            {"say": ["Monada oyala laga thiyana ramen"]},
            {"say": ["2 spice vage"], "expect": {
                "has_price": True, "not_contains": ["5 Pack", "5-pack", "3,750", "4,475"],
                "script": "latin",
            }},
            {"say": ["Meva 2 spice da"], "expect": {
                "not_contains": ["5 Pack", "3,750", "4,475"], "script": "latin", "max_chars": 260,
            }},
            {"say": ["Shin black eka kiyada"], "expect": {
                "contains": ["895"], "not_contains": ["5 Pack", "4,475"], "script": "latin",
            }},
        ],
    },
    # --- photos and voice ---------------------------------------------------------
    {
        "id": "photos-request",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Products photos"], "expect": {"tools": ["send_product_photo"]}},
        ],
    },
    {
        "id": "photo-of-shin",
        "turns": [
            {"say": ["Kiyada"]},
            {"say": ["Poto avanavada"]},
            # Eight products are called Shin, so asking which one is fair.
            {"say": ["Shin"], "expect": {"contains_any": ["650", "Original"]}},
        ],
    },
    {
        "id": "customer-photo-red-and-yellow",
        "source": "a customer photographed two packs and asked for both with delivery",
        "turns": [
            {"say": [OPENER]},
            {"say": [{
                "image": "Product photo: Shin Ramyun Original, Chapagetti. A red Shin Ramyun "
                         "Original pack and a yellow Chapagetti pack side by side.",
                "caption": "මේකේ රතු පාට එකයි කහපාට එකයි oni",
            }], "expect": {
                "contains": ["Shin Ramyun Original", "Chapagetti", "1,800"], "script": "sinhala",
            }},
        ],
    },
    {
        "id": "customer-photo-two-packs",
        "turns": [{"say": [{
            "image": "Product photo: Hot Dak Cheese Stir-Fry Ramen, Samyang Buldak 2x Spicy. "
                     "An orange Hot Dak Cheese pack and a black Samyang Buldak 2x Spicy pack.",
            "caption": "Me deka kiyada",
        }], "expect": {"contains": ["Hot Dak Cheese", "750"]}}],
    },
    {
        "id": "voice-note-misheard",
        "source": "a Sinhala voice note came back from transcription in the wrong language",
        "turns": [
            {"say": [OPENER]},
            {"say": [{"voice": "Hi, neenu hogondu productsakke podigaanate naadare. Keertaneeudala, "
                               "podi gargantulu, makkariyalli, ippisheyaanaatayi."}],
             "expect": {"no_tools": ["create_order", "quote_order"]}},
        ],
    },
    # --- totals and orders --------------------------------------------------------
    {
        "id": "nine-packs-free-delivery",
        "source": "Rs. 6,750 of noodles; free delivery over Rs. 5,000",
        "turns": [
            {"say": [OPENER]},
            {"say": ["Shin ramyin spicy chicken-03\nHot dak cheese stir fry ramen-02\n"
                     "Shin rmyun stir fry cheese -02\nShin ramyen red super spicy-02"], "expect": {
                "contains": ["6,750"], "contains_any": FREE, "not_contains": ["7,150"],
                "no_tools": ["create_order"],
            }},
            {"say": ["Epa epa", "Mn kiynnm"], "expect": {"no_tools": ["create_order"]}},
        ],
        "end": {"orders": 0},
    },
    {
        "id": "two-five-packs-free-delivery",
        "source": "quoted Rs. 6,900 on the day; it is Rs. 6,500 with free delivery",
        "turns": [
            {"say": [OPENER, "Price list"]},
            {"say": ["5packs price shin Ramyun"]},
            {"say": ["Deliver chj"], "expect": {"contains": ["400"]}},
            {"say": ["Shin original 5 packs dekk gnnwa nm"], "expect": {
                "contains": ["6,500"], "contains_any": FREE, "not_contains": ["6,900"],
                "no_tools": ["create_order"],
            }},
        ],
        "end": {"orders": 0},
    },
    {
        "id": "order-needs-a-full-address",
        "source": "order #23 went in with 'Kadawatha' as its only address",
        "turns": [
            {"say": ["I want one Hot Dak Carbo 5 pack. Delivery to Kadawatha"], "expect": {
                "contains": ["4,150"],
            }},
            {"say": ["Ok"], "expect": {"contains_any": ASKS_ADDRESS, "no_tools": ["create_order"]}},
            {"say": ["Dinesh Perera, No 12, Church Road, Kadawatha"], "expect": {
                "tools": ["create_order"], "contains": ["4,150", "123020163895"],
            }},
        ],
        "end": {"orders": 1, "order_total": 4150},
    },
    {
        "id": "order-next-month",
        "turns": [
            {"say": [OPENER]},
            {"say": [{
                "image": "Product photo: Shin Ramyun Original, Chapagetti. A red Shin pack and a "
                         "yellow Chapagetti pack.",
                "caption": "මේකේ රතු පාට එකයි කහපාට එකයි oni",
            }]},
            {"say": ["මම් දැන්ම ඕඩර් කරන්නේ නැ\nලබන මාසේ 11 හරි oni"], "expect": {
                "no_tools": ["create_order"],
            }},
        ],
        "end": {"orders": 0},
    },
]
