import frappe


def manual_boundaries():
	# ruleid: frappe-kit-no-manual-transaction-boundary
	frappe.db.commit()
	# ruleid: frappe-kit-no-manual-transaction-boundary
	frappe.db.rollback()


def nested_boundary(doc):
	try:
		doc.save()
	except Exception:
		# ruleid: frappe-kit-no-manual-transaction-boundary
		frappe.db.rollback()
		raise
	# ruleid: frappe-kit-no-manual-transaction-boundary
	return log_result(frappe.db.commit())


def framework_boundary(name):
	# ok: frappe-kit-no-manual-transaction-boundary
	return frappe.db.exists("ToDo", name)


def savepoint_boundary(doc):
	# ok: frappe-kit-no-manual-transaction-boundary
	frappe.db.savepoint("before_save")
	doc.save()


def log_result(value):
	return value
