import frappe
from frappe.tests import IntegrationTestCase


class TestInstallation(IntegrationTestCase):
	def test_app_is_installed(self):
		self.assertIn("__APP_NAME__", frappe.get_installed_apps())

	def test_module_belongs_to_app(self):
		module = frappe.get_doc("Module Def", "__APP_TITLE__")
		self.assertEqual(module.app_name, "__APP_NAME__")
