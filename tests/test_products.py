def _create_product(client, admin_auth_headers, sku="SKU-1", qty=10, price="19.99"):
    return client.post(
        "/products",
        json={
            "sku": sku,
            "name": "Widget",
            "description": "A useful widget",
            "price": price,
            "initial_quantity": qty,
            "reorder_threshold": 2,
        },
        headers=admin_auth_headers,
    )


def test_admin_can_create_product(client, admin_auth_headers):
    resp = _create_product(client, admin_auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["sku"] == "SKU-1"
    assert body["is_active"] is True


def test_customer_cannot_create_product(client, customer_auth_headers):
    resp = client.post(
        "/products",
        json={"sku": "SKU-X", "name": "Nope", "price": "5.00", "initial_quantity": 1},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_anonymous_cannot_create_product(client):
    resp = client.post("/products", json={"sku": "SKU-Y", "name": "Nope", "price": "5.00"})
    assert resp.status_code == 401


def test_duplicate_sku_rejected(client, admin_auth_headers):
    _create_product(client, admin_auth_headers, sku="DUP-1")
    resp = _create_product(client, admin_auth_headers, sku="DUP-1")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SKU_TAKEN"


def test_invalid_price_rejected(client, admin_auth_headers):
    resp = client.post(
        "/products",
        json={"sku": "BAD-PRICE", "name": "Bad", "price": "-5.00", "initial_quantity": 1},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


def test_list_products_public(client, admin_auth_headers):
    _create_product(client, admin_auth_headers, sku="LIST-1")
    resp = client.get("/products")
    assert resp.status_code == 200
    assert any(p["sku"] == "LIST-1" for p in resp.json())


def test_get_missing_product_404(client):
    resp = client.get("/products/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_admin_can_update_product(client, admin_auth_headers):
    created = _create_product(client, admin_auth_headers, sku="UPD-1").json()
    resp = client.put(
        f"/products/{created['id']}",
        json={"price": "29.99"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["price"] == "29.99"


def test_admin_can_deactivate_product(client, admin_auth_headers):
    created = _create_product(client, admin_auth_headers, sku="DEL-1").json()
    resp = client.delete(f"/products/{created['id']}", headers=admin_auth_headers)
    assert resp.status_code == 204

    # deactivated products are excluded from the default (active_only) listing
    listing = client.get("/products").json()
    assert not any(p["sku"] == "DEL-1" for p in listing)
