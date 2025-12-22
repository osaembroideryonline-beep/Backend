from fastapi import Depends
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from fastapi import APIRouter, Request 
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import os,httpx
from dotenv import load_dotenv
from app.models.admin import Admin
from sqlalchemy.future import select

load_dotenv()

router = APIRouter(prefix='/admin', tags=['oAuth'])

# Middleware for sessions


# OAuth setup
config = Config(environ=os.environ)
oauth = OAuth(config)





@router.get("/login")
def login():
    url = ( 
        f"{os.getenv('GOOGLE_AUTH_URI')}"
        f"?client_id={os.getenv('GOOGLE_CLIENT_ID')}"
        f"&redirect_uri={os.getenv('ADMIN_GOOGLE_REDIRECT_URI')}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url)


frontend_add = "https://admin.brainstermath.com"
# frontend_add = "https://d2yyk8e1pvcyy7.cloudfront.net"
@router.get("/auth/callback")
async def google_callback(request: Request, db : AsyncSession = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url=frontend_add)
        # raise HTTPException(status_code=400, detail="Missing code")
 
    # Step 3: Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(os.getenv('GOOGLE_TOKEN_URI'), data={
            "code": code,
            "client_id": os.getenv('GOOGLE_CLIENT_ID'),
            "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
            "redirect_uri": os.getenv('ADMIN_GOOGLE_REDIRECT_URI'),
            "grant_type": "authorization_code"
        })
    token_data = token_resp.json()
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
    # Step 5: Create internal JWT
    details = await db.execute(select(Admin).where(Admin.email == user_info["email"]))
    details = details.scalars().first()
    response = {}
    frontend_add = "https://osa-admin-nu.vercel.app"
    if details: 
        if details.email == user_info['email'] :
            response['email'] = details.email
            response['full_name'] = details.first_name + " " + details.last_name
            response['id'] = 'admin'
            response['message'] = "success"
    else : 
        # response['email'] = None
        # response['full_name'] = None
        # response['id'] = None
        # response['message'] = "User Not an Admin"
        return RedirectResponse(url=f'{frontend_add}/loginerror')
    
    frontend_add = "https://admin.osaembroidery.com"
    frontend_url = f'{frontend_add}/callback?token=scheduler&email={response["email"]}&name={response["full_name"]}&id={response["id"]}&message={response["message"]}'
    return RedirectResponse(frontend_url)


