# Python shop (TestForge demo project)

A small FastAPI service with a pricing module, a cart and an inventory module. Only the
discount function has a test; TestForge's analysis finds the rest untested. `split_bill`
has a real bug its own docstring documents: the shares do not add up to the total.
