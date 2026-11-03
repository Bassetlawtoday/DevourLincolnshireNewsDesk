"""App Publishing area selector checks."""
from newsdesk.app_publishing.areas import available_areas


def test_area_choices_include_main_towns():
    areas = available_areas()
    assert "Lincoln" in areas
    assert "Boston" in areas
    assert "Grimsby" in areas
    assert "Scunthorpe" in areas


def test_non_geographical_source_labels_excluded():
    areas = available_areas()
    assert "Lincoln Crown Court" not in areas
    assert "Grantham station" not in areas
    assert "Lincolnshire" not in areas
    assert len(areas) == len(set(areas))
