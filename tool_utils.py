from typing import List, Tuple, Dict, Any
from difflib import SequenceMatcher
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GROCERY_INDEX_PATH = os.path.join(BASE_DIR, "grocery_index")

print(f"Loading FAISS index from: {GROCERY_INDEX_PATH}")
OPENAI_API_KEY="sk-MGdasqvMe-7p4Pux2Yep11DLiaAPFbpBSS7KqA-ZvaT3BlbkFJkiBvwAKuFex5lpoApnbwuEo7-1-r1RktA8N49KPegA"


# embeddings = OpenAIEmbeddings(openai_api_key = os.getenv("OPENAI_API_KEY"))
embeddings = OpenAIEmbeddings(openai_api_key = OPENAI_API_KEY)


def get_sku(item_name:str):
    sku = None
    allow_dangerous_deserialization = True
    database = FAISS.load_local(GROCERY_INDEX_PATH, embeddings, allow_dangerous_deserialization=allow_dangerous_deserialization)
    # database = FAISS.load_local("grocery_index", embeddings)
    result = database.similarity_search_with_relevance_scores(item_name, k=1)

    similarity_score = result[0][1]

    if similarity_score >= 0.85:
        sku = result[0][0].metadata["sku"]
    
    return sku


def get_relevant_products(item_name:str):
    allow_dangerous_deserialization = True
    database = FAISS.load_local(GROCERY_INDEX_PATH, embeddings, allow_dangerous_deserialization=allow_dangerous_deserialization)
    # database = FAISS.load_local("grocery_index", embeddings)
    result = database.similarity_search_with_relevance_scores(item_name, k=3)
    
    similar_products = {}
    desired_product = []
    similarity_score = result[0][1]
    sku = 0

    if similarity_score >= 0.85:
        desired_product = [result[0][0].metadata]
        sku = result[0][0].metadata["sku"]
    
    if similarity_score >= 0.80 and similarity_score < 0.85:
        list_similar_items = []
        list_similar_items.append(result[0][0].metadata["product_name"])
        list_similar_items.append(result[1][0].metadata["product_name"])
        list_similar_items.append(result[2][0].metadata["product_name"])
        similar_products["item_name"] = item_name
        similar_products["similar_items"] = list_similar_items

    return desired_product, similar_products, sku


def check_quantity_from_store(desired_quantity: float, unit_of_measure: str, relevant_products: List):
    store_quantity = relevant_products[0].get('quantity_in_stock')
    unit = relevant_products[0].get('unit_to_measure').lower()
    unit_of_measure_l = unit_of_measure.lower()

    unit_miss_match = False

    if SequenceMatcher(None, unit, unit_of_measure_l).ratio() > .6:
        pass
    else:
        unit_miss_match = True

    return (desired_quantity, store_quantity, unit_miss_match)

def get_item_detail(grocery_cart, sku):
    cart_quantity = None
    cart_unit = ""
    product_url = ""
    product_name = ""
    unit_price = 0
    cart_item_sku = None

    for product in grocery_cart:

        cart_item_sku = product.get("sku")

        if cart_item_sku is not None:
            if int(cart_item_sku) == int(sku):
                unit_price = int(product.get("unit_price"))
                p_unit = product.get("item_quantity")
                cart_quantity = float(p_unit.split(" ")[0])
                cart_unit = p_unit.split(" ")[1]
                product_url = product.get("image_url")
                product_name = product.get("item_name")

    return cart_quantity, cart_unit, product_url, product_name, unit_price

def remove_duplicate(item_name_list: List):
    unique_items = []

    for item in item_name_list:
        if item not in unique_items:
            unique_items.append(item)
    
    return unique_items


def prepare_similar_item_dict(similar_item_dict: Dict, grocery_item_name: str, grocery_similar_items: List):

    if similar_item_dict:
        similar_item_dict["desired_items"].append(grocery_item_name)
        temp_list = similar_item_dict["similar_items"]
        temp_list.extend(grocery_similar_items)
        temp_list = remove_duplicate(temp_list)
        similar_item_dict["similar_items"].extend(temp_list)

    else:

        similar_item_dict["desired_items"] = []
        similar_item_dict["similar_items"] = []
        similar_item_dict["desired_items"].append(grocery_item_name)
        similar_item_dict["similar_items"].extend(grocery_similar_items)
    
    return similar_item_dict

