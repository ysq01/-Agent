from app.db.base import Base
from app.db.session import make_engine
from app.models import Order, OrderItem, Product, Shipment, Ticket, User


def init_database(database_url: str | None = None) -> None:
    engine = make_engine(database_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()


if __name__ == "__main__":
    init_database()
    print("Database tables initialized.")
