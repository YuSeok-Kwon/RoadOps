import pytest

from roadops.safemap_crime import validate_wms_response


def test_validates_png_and_returns_embeddable_data_url():
    result = validate_wms_response(b"\x89PNG\r\n\x1a\nabc", "image/png")
    assert result["image_type"] == "image/png"
    assert result["data_url"].startswith("data:image/png;base64,")


def test_rejects_provider_error_document_as_image():
    with pytest.raises(ValueError, match="safemap_wms_response_not_image"):
        validate_wms_response(b"<ServiceException>invalid key</ServiceException>", "text/xml")
