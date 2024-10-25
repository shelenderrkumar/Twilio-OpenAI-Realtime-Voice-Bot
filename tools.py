from langchain_core.tools import tool

from langchain_community.tools import TavilySearchResults


import os
import time
import random
import requests
import datetime
import pandas as pd
from langchain_community.document_loaders import DirectoryLoader
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.storage._lc_store import create_kv_docstore
from langchain.storage import LocalFileStore
from langchain.retrievers import ParentDocumentRetriever
from langchain.tools.retriever import create_retriever_tool

from langchain_google_community.gmail.send_message import GmailSendMessage as OriginalGmailSendMessage
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from langchain_google_community import GmailToolkit
from langchain_google_community.gmail.utils import (
    build_resource_service,
    get_gmail_credentials,
)



upsell =False

from typing import List
# from difflib import SequenceMatcher
from langchain_core.tools import InjectedToolArg, tool
# import os
from typing_extensions import Annotated
# from langgraph.prebuilt import InjectedState
# from langchain_openai import OpenAIEmbeddings
# from langchain_community.vectorstores import FAISS
from tool_utils import add_grocery_item_to_cart, increase_grocery_item_quantity_in_cart, get_sku, get_relevant_products, \
    reduce_grocery_item_quantity_in_cart, set_item_quantity


# embeddings = OpenAIEmbeddings(openai_api_key = os.getenv("OPENAI_API_KEY"))
    
@tool
def add_modify_grocery_item_to_cart(
    item_name: str, item_quantity: float, unit_of_measure: str, action: str, grocery_cart: Annotated[List, InjectedToolArg]
):
    """ Adds grocery items into the cart list or modify (increase or decrease) the grocery item quantity.
    Args:
        item_name: grocery item name :str
        item_quantity: quantity of grocery item: int
        unit_of_measure: unit of measure: str
        action: This is the important parameters, if customer adds a grocery item, make the action parameter as 'add',
        if the customer increase the quantity of grocery item, make the action parameter as 'plus',
        if the customer decreases or reduce the quantity of grocery item in cart, make the action parameter as 'minus',
        and lastly, if the customer want to set the quantity of an item make the action parameter as 'set'.
        grocery_cart: cart object for the grocery items
    """
    cart = []
    products_not_found_in_store = ""
    product_not_found_in_cart = ""
    unit_miss_match = {}
    desired_quantity_error = {}
    similar_items_in_store = []
    cart_dict = {}
    quantity_reduce_error = ""

    if action == "add":
        set_output_tupple = add_grocery_item_to_cart(item_name, item_quantity, unit_of_measure, grocery_cart)
        products_not_found_in_store = set_output_tupple[0]
        unit_miss_match = set_output_tupple[1]
        desired_quantity_error = set_output_tupple[2]
        similar_items_in_store = set_output_tupple[3]
        cart_dict = set_output_tupple[4]
        # print(cart_dict)
        # grocery_cart.append(cart_dict)

    elif action == "plus":
        add_output_tupple = increase_grocery_item_quantity_in_cart(item_name, item_quantity, unit_of_measure, grocery_cart)
        products_not_found_in_store = add_output_tupple[0]
        product_not_found_in_cart = add_output_tupple[1]
        unit_miss_match = add_output_tupple[2]
        desired_quantity_error = add_output_tupple[3]
        cart_dict = add_output_tupple[4]
        # print("cart_dict: ", cart_dict)
        # grocery_cart = [cart_dict if d["item_name"] == cart_dict["item_name"] else d for d in grocery_cart]
    
    elif action == "minus":
        reduce_output_tupple = reduce_grocery_item_quantity_in_cart(item_name, item_quantity, unit_of_measure, grocery_cart)
        product_not_found_in_cart = reduce_output_tupple[0]
        unit_miss_match = reduce_output_tupple[1]
        quantity_reduce_error = reduce_output_tupple[2]
        cart_dict = reduce_output_tupple[3]
        # print("cart_dict: ", cart_dict)

        # grocery_cart = [cart_dict if d["item_name"] == cart_dict["item_name"] else d for d in grocery_cart]
        # print("grocery_cart: ", grocery_cart)
    elif action == "set":
        set_output_tupple = set_item_quantity(item_name, item_quantity, unit_of_measure, grocery_cart)
        # return (products_not_found_in_store, product_not_found_in_cart, unit_miss_match, desired_quantity_error, cart)
    
        products_not_found_in_store = set_output_tupple[0]
        product_not_found_in_cart = set_output_tupple[1]
        unit_miss_match = set_output_tupple[2]
        desired_quantity_error = set_output_tupple[3]
        cart_dict = set_output_tupple[4]
    return (
        products_not_found_in_store, 
        product_not_found_in_cart, 
        unit_miss_match, 
        desired_quantity_error, 
        quantity_reduce_error,
        similar_items_in_store,
        cart_dict
    )

