"""The shop's HTTP API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.cart import Cart

app = FastAPI(title="Python shop", version="1.0.0")

PRODUCTS = {
    1: {"id": 1, "name": "Green tea", "price": 3.5},
    2: {"id": 2, "name": "Tea cup", "price": 8.0},
}


class Product(BaseModel):
    id: int
    name: str
    price: float


class QuoteLine(BaseModel):
    product_id: int
    quantity: int


class QuoteRequest(BaseModel):
    lines: list[QuoteLine]
    discount_percent: float = 0


class Quote(BaseModel):
    items: int
    total: float


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/products", response_model=list[Product])
def list_products() -> list[dict[str, object]]:
    return list(PRODUCTS.values())


@app.get("/products/{product_id}", response_model=Product, responses={404: {"description": "No such product"}})
def get_product(product_id: int) -> dict[str, object]:
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="No such product")
    return PRODUCTS[product_id]


@app.post("/cart/quote", response_model=Quote, responses={404: {"description": "No such product"}})
def quote(body: QuoteRequest) -> Quote:
    cart = Cart()
    for line in body.lines:
        product = PRODUCTS.get(line.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="No such product")
        cart.add(str(product["name"]), line.quantity, float(product["price"]))  # type: ignore[arg-type]
    return Quote(items=cart.count(), total=cart.total(body.discount_percent))