###############################################################################################################
############################################ Add Items to Cart ################################################
###############################################################################################################

def add_grocery_item_to_cart(item_name: str, item_quantity: float, unit_of_measure: str, grocery_cart: List):
    products_not_found_in_store = ""
    unit_miss_match = {}
    desired_quantity_error = {}
    cart = {}
    similar_items_in_store = {}
    
    desired_product, similar_products, sku = get_relevant_products(item_name)
    
    if desired_product:
        cart_quantity, _, _, _, _ = get_item_detail(grocery_cart, sku)
        if cart_quantity is not None:
            item_quantity = item_quantity + cart_quantity

        output_tupple = check_quantity_from_store(
            item_quantity, unit_of_measure, desired_product
        )
        unit_of_measure = desired_product[0].get('unit_to_measure')
        product_url = desired_product[0].get('image_uri')
        unit_price = desired_product[0].get('price_per_unit')
        product_name = desired_product[0].get('product_name')

    elif len(similar_products) > 0:
        similar_items_in_store = similar_products
        return (products_not_found_in_store, unit_miss_match, desired_quantity_error, similar_items_in_store, cart)
    else:
        products_not_found_in_store = item_name
        return (products_not_found_in_store, unit_miss_match, desired_quantity_error, similar_items_in_store, cart)

    desired_quantity = output_tupple[0]
    store_quantity = output_tupple[1]
    wrong_unit = output_tupple[2]

    if wrong_unit:
        unit_miss_match = {"item_name": product_name, "unit_miss_match": wrong_unit}
        return (products_not_found_in_store, unit_miss_match, desired_quantity_error, similar_items_in_store, cart)

    if desired_quantity >  store_quantity:
        des_quant_str = str(desired_quantity) + " " + unit_of_measure
        store_quant_str = str(store_quantity) + " " + unit_of_measure
        
        desired_quantity_error = {
            "item_name": product_name, 
            "desired_quantity": des_quant_str, 
            "available_quantity": store_quant_str
        }
    else:
        
        product_str = str(round(item_quantity, 2)) + " " + unit_of_measure
        price = round((item_quantity * unit_price), 2)
        cart = {
            "sku": sku,
            "item_name": product_name, 
            "item_quantity": product_str, 
            "unit_price": unit_price, 
            "price": price, 
            "image_url":product_url
        }
    
    return (products_not_found_in_store, unit_miss_match, desired_quantity_error, similar_items_in_store, cart)

def increase_grocery_item_quantity_in_cart(item_name: str, item_quantity: float, unit_of_measure: str, grocery_cart: List):
    products_not_found_in_store = ""
    unit_miss_match = {}
    desired_quantity_error = {}
    cart = {}
    product_not_found_in_cart = ""

    desired_product, _, sku = get_relevant_products(item_name)

    cart_quantity, _, _, _, _ = get_item_detail(grocery_cart, sku)
    if cart_quantity is None:
        product_not_found_in_cart = item_name
        return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)
    
    # desired_product, _, sku = get_relevant_products(item_name)
    if desired_product: 
        output_tupple = check_quantity_from_store(
            item_quantity, unit_of_measure, desired_product
        )
        unit_of_measure = desired_product[0].get('unit_to_measure')
        product_url = desired_product[0].get('image_uri')
        unit_price = desired_product[0].get('price_per_unit')
        product_name = desired_product[0].get('product_name')
    else:
        products_not_found_in_store = item_name
        return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)

    desired_quantity = output_tupple[0]
    store_quantity = output_tupple[1]
    wrong_unit = output_tupple[2]

    # print("desired_quantity_1: ", desired_quantity)

    desired_quantity = cart_quantity + desired_quantity

    if wrong_unit:
        unit_miss_match = {"item_name": product_name, "unit_miss_match": wrong_unit}
        return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)
    
    if desired_quantity > store_quantity:
        des_quant_str = str(desired_quantity) + " " + unit_of_measure
        store_quant_str = str(store_quantity) + " " + unit_of_measure
        desired_quantity_error = {
            "item_name": product_name, 
            "desired_quantity": des_quant_str, 
            "available_quantity": store_quant_str
        }
    else:
        # print("desired_quantity_2: ", desired_quantity)
        product_str = str(round(desired_quantity, 2)) + " " + unit_of_measure
        price = round((desired_quantity * unit_price), 2)
        cart = {
            "sku": sku,
            "item_name": product_name, 
            "item_quantity": product_str, 
            "unit_price": unit_price, 
            "price": price,
            "image_url":product_url
        }
    
    return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)


