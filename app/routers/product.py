from itertools import product
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Query, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.product import Product
from sqlalchemy.future import select
from typing import List, Optional, Union
from app.services.cloudinary import upload_file_to_cloudinary
from app.services.r2_client import upload_to_r2, generate_r2_download_url, delete_from_r2, upload_image_to_r2
from app.models.orderitems import OrderItem
from app.models.orders import Order
import json

router = APIRouter(prefix="/products", tags=["products"])


def valid_upload(f):
    return hasattr(f, "filename") and bool(f.filename)



@router.get("/get_all_products_infinite_scroll")
async def get_products(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0)
):
    # Fetch paginated products
    result = await db.execute(
        select(Product).order_by(Product.date_created.desc(), Product.id.desc()).offset(offset).limit(limit)
    )
    products = result.scalars().all()

    # Get total count for frontend decision making
    total_query = await db.execute(select(func.count(Product.id)))
    total = total_query.scalar()
    product_details = [product for product in products]
    return {
        "products": product_details,
        "total": total,
        "limit": limit,
        "offset": offset,
        "hasMore": offset + limit < total
    }

@router.get("/get_all_products")
async def get_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return products

        
@router.get('/latest_products')
async def get_latest_products(db: AsyncSession = Depends(get_db), limit: int = 10):
    result = await db.execute(select(Product).order_by(Product.date_created.desc()).limit(limit))
    products = result.scalars().all()
    
    return products


@router.get("/{product_id}")
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product  




@router.get("/category/{category_name}")
async def get_products_by_category(category_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.category == category_name))
    products = result.scalars().all()
    return products


@router.get("/get_sub_category_names/{category_name}")
async def get_sub_category_names(category_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product.sub_category).where(Product.category == category_name).distinct())
    sub_categories = [row[0] for row in result.all() if row[0] is not None]
    return sub_categories

@router.get("/category_wise/{category}/{sub_category_name}")
async def get_products_by_sub_category(category: str, sub_category_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.category == category).where(Product.sub_category == sub_category_name))
    products = result.scalars().all()
    return products


@router.post("/add_product")
async def add_product(request: Request,
                      name : str = Form(...),
                      description : str = Form(None),
                      price : float = Form(...),
                      discount_price : float = Form(None),
                      in_stock : bool = Form(True),
                      sub_category : str = Form(None),
                      category : str = Form(None),
                      brand : str = Form(None),
                      images : List[UploadFile] = File(...),
                      db: AsyncSession = Depends(get_db)):
    
        # Upload images first
    images_urls = []
    for image in images:
        upload_result = await upload_image_to_r2(image)
        if upload_result:
            images_urls.append(upload_result)
    form = await request.form()
    print("Form items:", list(form.items()))

    downloadable_files = {}

    for key, value in form.items():

        # Skip normal fields
        if key in ["name", "description", "price", "discount_price", "in_stock",
                "sub_category", "category", "brand", "machine_type", "color", "size", 
                "stock_count", "images"]:
            continue

        # Detect files even if type mismatch between Starlette/FastAPI UploadFile
        if hasattr(value, "filename") and value.filename:
            downloadable_files[key] = value

    print(f"Detected downloadable files: {downloadable_files.keys()}")

    downloadable_files_urls = {}

    for key, value in downloadable_files.items():
        print(f"Uploading downloadable file: {key}")
        file_url = await upload_to_r2(value)
        downloadable_files_urls[key] = file_url

    print("Downloadable files URLs:", downloadable_files_urls)
    machine_type = None
    if downloadable_files_urls:
        machine_type = list(downloadable_files_urls.keys())
    new_product = Product(
        name=name,
        description=description,
        price=price,
        discount_price=discount_price,
        in_stock=in_stock,
        sub_category=sub_category,
        images_urls=images_urls,
        category=category,
        brand=brand,
        machine_type=machine_type,
        downloadable_files=json.dumps(downloadable_files_urls) if downloadable_files_urls else None,
    )
    db.add(new_product)
    await db.commit()
    await db.refresh(new_product)
    return new_product



