# DDD with dataclasses

Pydantic is the default (see SKILL.md). Use these forms only when Pydantic
is unavailable, or when the type is a pure carrier that needs no validation.

## Contents
- Entities
- Value objects
- Aggregates
- Domain events

---

## Entities with dataclasses

Entities have identity (an `id` field) that persists over time. Equality is by identity, not value.

```python
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime


@dataclass
class User:
    id: UUID
    email: str
    name: str
    created_at: datetime

    @classmethod
    def create(cls, email: str, name: str) -> "User":
        return cls(
            id=uuid4(),
            email=email.lower().strip(),
            name=name.strip(),
            created_at=datetime.utcnow(),
        )

    def rename(self, new_name: str) -> "User":
        if not new_name.strip():
            raise ValueError("Name must not be blank")
        from dataclasses import replace
        return replace(self, name=new_name.strip())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
```

---

## Value Objects with dataclasses

Value objects have no identity — equality is by value. Always immutable.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: int   # store in minor units (cents)
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Amount must not be negative")
        if len(self.currency) != 3:
            raise ValueError("Currency must be a 3-letter ISO code")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.amount / 100:.2f} {self.currency}"


@dataclass(frozen=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        if "@" not in self.value:
            raise ValueError(f"Invalid email: {self.value!r}")
        object.__setattr__(self, "value", self.value.lower().strip())
```

---

## Aggregates with dataclasses

Aggregates group entities and value objects under a single root. External code only interacts with the root. Invariants are enforced inside the aggregate.

```python
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from typing import List


@dataclass
class OrderLine:
    product_id: UUID
    quantity: int
    unit_price: Money


@dataclass
class Order:
    id: UUID
    customer_id: UUID
    lines: List[OrderLine] = field(default_factory=list)
    _events: List["DomainEvent"] = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def create(cls, customer_id: UUID) -> "Order":
        order = cls(id=uuid4(), customer_id=customer_id)
        order._events.append(OrderCreated(order_id=order.id, customer_id=customer_id))
        return order

    def add_line(self, product_id: UUID, quantity: int, unit_price: Money) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.lines.append(OrderLine(product_id, quantity, unit_price))

    @property
    def total(self) -> Money:
        if not self.lines:
            return Money(0, "USD")
        result = Money(0, self.lines[0].unit_price.currency)
        for line in self.lines:
            result = result.add(Money(line.quantity * line.unit_price.amount, line.unit_price.currency))
        return result

    def collect_events(self) -> List["DomainEvent"]:
        events, self._events = self._events, []
        return events
```

---

---

## Domain Events with dataclasses

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    # kw_only matters: without it, a defaulted field in the base class makes
    # every non-default field in a subclass a TypeError at class creation.
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, kw_only=True)
class OrderCreated(DomainEvent):
    order_id: UUID
    customer_id: UUID


@dataclass(frozen=True, kw_only=True)
class OrderShipped(DomainEvent):
    order_id: UUID
    tracking_number: str
```

---

---

