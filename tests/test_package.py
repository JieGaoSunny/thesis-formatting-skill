from importlib.metadata import metadata


def test_installed_package_metadata() -> None:
    package_metadata = metadata("thesis-formatting-skill")

    assert package_metadata["Name"] == "thesis-formatting-skill"
    assert "Apple University" in package_metadata["Summary"]
