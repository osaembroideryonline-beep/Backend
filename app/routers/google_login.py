from fastapi import Depends
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from fastapi import APIRouter, Request
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import os, httpx
from dotenv import load_dotenv
from app.models import users
import uuid
from app.models.users import User 
from app.services.utils import create_cart_for_user, create_wishlist_for_user

 
load_dotenv()
 
router = APIRouter(prefix='/auth', tags=['oAuth'])
 
# Middleware for sessions
 
 
# OAuth setup
config = Config(environ=os.environ)
oauth = OAuth(config)
 
 
 
 
 
@router.get("/login")
def login():
    print(os.getenv('GOOGLE_REDIRECT_URI'))
    url = (
 
        f"{os.getenv('GOOGLE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth')}"
        f"?client_id={os.getenv('GOOGLE_CLIENT_ID')}"
        f"&redirect_uri={os.getenv('GOOGLE_REDIRECT_URI')}"
        # f"&redirect_uri=http://127.0.0.1:8000/auth/callback"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url)
 
frontend_add = "https://scheduler-frontend.bookzone.ai"
frontend_add = "http://localhost:5173"
frontend_add = "https://osaembroidery.com"
 
 
@router.get("/callback")
async def google_callback(request: Request, db : AsyncSession = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url=frontend_add)
        # raise HTTPException(status_code=400, detail="Missing code")
 
    # Step 3: Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(os.getenv('GOOGLE_TOKEN_URI', "https://accounts.google.com/o/oauth2/auth"), data={
            "code": code,
            "client_id": os.getenv('GOOGLE_CLIENT_ID'),
            "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
            "redirect_uri": os.getenv('GOOGLE_REDIRECT_URI'),
            # "redirect_uri": "http://127.0.0.1:8000/auth/callback",
            "grant_type": "authorization_code"
        })
        print(token_resp)
    token_data = token_resp.json()
    print(token_data )
    access_token = token_data.get("access_token")
 
    if not access_token:
        return RedirectResponse(url=frontend_add)
        # raise HTTPException(status_code=400, detail="Token exchange failed")
 
    # Step 4: Get user info
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
    user_info = user_resp.json()
    print(user_info)
    # Step 5: Create internal JWT
    details = await db.execute(select(users.User).where(users.User.email == user_info["email"]))
    details = details.scalars().first()
   
       
    if details:
 
        response = {
            "id": str(details.id),
            "email": details.email,
            "full_name": f"{details.first_name} {details.last_name}",
            "message": "Login Successful"
        }
        print(response)
    else:
        user_id = f'user_{uuid.uuid4()}'
        
        new_user = users.User(
            id=user_id,
            email=user_info["email"],
            first_name=user_info.get("given_name"),
            last_name=user_info.get("family_name"),
        )
        db.add(new_user)
        await db.commit()
        cart_id = await create_cart_for_user(user_id=user_id, db=db)
        wishlist_id = await create_wishlist_for_user(user_id=user_id, db=db)
        await db.commit()
        response = {
            "id": str(new_user.id),
            "email": new_user.email,
            "full_name": f"{new_user.first_name} {new_user.last_name}",
            "message": "User Created and Login Successful",
        }
        print(response)

    frontend_url = f"https://scheduler-frontend.bookzone.ai/callback?token=scheduler&email={response['email']}&name={response['full_name']}&id={response['id']}&message={response['message']}"

    frontend_url = f"{frontend_add}/callback?token=osa_123&email={response['email']}&name={response['full_name']}&id={response['id']}&message={response['message']}"
    return RedirectResponse(frontend_url)
