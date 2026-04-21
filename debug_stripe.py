import os
import stripe
from dotenv import load_dotenv

load_dotenv()

# Configuration
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY")
CUSTOMER_ID = "cus_UNAl69D254bcrY" 
METER_EVENT_NAME = os.getenv("STRIPE_METER_EVENT_NAME", "json_sanity_tool_invocation")

def test_direct_metering():
    if not STRIPE_KEY:
        print("❌ Error: STRIPE_SECRET_KEY not found in .env")
        return

    stripe.api_key = STRIPE_KEY
    
    print(f"📡 Attempting to send 1 unit to {CUSTOMER_ID}...")
    print(f"🏷️ Using Meter Event Name: {METER_EVENT_NAME}")

    try:
        # First, let's verify if the meter is visible to the API
        meters = stripe.billing.Meter.list(limit=10)
        meter_exists = any(m.event_name == METER_EVENT_NAME for m in meters.data)
        
        if not meter_exists:
            print(f"❌ Error: Could not find an active meter with event name '{METER_EVENT_NAME}'")
            print("Current meters found in your account:")
            for m in meters.data:
                print(f" - {m.display_name} (Event: {m.event_name}, Status: {m.status})")
            return

        # Attempt to create the event
        event = stripe.billing.MeterEvent.create(
            event_name=METER_EVENT_NAME,
            payload={
                "value": "1",
                "stripe_customer_id": CUSTOMER_ID,
            },
        )
        
        if hasattr(event, 'id'):
            print(f"✅ API Accepted Event! ID: {event.id}")
            print("🏁 Success! Now check your 'Events' tab in Stripe.")
        else:
            print("❓ Event created but no ID returned. Check Dashboard.")
            
    except stripe.error.InvalidRequestError as e:
        print(f"❌ Stripe rejected the request: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")

if __name__ == "__main__":
    test_direct_metering()