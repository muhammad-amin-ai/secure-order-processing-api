def _create_product(client, admin_auth_headers, sku="INV-SKU", qty=10):
    return client.post(
        "/products",
        json={"sku": sku, "name": "Gadget", "price": "9.99", "initial_quantity": qty, "reorder_threshold": 1},
        headers=admin_auth_headers,
    ).json()


def test_inventory_created_alongside_product(client, admin_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=15)
    resp = client.get(f"/inventory/{product['id']}", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["quantity_on_hand"] == 15


def test_admin_can_restock(client, admin_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=5)
    resp = client.patch(
        f"/inventory/{product['id']}",
        json={"delta": 20, "reason": "supplier delivery"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["quantity_on_hand"] == 25


def test_stock_cannot_go_negative(client, admin_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=3)
    resp = client.patch(
        f"/inventory/{product['id']}",
        json={"delta": -10, "reason": "damage"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"


def test_customer_cannot_adjust_inventory(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers)
    resp = client.patch(
        f"/inventory/{product['id']}",
        json={"delta": 5, "reason": "trying anyway"},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 403