@tool
def remove_item_from_cart(item_name: str, grocery_cart: Annotated[List, InjectedToolArg]):
    """ Romove a grocery item from the cart the user already added.
    Args:
        item_name: name of the grocery item to be removed
        grocery_cart: cart object for the grocery items
    """
    removed_item_error = ""

    def product_name_exists(cart: List, sku: int):
        for product in cart:
            cart_item_sku = product.get("sku")

            if sku == cart_item_sku:
                return True
        return False
    
    
    def remove_product_by_name(cart: List, sku: int):
        updated_cart = []
        for product in cart:
            if sku != product.get("sku"):
                updated_cart.append(product)

        return updated_cart
    

    sku = get_sku(item_name)
    u_cart = []

    if item_name is not None and len(grocery_cart) > 0:
        if (product_name_exists(grocery_cart, sku)):
            # print("product exixt:::")
            u_cart = remove_product_by_name(grocery_cart, sku)
        else:
            u_cart = grocery_cart
            removed_item_error = item_name

    # print("u_cart: ", u_cart)
    return (u_cart, removed_item_error)


@tool
def grocery_item_info(item_name: str):
    """Provides information about a specific grocery item in the store
    Args:
        item_name: The name of the grocery item to look up.
    """
    product_not_found = ""
    product_found = {}
    
    desired_product, _, sku = get_relevant_products(item_name)

    # r_len = len(desired_product)
    # if r_len == 0:
    #     product_not_found = item_name
    
    if desired_product:
        product_str = str(desired_product[0].get("quantity_in_stock")) + " " + desired_product[0].get("unit_to_measure")
        product_found = {
            "item_name": desired_product[0].get("product_name"), 
            # "item_quantity": product_str
        }
    else :
        product_not_found = item_name
    
    return product_not_found, product_found



@tool
def complete_cart_details(grocery_cart: Annotated[List, InjectedToolArg]):
    """Provides information about a complete cart item in the store and total price
    """

    items = []
    total_price = 0

    for item in grocery_cart:
        items.append(item['item_name'])
        total_price += item['price'] 
    
    # total_price = int(total_price/270)
    total_price = str(total_price) + "dollars"
    
    return {'all_items_purchased': items, 'total_price_of_all_items': total_price}






@tool
def check_tracking_status(tracking_number: str):
    """Tool to retrieve tracking information based on tracking number.
    
    Retrieve and display tracking information for a given tracking number.

    Args:
        tracking_number (str): The tracking number to query.

    Returns:
        dict: A dictionary containing the latest tracking information formatted for readability.
    """

    file_name='tracking_numbers.csv'
    tracking_number = int(tracking_number)

    try:
        data = pd.read_csv(file_name)
        
        # Check if the tracking number exists in the DataFrame
        # print(data['Tracking Number'].values)
        # print(type(data['Tracking Number'].values[0]))
        
        if tracking_number in data['Tracking Number'].values:
            # Get the status for the found tracking number
            status = data.loc[data['Tracking Number'] == tracking_number, 'Status'].values[0]
            # print(status)
            return {'result': f"Tracking number {tracking_number} has status: {status}"}
        
        else:
            return {'result': f"Tracking number {tracking_number} not found."}
        
    except FileNotFoundError:
        return {'error': f"File '{file_name}' not found."}
    

    # # Open the CSV file in read mode
    # try:
    #     with open(file_name, mode='r') as file:
    #         reader = csv.reader(file)
            
    #         # Skip the header row
    #         next(reader)

    #         print("File is opened")
            
    #         for row in reader:
    #             print(f"The row is: {row}")
    #             if row[0] == str(tracking_number):
    #                 print("Checking the order:.....")
    #                 return {'result': f"Tracking number {tracking_number} has status: {row[1]}"}
    #                 # return f"Tracking number {tracking_number} has status: {row[1]}"
            
    #         # If the tracking number is not found
    #         return {'result': f"Tracking number {tracking_number} not found."}
    #         # return f"Tracking number {tracking_number} not found."

    # except FileNotFoundError:
    #     return {'error': f"File '{file_name}' not found."}




