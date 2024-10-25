from typing_extensions import TypedDict, Sequence, List, Dict

class Args(TypedDict):
    item_name: str
    item_quantity: float
    unit_of_measure: str

class ToolCall(TypedDict):
    name: str
    args: Args
    id: str
    type: str

class CartData(TypedDict):
    sku: int
    item_name: str
    item_quantity: float
    unit_price: int
    price: int
    image_url: str

class Quantity(TypedDict):
    desired_quantity: float
    available_quantity: float

class ProductQuantity(TypedDict):
    product: Quantity

class UnitMissMatch (TypedDict):
    item_name: str
    unit_miss_match: bool

class ItemsFound (TypedDict):
    item_name: str
    item_quantity: float

class SimilarItems (TypedDict):
    desired_items: List[str]
    similar_items: List[str]

class AgentState(TypedDict):
    message: str
    tool_calls: List[ToolCall] = []
    cart_data: List[CartData] = []
    next: str = ""
    desired_quantity_error_list: List[ProductQuantity] = []
    item_missing_in_cart_list: List[str] = []
    item_missing_in_store_list: List[str] = []
    unit_of_measure_miss_match: List[UnitMissMatch] = []
    reduce_quantity_error_list: List[str] = []
    grocery_item_looking_for_found_list: List[ItemsFound] = []
    grocery_item_looking_for_not_found_list: List[str] = []
    similar_items_to_items_looking_for_in_store: SimilarItems = {}