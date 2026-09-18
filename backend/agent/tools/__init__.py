from .escalate import escalate_to_human
from .menu import product_details, search_menu
from .notes import save_note
from .orders import check_order_status, create_order
from .photos import send_product_photo
from .store import store_info

TOOLS = [
    search_menu,
    product_details,
    store_info,
    create_order,
    check_order_status,
    save_note,
    send_product_photo,
    escalate_to_human,
]

__all__ = [
    "TOOLS",
    "search_menu",
    "product_details",
    "store_info",
    "create_order",
    "check_order_status",
    "save_note",
    "send_product_photo",
    "escalate_to_human",
]