# @tool
# def save_grocercy_order():

#     """Tool to save order information
    
#     Save the order information along with tracking number


#     Returns:
#         dict: A dictionary containing the latest tracking information formatted for readability.
#     """

#     file_name='tracking_numbers.csv'

#     tracking_number = str(random.randint(100000, 999999))

#     status = "Order is preparing..." 
    
#     file_exists = os.path.isfile(file_name)
    
#     with open(file_name, mode='a', newline='') as file:
#         writer = csv.writer(file)
        
#         # Write the header if the file does not exist
#         if not file_exists:
#             writer.writerow(['Tracking Number', 'Status'])
        
#         # Write the tracking number and status to the file
#         writer.writerow([tracking_number, status])
    

#     return {'result': f"Tracking number {tracking_number}"}



@tool
def save_grocery_order(address: str, mobile_number: int):
    """Tool to save order information

    Saves the order information along with tracking number, address, and mobile number.

    Args:
        address (str): The delivery address.
        mobile_number (int): The customer's mobile number.

    Returns:
        dict: A dictionary containing the information that order with tracking number is saved
    """

    file_name = 'tracking_numbers.csv'

    tracking_number = str(random.randint(100000, 999999))
    status = "Order is preparing..."

    if os.path.isfile(file_name):
        data = pd.read_csv(file_name)
    else:
        data = pd.DataFrame(columns=['Tracking Number', 'Status', 'Address', 'Mobile Number'])
        # data = pd.DataFrame(columns=['Tracking Number', 'Status'])


    # new_entry = pd.DataFrame({'Tracking Number': [tracking_number], 'Status': [status]})
    new_entry = pd.DataFrame({'Tracking Number': [tracking_number], 'Status': [status], 'Address': [address], 'Mobile Number': [mobile_number]})

    data = pd.concat([data, new_entry], ignore_index=True)


    data.to_csv(file_name, index=False)

    return {'result': f"Tracking number {tracking_number}. Order will be delievered within 30 minutes."}



@tool
def generate_promotional_message():
    """
    Tool to send the promtional message to the user

    Returns:
        promo_message: A promotional message if it is not sent already
        None: Returns nothing if promotional message is already sent
    """

    global upsell
    if upsell == False:


        items = ["Apples", "Banana", "Oranges"]
        product = random.choice(items)
    

        promo_message = f"We are offering an exclusive discount on {product}! Don't miss out on this amazing deal."

        upsell = True
    
        return promo_message
    
    return None



@tool
def submit_complaint(tracking_number: str, complaint: str, email: str) -> dict:
    """Tool to submit complaint of the customer

    Args:
        tracking_number (str): The tracking numbe of the order
        complaint (str): Complaint details
        email (str): Customer's email address

    Returns:
        dict: A dictionary ontaining the information that about the complaint submission.
    """

    # Prepare complaint data

    file_name = 'tracking_numbers.csv'
    tracking_number = int(tracking_number)

    try:
        data = pd.read_csv(file_name)

        # Check if the tracking number exists in the DataFrame
        if tracking_number in data['Tracking Number'].values:
            # Retrieve address and mobile number for the given tracking number
            order_info = data.loc[data['Tracking Number'] == tracking_number]
            address = order_info['Address'].values[0]
            mobile_number = order_info['Mobile Number'].values[0]
        else:
            return {'error': f"Tracking number {tracking_number} not found."}

    except FileNotFoundError:
        return {'error': f"File '{file_name}' not found."}

    complaint_data = {
        "complaint": complaint,
        "tracking_number": tracking_number,
        "email": email,
        "address": address,
        "mobile_number": mobile_number
    }
    # complaint_data = {
    #     "complaint": complaint,
    #     "tracking_number":tracking_number,
    #     "email": email
    # }

    response = send_email_with_attachment(complaint_data, email)
    return response




class GmailSendMessageWithAttachment(OriginalGmailSendMessage):
    def send_message_with_attachments(
        self, sender: str, to: str, subject: str, body_text: str, cc: List[str] = None
    ) -> dict:
        """Send an email with attachments using the Gmail API."""
        message = MIMEMultipart()
        message['to'] = to
        message['from'] = sender
        message['subject'] = subject
        
        print("Inside gmail class")
        if cc:
            message['cc'] = ', '.join(cc)

        msg_body = MIMEText(body_text, 'plain')
        message.attach(msg_body)


        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        # return self.api_resource.users().messages().send(userId="me", body={'raw': raw_message}).execute()
        result = self.api_resource.users().messages().send(userId="me", body={'raw': raw_message}).execute()
        
        
        return result


