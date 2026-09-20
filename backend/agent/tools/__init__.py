from .dietary import find_dietary_options
from .escalate import escalate_to_human, flag_for_staff
from .menu import product_details, search_menu
from .notes import save_note
from .orders import check_order_status, create_order
from .payments import payment_details, record_payment_receipt
from .photos import send_product_photo
from .recommend import suggest_products
from .store import store_info

TOOLS = [
    search_menu,
    find_dietary_options,
    suggest_products,
    product_details,
    store_info,
    payment_details,
    create_order,
    check_order_status,
    record_payment_receipt,
    save_note,
    send_product_photo,
    flag_for_staff,
    escalate_to_human,
]

__all__ = [
    "TOOLS",
    "search_menu",
    "find_dietary_options",
    "suggest_products",
    "product_details",
    "store_info",
    "payment_details",
    "create_order",
    "check_order_status",
    "record_payment_receipt",
    "save_note",
    "send_product_photo",
    "flag_for_staff",
    "escalate_to_human",
]
