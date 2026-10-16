"""Offline regressions for the public template validator."""

import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import check_templates as checker


class TemplateCheckerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)

    def document(self):
        return {"submodels": [{
            "modelType": "Submodel", "id": "urn:test:template",
            "idShort": "Template", "kind": "Template",
            "submodelElements": [{
                "modelType": "Property", "idShort": "Reading", "valueType": "xs:integer",
            }],
        }]}

    def check(self, document, filename="Template.json"):
        text = document if isinstance(document, str) else json.dumps(document)
        (self.root / filename).write_text(text, encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            valid = checker.check_template(self.root, self.root)
        return valid, output.getvalue()

    def test_uses_the_requested_public_sdk(self):
        expected = {"3.0": "aas_core3", "3.1": "aas_core3_1"}[checker.AAS_VERSION]
        self.assertEqual(checker.aas_verification.__name__, f"{expected}.verification")

    def test_template_may_leave_instance_values_unset(self):
        valid, output = self.check(self.document())
        self.assertTrue(valid, output)

    def test_valid_typed_value_passes(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["value"] = "42"
        valid, output = self.check(document)
        self.assertTrue(valid, output)

    def test_invalid_typed_value_fails_with_location(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["value"] = "not-an-integer"
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn(".submodels[0].submodel_elements[0]", output)
        self.assertIn("Value must be consistent", output)

    def test_invalid_id_short_fails(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["idShort"] = "invalid name"
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn("id_short", output)

    def test_unknown_model_type_fails(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["modelType"] = "NotAnAasElement"
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn("check failed", output)

    def test_duplicate_qualifier_types_fail(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["qualifiers"] = [
            {"type": "FormInfo", "valueType": "xs:string", "value": "First"},
            {"type": "FormInfo", "valueType": "xs:string", "value": "Second"},
        ]
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn("AASd-021", output)

    def test_iec61360_measure_requires_a_unit(self):
        document = self.document()
        document["conceptDescriptions"] = [{
            "modelType": "ConceptDescription", "id": "urn:test:quantity", "idShort": "Quantity",
            "embeddedDataSpecifications": [{
                "dataSpecification": {
                    "type": "ExternalReference", "keys": [{
                        "type": "GlobalReference",
                        "value": "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIEC61360/3/0",
                    }],
                },
                "dataSpecificationContent": {
                    "modelType": "DataSpecificationIec61360",
                    "preferredName": [{"language": "en", "text": "Quantity"}],
                    "definition": [{"language": "en", "text": "A measured quantity"}],
                    "dataType": "INTEGER_MEASURE",
                },
            }],
        }]
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn("AASc-3a-009", output)

    def test_invalid_json_fails(self):
        valid, output = self.check("{not json}")
        self.assertFalse(valid)
        self.assertIn("check failed", output)

    def test_empty_environment_is_not_a_template(self):
        valid, output = self.check({})
        self.assertFalse(valid)
        self.assertIn("No submodels defined", output)

    def test_valid_file_does_not_hide_another_files_failure(self):
        (self.root / "Bad.json").write_text("{not json}", encoding="utf-8")
        valid, output = self.check(self.document(), filename="Good.json")
        self.assertFalse(valid)
        self.assertIn("Bad.json check failed", output)
        self.assertIn("Good.json is ok", output)

    def test_supplemental_semantic_id_requires_main_semantic_id(self):
        document = self.document()
        document["submodels"][0]["submodelElements"][0]["supplementalSemanticIds"] = [{
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "urn:test:additional-concept"}],
        }]
        valid, output = self.check(document)
        self.assertFalse(valid)
        self.assertIn("AASd-118", output)

    def test_existing_exclusion_is_reported(self):
        valid, output = self.check("{not json}", filename=sorted(checker._SKIP)[0])
        self.assertTrue(valid)
        self.assertIn("SKIPPED (existing known legacy exclusion)", output)

    def test_latest_release_is_not_lost_when_it_has_nested_files(self):
        for version in ("1/0/1", "1/0/2", "2/0"):
            folder = self.root / "Example" / version
            folder.mkdir(parents=True)
            (folder / "Template.json").write_text("{}", encoding="utf-8")
        latest = self.root / "Example" / "2" / "0"
        (latest / "images").mkdir()
        self.assertEqual(checker.find_latest_per_submodel(self.root, self.root), [latest])

    def test_main_fails_if_no_template_json_is_found(self):
        (self.root / "published").mkdir()
        script = self.root / "_help_and_materials" / "check_templates.py"
        output = io.StringIO()
        with mock.patch.object(checker, "__file__", str(script)):
            with contextlib.redirect_stdout(output):
                self.assertEqual(checker.main(), 1)
        self.assertIn("No template JSON", output.getvalue())

    def test_main_does_not_pass_when_every_file_is_excluded(self):
        folder = self.root / "published" / "Example" / "1" / "0"
        folder.mkdir(parents=True)
        (folder / sorted(checker._SKIP)[0]).write_text("{}", encoding="utf-8")
        script = self.root / "_help_and_materials" / "check_templates.py"
        output = io.StringIO()
        with mock.patch.object(checker, "__file__", str(script)):
            with contextlib.redirect_stdout(output):
                self.assertEqual(checker.main(), 1)
        self.assertIn("No template JSON eligible", output.getvalue())


if __name__ == "__main__":
    unittest.main()