#     # Initialize the toolkit
credentials = get_gmail_credentials(
    token_file="token.json",
    scopes=["https://mail.google.com/"],
    client_secrets_file="credentials.json",
)
api_resource = build_resource_service(credentials=credentials)
toolkit = GmailToolkit(api_resource=api_resource)

    

def send_email_with_attachment(complaint_data: dict, email: str):
    # Your email sending logic here
   
    # recipient_email = "shelender001@gmail.com"
    recipient_email = email
    cc_emails = ["skumar.bscs20seecs@seecs.edu.pk", "basit@forloops.co"]
    # cc_emails = "skumar.bscs20seecs@seecs.edu.pk"
    # cc_emails = ["Basit.r.Sheikh@instaworld.pk"]
    subject = "Grocery Bot: Complaint"
    
    email_body = f"""
    Dear Customer Support Department,

    The following complaint has been Received through Grocery AI Voice Bot:

    Complaint:  {complaint_data['complaint']}
    Order ID:   {complaint_data['tracking_number']}
    Customer E-mail:   {complaint_data['email']}
    Customer Address:  {complaint_data['address']}
    Customer Mobile No.:  {complaint_data['mobile_number']}


    Best regards,
    Grocery AI Voice Bot
    """
    

    
    send_message_tool = GmailSendMessageWithAttachment(api_resource=api_resource)
    response = send_message_tool.send_message_with_attachments(
        sender="abdullah.rauf@forloops.co",
        to=recipient_email,
        subject=subject,
        body_text=email_body,
        cc=cc_emails
    )
    

    print(f"The response after sending email is: {response}")
    return response



# @tool
# def add(a: int, b: int):
#     """Add two numbers. Please let the user know that you're adding the numbers BEFORE you call the tool"""
#     return a + b


"""
******************************************************************************************************
******************************************************************************************************
"""


tavily_tool = TavilySearchResults(
    max_results=5,
    include_answer=True,
    description=(
        "This is a search tool for accessing the internet.\n\n"
        "Let the user know you're asking your friend Tavily for help before you call the tool."
    ),
)



#############################################
UPLOAD_DIR = "testdata/"
store_location = "./store_location"
loader = DirectoryLoader(UPLOAD_DIR)
doc_instaworld = loader.load()
key = "9a4f0d0f-e882-4f84-944f-7370e0987745"
pc = Pinecone(api_key=key)
# pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY")) 


embedding_function = OpenAIEmbeddings(
    model="text-embedding-3-small",
    # With the `text-embedding-3` class
    # of models, you can specify the size
    # of the embeddings you want returned.
    dimensions=1536
)

# existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
# print(existing_indexes)


index_name = 'testinsta'  


# if index_name not in existing_indexes:
# if index_name in pc.list_indexes().names():
#     pc.delete_index(index_name)
#     print("creating indexes")
#     pc.create_index(
#         name=index_name,
#         # dimension=1024,
#         dimension=1536,
#         metric="cosine",
#         # metric="dotproduct",
#         spec=ServerlessSpec(cloud="aws", region="us-east-1"),
#     )
#     while not pc.describe_index(index_name).status["ready"]:
#         time.sleep(1)


if index_name not in pc.list_indexes().names():
    print(f"Index '{index_name}' does not exist. Please create it first.")
else:
    print(f"Index '{index_name}' found. Using the existing index.")



index = pc.Index(index_name)
vectorstore = PineconeVectorStore(index=index,embedding=embedding_function)

parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)


fs = LocalFileStore(store_location)
store_instaworld = create_kv_docstore(fs)


retriever_instaworld = ParentDocumentRetriever(
    vectorstore=vectorstore,
    docstore=store_instaworld,
    child_splitter=child_splitter,
    parent_splitter=parent_splitter,
)

retriever_instaworld.add_documents(documents=doc_instaworld)