@router.delete("/{product_id}")
async def delete_product(product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    
    # Delete associated files from R2
    if product.downloadable_files:
        for file_url in json.loads(product.downloadable_files).values():
            await delete_from_r2(file_url)
    await db.delete(product)
    await db.commit()
    return {"detail": "Product deleted successfully"}




@router.get("/generate-r2-url/{product_id}")
async def generate_r2_url(product_id: str, expiry: int = 3600, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    
    urls = {}
    for file_type, file_url in json.loads(product.downloadable_files).items():
        if file_type == 'embroidery_dst':
            download_url = await generate_r2_download_url(file_url, expiry)
            urls[f'{file_type}_url'] = download_url
    
    return urls







@router.put("/edit_product/{product_id}")
async def update_product(request: Request,
                        product_id: str,
                      name : str = Form(...),
                      description : str = Form(None),
                      price : float = Form(...),
                      discount_price : float = Form(None),
                      in_stock : bool = Form(True),
                      sub_category : str = Form(None),
                      category : str = Form(None),
                      brand : str = Form(None),
                      machine_type : List[str] = Form(None),
                      image_urls : List[str] = Form(None),
                      images : List[UploadFile] = File(None),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    print("Fetched product:", product)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    print("Updating product fields")
    print("Current product data:", product.__dict__)
    print("Received update data:", {
        "name": name,
        "description": description,
        "price": price,
        "discount_price": discount_price,
        "in_stock": in_stock,
        "sub_category": sub_category,
        "category": category,
        "brand": brand,
        "machine_type": machine_type,
        "images": images,
    })
    if name is not None:
        product.name = name
    if description is not None:
        product.description = description
    if price is not None:
        product.price = price
    if discount_price is not None:
        product.discount_price = discount_price
    if in_stock is not None:
        product.in_stock = in_stock
    if sub_category is not None:
        product.sub_category = sub_category
    if category is not None:
        product.category = category
    if brand is not None:
        product.brand = brand
    # if machine_type is not None:
    #     product.machine_type = machine_type

    # Handle image uploads
    if images is not None:
        images_urls = image_urls if image_urls is not None else []
        for image in images:
            print("Uploading image to Cloudinary")
            upload_result = await upload_file_to_cloudinary(image)
            print(f"Upload result: {upload_result}")
            if upload_result:
                print(f"Uploaded image URL: {upload_result}")
                images_urls.append(upload_result)
        product.images_urls = images_urls
    else :
        if image_urls is not None:
            product.images_urls = image_urls
    form = await request.form()
    print("Form items:", list(form.items()))

    downloadable_files = {}

    for key, value in form.items():

        # Skip normal fields
        if key in ["name", "description", "price", "discount_price", "in_stock",
                "sub_category", "category", "brand", "machine_type", "color", "size", 
                "stock_count", "images"]:
            continue

        # Detect files even if type mismatch between Starlette/FastAPI UploadFile
        if hasattr(value, "filename") and value.filename:
            downloadable_files[key] = value

    print(f"Detected downloadable files: {downloadable_files.keys()}")

    downloadable_files_urls = {}

    for key, value in downloadable_files.items():
        print(f"Uploading downloadable file: {key}")
        file_url = await upload_to_r2(value)
        downloadable_files_urls[key] = file_url
    print("Existing downloadable files:", product.downloadable_files)
    print("Downloadable files URLs:", downloadable_files_urls)
    if downloadable_files_urls:
        total_downloadable_files = {}
        if product.downloadable_files:
            total_downloadable_files = json.loads(product.downloadable_files)
        total_downloadable_files.update(downloadable_files_urls)
        product.downloadable_files = json.dumps(total_downloadable_files)
        product.machine_type = list(total_downloadable_files.keys())
    
    
    await db.commit()
    await db.refresh(product)
    return product

@router.get("/product_download_urls/{payment_id}/{product_id}/{file_type}")
async def get_product_download_urls(payment_id: str, product_id: str, file_type: str, expiry: int = 3600, db: AsyncSession = Depends(get_db)):
    order_status = await db.execute(select(Order).where(Order.payment_id == payment_id))
    order_status = order_status.scalars().first()
    print(order_status.status if order_status else "No order found")
    if not order_status or order_status.status != "paid":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payment not completed for this order",
        )
    item_id = await db.execute(select(OrderItem).where(OrderItem.order_id == order_status.id))
    item_id = item_id.scalars().first()
    # print(item_id.product_id)
    # product_id = item_id.product_id
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    
    urls = {}
    if product.downloadable_files:
        downloadable_files = json.loads(product.downloadable_files)
        if file_type in downloadable_files:
            file_url = downloadable_files[file_type]
            download_url = await generate_r2_download_url(file_url, expiry)
            urls[f'{file_type}_url'] = download_url
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{file_type} not found for this product",
            )
    return urls
