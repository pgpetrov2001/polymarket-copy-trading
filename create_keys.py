import os
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

# Load your private key securely from .env-style file
load_dotenv("keys.env")

PRIVATE_KEY = os.getenv("PK")
if not PRIVATE_KEY:
    raise RuntimeError("❌ Missing PK in keys.env")

# Initialize client with your private key
client = ClobClient(
    host="https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137  # Polygon mainnet
)

# Generate or fetch your API credentials
api_creds = client.create_or_derive_api_creds()

# Print them out
print("✅ Polymarket CLOB API credentials generated:\n")
print("API Key:      ", api_creds.api_key)
print("Secret:       ", api_creds.api_secret)
print("Passphrase:   ", api_creds.api_passphrase)
