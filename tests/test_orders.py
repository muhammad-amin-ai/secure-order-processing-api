def _create_product(client, admin_auth_headers, sku="ORD-SKU", qty=10, price="10.00"):
    return client.post(
        "/products",
        json={"sku": sku, "name": "Order Item", "price": price, "initial_quantity": qty, "reorder_threshold": 1},
        headers=admin_auth_headers,
    ).json()


def test_create_order_deducts_stock_and_computes_total(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10, price="10.00")

    resp = client.post(
        "/orders",
        json={"items": [{"product_id": product["id"], "quantity": 3}]},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "pending"
    assert order["total_amount"] == "30.00"
    assert order["items"][0]["quantity"] == 3

    inv = client.get(f"/inventory/{product['id']}", headers=admin_auth_headers).json()
    assert inv["quantity_on_hand"] == 7


def test_create_order_merges_duplicate_line_items(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10, price="5.00")
    resp = client.post(
        "/orders",
        json={"items": [
            {"product_id": product["id"], "quantity": 2},
            {"product_id": product["id"], "quantity": 3},
        ]},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 5
    assert order["total_amount"] == "25.00"


def test_create_order_insufficient_stock_leaves_no_partial_state(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=2, price="10.00")

    resp = client.post(
        "/orders",
        json={"items": [{"product_id": product["id"], "quantity": 5}]},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # Stock must be untouched -- the failed order should not have deducted anything.
    inv = client.get(f"/inventory/{product['id']}", headers=admin_auth_headers).json()
    assert inv["quantity_on_hand"] == 2

    # And no order should have been persisted for this customer.
    orders = client.get("/orders", headers=customer_auth_headers).json()
    assert orders == []


def test_create_order_unknown_product_rejected(client, customer_auth_headers):
    resp = client.post(
        "/orders",
        json={"items": [{"product_id": "does-not-exist", "quantity": 1}]},
        headers=customer_auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_create_order_empty_items_rejected(client, customer_auth_headers):
    resp = client.post("/orders", json={"items": []}, headers=customer_auth_headers)
    assert resp.status_code == 422  # caught by pydantic min_length on the list


def test_customer_only_sees_own_orders(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10)
    client.post("/orders", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=customer_auth_headers)

    admin_orders = client.get("/orders", headers=admin_auth_headers).json()
    customer_orders = client.get("/orders", headers=customer_auth_headers).json()
    assert len(customer_orders) == 1
    assert len(admin_orders) == 1  # admin sees all orders too


def test_customer_cannot_view_others_order(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10)
    order = client.post(
        "/orders", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=customer_auth_headers
    ).json()

    # A second, different customer
    client.post("/auth/register", json={"email": "other@example.com", "password": "Password123"})
    other_login = client.post("/auth/login", data={"username": "other@example.com", "password": "Password123"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = client.get(f"/orders/{order['id']}", headers=other_headers)
    assert resp.status_code == 403


def test_order_status_transition_flow(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10)
    order = client.post(
        "/orders", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=customer_auth_headers
    ).json()

    # pending -> paid
    resp = client.patch(f"/orders/{order['id']}/status", json={"status": "paid"}, headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"

    # paid -> fulfilled
    resp = client.patch(f"/orders/{order['id']}/status", json={"status": "fulfilled"}, headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "fulfilled"

    # fulfilled -> paid is not a valid transition
    resp = client.patch(f"/orders/{order['id']}/status", json={"status": "paid"}, headers=admin_auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TRANSITION"


def test_cancelling_order_restocks_items(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10)
    order = client.post(
        "/orders", json={"items": [{"product_id": product["id"], "quantity": 4}]}, headers=customer_auth_headers
    ).json()

    inv_before = client.get(f"/inventory/{product['id']}", headers=admin_auth_headers).json()
    assert inv_before["quantity_on_hand"] == 6

    resp = client.patch(f"/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin_auth_headers)
    assert resp.status_code == 200

    inv_after = client.get(f"/inventory/{product['id']}", headers=admin_auth_headers).json()
    assert inv_after["quantity_on_hand"] == 10


def test_customer_cannot_change_order_status(client, admin_auth_headers, customer_auth_headers):
    product = _create_product(client, admin_auth_headers, qty=10)
    order = client.post(
        "/orders", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=customer_auth_headers
    ).json()
    resp = client.patch(f"/orders/{order['id']}/status", json={"status": "paid"}, headers=customer_auth_headers)
    assert resp.status_code == 403