def get_tracking_info(tracking_number: str) -> dict:
    """
    Retrieve and display tracking information for a given tracking number from InstaWorld.

    Args:
        tracking_number (str): The tracking number to query.

    Returns:
        dict: A dictionary containing the latest tracking information formatted for readability.
    """
    url = "https://one-be.instaworld.pk/logistics/trackingHistory"
    params = {"tracking_number": tracking_number}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an error for bad status codes
        tracking_data = response.json()

        # Extract the latest tracking event and additional information if available
        latest_event = tracking_data.get('tracking_history', [{}])[-1]
        tracking_status = tracking_data.get('tracking_status', 'Status not available')

        # Consignee and Shipper details
        consignee_info = {
            "Consignee Name": tracking_data.get('consignee_name', 'N/A'),
            "Consignee First Name": tracking_data.get('consignee_first_name', 'N/A'),
            "Consignee Last Name": tracking_data.get('consignee_last_name', 'N/A'),
            "Consignee Email": tracking_data.get('consignee_email', 'N/A'),
            "Consignee Phone": tracking_data.get('consignee_phone', 'N/A'),
            "Consignee Address": tracking_data.get('consignee_address', 'N/A'),
        }

        shipper_info = {
            "Shipper Name": tracking_data.get('shipper_name', 'N/A'),
            "Shipper Email": tracking_data.get('shipper_email', 'N/A'),
            "Shipper City": tracking_data.get('shipper_city', 'N/A')
        }

        # Compile the information in a human-readable format
        human_readable_info = {
            "Tracking Number": tracking_number,
            "Shipment Number": latest_event.get('shipment', 'shipment Number not available'),
            "Status": latest_event.get('status', 'Status not available'),
            "Timestamp": latest_event.get('date_time', 'Timestamp not available'),
            "Tracking Status": tracking_status
        }

        # Convert the dictionary into a human-readable format with bullet points
        formatted_info = "\n".join([
            f"• Tracking Number: {human_readable_info['Tracking Number']}",
            f"• Shipment Number: {human_readable_info['Shipment Number']}",
            f"• Status: {human_readable_info['Status']}",
            f"• Timestamp: {human_readable_info['Timestamp']}",
            f"• Tracking Status: {human_readable_info['Tracking Status']}",
            "",
            "Consignee Information:",
            f"• Name: {consignee_info['Consignee Name']}",
            f"• Email: {consignee_info['Consignee Email']}",
            f"• Phone: {consignee_info['Consignee Phone']}",
            f"• Address: {consignee_info['Consignee Address']}",
            "",
            "Shipper Information:",
            f"• Name: {shipper_info['Shipper Name']}",
            f"• Email: {shipper_info['Shipper Email']}",
            f"• City: {shipper_info['Shipper City']}"
        ])
        
        return {"latest_tracking_info": formatted_info}

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return {"error": str(e)}


# Decorate the tool using @tool
@tool
def instaworld_tracking_tool(tracking_number: str) -> dict:
    """Tool to retrieve tracking information from InstaWorld based on tracking number."""
    return get_tracking_info(tracking_number)


# Forloops retrieval function
def instaworld(query: str) -> list:
    """
    Retrieve relevant information about InstaWorld based on the provided query.

    Args:
        query (str): The search query related to InstaWorld, including its history, services, FAQ, client information, job opportunities, projects, job details, contact information, and CEO information.

    Returns:
        List[Document]: A list of documents that are relevant to the query.
    """
    if retriever_instaworld is None:
        print("Retriever not initialized. Please ensure files are processed first.")
        return []

    return retriever_instaworld.get_relevant_documents(query=query)
    # return retriever_instaworld.invoke(input=query)
    # return retriever_instaworld.similarity_search(query=query)
    # return vectorstore.similarity_search(query=query)


function_description = """
    This tool is specifically designed to retrieve detailed and relevant information about Instaworld, a company recognized for its strengths in logistics and delivery services. 
    Use this tool to answer queries related to Instaworld's business process, service rates, major operational cities, packaging materials, volumetric weight charges, and comprehensive scope of services. 
    Additionally, this tool provides insights into Instaworld's operations process, claims handling, customer support, and terms and conditions, including their right of inspection and materials not acceptable for transport. 
    It also covers the booking procedure, financial status, and miscellaneous options available. Moreover, the tool guides users on how to lodge a query, understand delivery and payment timelines, and get an overall understanding of Instaworld's offerings.
    """

retriever_instaworld_txt = create_retriever_tool(
    retriever_instaworld,
    "instaworld",
    f"""{function_description}"""
)



TOOLS = [instaworld_tracking_tool, retriever_instaworld_txt, tavily_tool]
# TOOLS = [add_modify_grocery_item_to_cart, remove_item_from_cart, grocery_item_info, complete_cart_details, save_grocery_order, check_tracking_status, generate_promotional_message, submit_complaint]
