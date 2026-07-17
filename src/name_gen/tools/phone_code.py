import phonenumbers
import pycountry


def get_country_code(name: str) -> int:
    try:
        iso_name = name_to_iso(name)
    except LookupError:
        # TODO: LOGGER HERE
        print(f"Could not convert: {name}\nTry country code.")
        return
    except Exception as e:
        print(f"Unexpected exception: {e}")

    cc = phonenumbers.country_code_for_region(iso_name)
    return cc


def name_to_iso(name: str) -> str:
    # handles "United States", "USA", etc. via fuzzy search
    return pycountry.countries.search_fuzzy(name)[0].alpha_2
