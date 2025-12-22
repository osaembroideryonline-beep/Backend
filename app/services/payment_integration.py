import razorpay
import hmac
import hashlib
import os

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_API_KEY")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


async def create_payment_link(amount: float, customer_details : dict, currency: str = "INR") -> dict:
    try:
        print(customer_details)
       
        payment_data = {
            "amount": int(amount * 100),
            "currency": currency,
            "customer": {
                "name": customer_details["name"],
                "email": customer_details["email"],
                "contact": customer_details["phone"]
            },
            "notify": {
                "sms": True,
                "email": True
            },
            "description": "Payment Link",
            "callback_url": "https://osaembroidery.com/payment-success",
            # "callback_url": "http://localhost:5173/payment-success",
            "callback_method": "get"
        }

        response = razorpay_client.payment_link.create(payment_data)
        print(response)
        response = razorpay_client.payment_link.create(payment_data)

# Update notes immediately (optional but recommended)
        razorpay_client.payment_link.edit(response["id"], {
            "notes": {
                "payment_link_id": response["id"]
            }
        })
        


        return {
            # "order_id": response["order_id"],
            "payment_link_id": response["id"],
            "redirect_url": response["short_url"] 
        }
    except Exception as e:
        print(f"Error creating Razorpay payment link: {e}")
        return None