def reduce_grocery_item_quantity_in_cart(item_name: str, item_quantity: float, unit_of_measure: str, grocery_cart: List):
    unit_miss_match = {}
    cart = {}
    product_not_found_in_cart = ""
    products_not_found_in_store = ""
    quantity_reduce_error = ""

    sku = get_sku(item_name)

    cart_quantity, cart_unit, product_url, product_name, unit_price = get_item_detail(grocery_cart, sku)
    if cart_quantity is None:
        product_not_found_in_cart = item_name
        return (product_not_found_in_cart, unit_miss_match, quantity_reduce_error, cart)
    
    if SequenceMatcher(None, cart_unit.lower(), unit_of_measure.lower()).ratio() > .7:
        pass
    else:
        unit_miss_match = {"item_name": item_name, "unit_miss_match": False}
        return (product_not_found_in_cart, unit_miss_match, quantity_reduce_error, cart)
    
    desired_quantity = cart_quantity - item_quantity
    
    if desired_quantity > 0:
        product_str = str(round(desired_quantity, 2)) + " " + cart_unit
        price = round((desired_quantity * unit_price), 2)
    
        cart = {
            "sku": sku,
            "item_name": product_name, 
            "item_quantity": product_str, 
            "unit_price": unit_price, 
            "price": price,
            "image_url":product_url
        }
        
    else:
        # quantity_reduce_error = item_name
        # cart = [d for d in cart if d["item_name"] != item_name]
        product_str = str(0.0) + " " + cart_unit
        cart = {
            "sku": sku,
            "item_name": product_name, 
            "item_quantity": product_str, 
            "unit_price": unit_price, 
            "price": 0.0,
            "image_url":product_url
        }
    return(product_not_found_in_cart, unit_miss_match, quantity_reduce_error, cart)

def set_item_quantity(item_name: str, item_quantity: float, unit_of_measure: str, grocery_cart: List):
    products_not_found_in_store = ""
    product_not_found_in_cart = ""
    unit_miss_match = {}
    desired_quantity_error = {}
    cart = {}
    
    desired_product, _, sku = get_relevant_products(item_name)

    cart_quantity, cart_unit, product_url, product_name, unit_price = get_item_detail(grocery_cart, sku)
    if cart_quantity is None:
        product_not_found_in_cart = item_name
        return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)
    
    if cart_quantity > item_quantity:
        product_str = str(item_quantity) + " " + cart_unit
        price = item_quantity * unit_price
        # print("price: ", price)
        # cart = {"item_name": product_name, "item_quantity": product_str, "image_url":product_url}
        cart = {
            "sku": sku,
            "item_name": product_name, 
            "item_quantity": product_str, 
            "unit_price": unit_price, 
            "price": price,
            "image_url":product_url
        }
    else:
        if desired_product: 
            output_tupple = check_quantity_from_store(
                item_quantity, unit_of_measure, desired_product
            )
            unit_of_measure = desired_product[0].get('unit_to_measure')
            product_url = desired_product[0].get('image_uri')
            unit_price = desired_product[0].get('price_per_unit')
            product_name = desired_product[0].get('product_name')
        else:
            products_not_found_in_store = item_name
            return (products_not_found_in_store, unit_miss_match, desired_quantity_error, cart)

        desired_quantity = output_tupple[0]
        store_quantity = output_tupple[1]
        wrong_unit = output_tupple[2]

        if wrong_unit:
            unit_miss_match = {"item_name": product_name, "unit_miss_match": wrong_unit}
            return (products_not_found_in_store, unit_miss_match, desired_quantity_error, cart)

        if desired_quantity >  store_quantity:
            des_quant_str = str(desired_quantity) + " " + unit_of_measure
            store_quant_str = str(store_quantity) + " " + unit_of_measure
            
            desired_quantity_error = {
                "item_name": product_name, 
                "desired_quantity": des_quant_str, 
                "available_quantity": store_quant_str
            }
        else:
            product_str = str(round(item_quantity, 2)) + " " + unit_of_measure
            price = round((item_quantity * unit_price), 2)
            cart = {
                "sku": sku,
                "item_name": product_name, 
                "item_quantity": product_str, 
                "unit_price": unit_price, 
                "price": price, 
                "image_url":product_url
            }
            
    return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)