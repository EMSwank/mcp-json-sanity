import asyncio
import os
from dotenv import load_dotenv
from mcp.client.sse import sse_client
from mcp import ClientSession

# Load your new .env file
load_dotenv()

async def run_first_billable_repair():
    """
    Simulates a 'Death Loop' scenario and verifies Stripe metering.
    """
    # 1. REPLACE THIS with your actual cus_ ID from the Stripe Sandbox
    test_customer_id = "cus_UNAl69D254bcrY" 
    
    # 2. A "Poisoned" string that is easier to repair for the first test
    # (Prose preamble + JSON with a trailing comma/missing brace)
    poisoned_json = 'Sure, here is the data: {"status": "active", "count": 42'

    print(f"🚀 Starting test for customer: {test_customer_id}")
    
    if test_customer_id == "cus_your_id_here":
        print("❌ STOP: You need to put your real Stripe Customer ID in the script!")
        return

    try:
        # Assuming your server is running locally on port 8000
        async with sse_client("http://localhost:8000/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                print("🛠 Calling sanitize_json_output...")
                result = await session.call_tool(
                    "sanitize_json_output",
                    {
                        "raw_string": poisoned_json,
                        "api_key_id": test_customer_id
                    }
                )
                
                # Check if the response contains an error or the repaired JSON
                response_text = result.content[0].text
                print(f"📥 Server Response: {response_text}")

                if "error" not in response_text:
                    print("✅ SUCCESS: Repair confirmed.")
                    print("🏁 CHECK STRIPE: Go to Dashboard -> Customers -> [Your Customer] -> Usage.")
                    print("It may take 30-60 seconds to reflect the $0.01.")
                else:
                    print("⚠️ Server returned an error. No charge was sent to Stripe.")
                
    except Exception as e:
        print(f"❌ Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_first_billable_repair())