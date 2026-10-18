import decimal
from decimal import Decimal


def from_float_literals():
	# ruleid: frappe-kit-decimal-from-float-literal
	positive = Decimal(0.1)
	# ruleid: frappe-kit-decimal-from-float-literal
	negative = Decimal(-1.25)
	# ruleid: frappe-kit-decimal-from-float-literal
	exponent = Decimal(1e-3)
	# ruleid: frappe-kit-decimal-from-float-literal
	qualified = decimal.Decimal(2.5)
	return positive, negative, exponent, qualified


def nested_float_literal(amount):
	# ruleid: frappe-kit-decimal-from-float-literal
	return round(amount * Decimal(0.07), 2)


def from_strings_and_integers(rate):
	# ok: frappe-kit-decimal-from-float-literal
	from_string = Decimal("0.1")
	# ok: frappe-kit-decimal-from-float-literal
	from_integer = Decimal(10)
	# ok: frappe-kit-decimal-from-float-literal
	nested_str = Decimal(str(rate))
	# ok: frappe-kit-decimal-from-float-literal
	qualified = decimal.Decimal("2.5")
	return from_string, from_integer, nested_str, qualified
