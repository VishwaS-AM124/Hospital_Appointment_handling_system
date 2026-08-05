"""Business-logic layer.

All five business rules are enforced here, never in the routers. Routers validate
input, call one function from this package, and serialize the result.

Global lock ordering, obeyed by every function that takes row locks:

    slots  ->  appointments

Booking, cancelling and completing all touch both tables. Taking the locks in one
fixed order is what guarantees two concurrent requests can never deadlock each other.
"""
