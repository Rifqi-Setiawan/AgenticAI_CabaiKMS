import openpyxl

from src.schema.provenance import source_file_sha256


def test_same_bytes_have_same_sha256_and_modified_bytes_change_it(tmp_path):
    first = tmp_path / "first.xlsx"
    second = tmp_path / "renamed.xlsx"
    changed = tmp_path / "changed.xlsx"

    workbook = openpyxl.Workbook()
    workbook.active["A1"] = "original"
    workbook.save(first)
    workbook.close()
    second.write_bytes(first.read_bytes())

    workbook = openpyxl.load_workbook(first)
    workbook.active["A1"] = "modified"
    workbook.save(changed)
    workbook.close()

    assert source_file_sha256(first) == source_file_sha256(second)
    assert source_file_sha256(first) != source_file_sha256(changed)
