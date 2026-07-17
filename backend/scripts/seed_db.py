from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.models import Order, OrderItem, Product, Shipment, Ticket, User


BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class SeedSummary:
    users: int
    products: int
    orders: int
    order_items: int
    shipments: int
    tickets: int


def _count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _seed_users(session: Session) -> list[User]:
    tiers = ["standard", "silver", "gold", "vip"]

    for index in range(1, 31):
        external_id = f"U{index:04d}"
        user = session.scalar(select(User).where(User.external_id == external_id))
        if user is None:
            session.add(
                User(
                    external_id=external_id,
                    name=f"Customer {index:02d}",
                    email=f"customer{index:02d}@example.com",
                    phone=f"1380000{index:04d}",
                    tier=tiers[index % len(tiers)],
                )
            )

    session.flush()
    return list(
        session.scalars(
            select(User)
            .where(User.external_id.in_([f"U{index:04d}" for index in range(1, 31)]))
            .order_by(User.external_id)
        )
    )


def _seed_products(session: Session) -> list[Product]:
    categories = ["electronics", "home", "beauty", "sports", "books"]

    for index in range(1, 21):
        sku = f"SKU-{index:04d}"
        product = session.scalar(select(Product).where(Product.sku == sku))
        if product is None:
            session.add(
                Product(
                    sku=sku,
                    name=f"Product {index:02d}",
                    category=categories[index % len(categories)],
                    price=Decimal("29.90") + Decimal(index * 7),
                    stock_quantity=100 + index * 3,
                    is_active=True,
                )
            )

    session.flush()
    return list(
        session.scalars(
            select(Product)
            .where(Product.sku.in_([f"SKU-{index:04d}" for index in range(1, 21)]))
            .order_by(Product.sku)
        )
    )


def _order_item_specs(order_index: int, products: list[Product]) -> list[tuple[Product, int]]:
    item_count = (order_index % 3) + 1
    return [
        (products[(order_index + offset - 1) % len(products)], ((order_index + offset) % 3) + 1)
        for offset in range(item_count)
    ]


def _seed_orders(session: Session, users: list[User], products: list[Product]) -> list[Order]:
    statuses = ["paid", "shipped", "delivered", "completed", "refunding"]
    payment_statuses = ["paid", "paid", "paid", "paid", "refund_pending"]

    for index in range(1, 101):
        order_number = f"ORD-2026-{index:04d}"
        order = session.scalar(select(Order).where(Order.order_number == order_number))
        item_specs = _order_item_specs(index, products)
        total_amount = sum(product.price * quantity for product, quantity in item_specs)

        if order is None:
            order = Order(
                order_number=order_number,
                user=users[(index - 1) % len(users)],
                status=statuses[index % len(statuses)],
                payment_status=payment_statuses[index % len(payment_statuses)],
                total_amount=total_amount,
                placed_at=BASE_TIME + timedelta(days=index, hours=index % 12),
            )
            session.add(order)
            session.flush()

        if not order.items:
            for product, quantity in item_specs:
                session.add(
                    OrderItem(
                        order=order,
                        product=product,
                        quantity=quantity,
                        unit_price=product.price,
                        subtotal=product.price * quantity,
                    )
                )

    session.flush()
    return list(
        session.scalars(
            select(Order)
            .where(
                Order.order_number.in_(
                    [f"ORD-2026-{index:04d}" for index in range(1, 101)]
                )
            )
            .order_by(Order.order_number)
        )
    )


def _seed_shipments(session: Session, orders: list[Order]) -> None:
    carriers = ["SF Express", "JD Logistics", "YTO Express", "ZTO Express"]
    statuses = ["in_transit", "delivered", "exception", "pending_pickup"]

    for index, order in enumerate(orders[:50], start=1):
        tracking_number = f"TRK-2026-{index:04d}"
        shipment = session.scalar(
            select(Shipment).where(Shipment.tracking_number == tracking_number)
        )
        if shipment is None:
            shipped_at = BASE_TIME + timedelta(days=index + 1)
            delivered_at = (
                shipped_at + timedelta(days=2)
                if statuses[index % len(statuses)] == "delivered"
                else None
            )
            session.add(
                Shipment(
                    tracking_number=tracking_number,
                    order=order,
                    carrier=carriers[index % len(carriers)],
                    status=statuses[index % len(statuses)],
                    shipped_at=shipped_at,
                    delivered_at=delivered_at,
                    last_checkpoint=f"Checkpoint {index:02d}",
                )
            )

    session.flush()


def _seed_tickets(session: Session, orders: list[Order]) -> None:
    categories = ["refund", "delivery", "invoice", "product_quality", "exchange"]
    statuses = ["open", "pending", "escalated", "resolved"]
    priorities = ["low", "medium", "high"]

    for index, order in enumerate(orders[:30], start=1):
        ticket_number = f"TCK-2026-{index:04d}"
        ticket = session.scalar(select(Ticket).where(Ticket.ticket_number == ticket_number))
        status = statuses[index % len(statuses)]

        if ticket is None:
            session.add(
                Ticket(
                    ticket_number=ticket_number,
                    order=order,
                    user=order.user,
                    category=categories[index % len(categories)],
                    status=status,
                    priority=priorities[index % len(priorities)],
                    subject=f"After-sales request for {order.order_number}",
                    description=(
                        "Customer needs support for order status, refund, or shipment."
                    ),
                    resolution=(
                        "Customer notified with resolution." if status == "resolved" else None
                    ),
                )
            )

    session.flush()


def seed_database(session: Session) -> SeedSummary:
    users = _seed_users(session)
    products = _seed_products(session)
    orders = _seed_orders(session, users, products)
    _seed_shipments(session, orders)
    _seed_tickets(session, orders)

    session.commit()

    return SeedSummary(
        users=_count_rows(session, User),
        products=_count_rows(session, Product),
        orders=_count_rows(session, Order),
        order_items=_count_rows(session, OrderItem),
        shipments=_count_rows(session, Shipment),
        tickets=_count_rows(session, Ticket),
    )


def main() -> None:
    engine = make_engine()
    Base.metadata.create_all(bind=engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        summary = seed_database(session)

    engine.dispose()
    print(
        "Seed data ready: "
        f"users={summary.users}, products={summary.products}, orders={summary.orders}, "
        f"order_items={summary.order_items}, shipments={summary.shipments}, "
        f"tickets={summary.tickets}."
    )


if __name__ == "__main__":
    main()
