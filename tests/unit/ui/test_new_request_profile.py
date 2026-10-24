from streamlit.testing.v1 import AppTest


def _page() -> None:
    from barthelona.ui.pages.new_request import page_new_request

    page_new_request()


def test_the_profile_radio_offers_meterless_and_selects_it_first() -> None:
    app = AppTest.from_function(_page, default_timeout=60).run()  # the first import of the page is slow
    assert not app.exception
    profile = next(radio for radio in app.radio if radio.label == "Model Profile")
    assert profile.options[0].startswith("🌙 Meterless")
    assert [option.split(" ")[1] for option in profile.options] == ["Meterless", "Local", "Hybrid", "Cloud"]
    assert profile.value == "meterless"
