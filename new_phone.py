def lookup_phone_advanced(number):
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder
        p = phonenumbers.parse(number, None)
        if not phonenumbers.is_valid_number(p):
            return {"error": "Numero non valido"}
        result = {
            "number": number,
            "operator": carrier.name_for_number(p, "it") or None,
            "region": geocoder.description_for_number(p, "it") or None,
            "country": phonenumbers.region_code_for_number(p),
        }
        region_name = result.get("region") or "Italy"
        try:
            import requests
            geo_api_url = "https://nominatim.openstreetmap.org/search?q=" + region_name + ",Italy&format=json&limit=1"
            geo_response = requests.get(geo_api_url, headers={"User-Agent": "NEXORA-OSINT-Tool"}, timeout=10).json()
            if geo_response:
                lat = geo_response[0]['lat']
                lon = geo_response[0]['lon']
                result["latitude"] = lat
                result["longitude"] = lon
                result["google_maps_link"] = "https://www.google.com/maps?q=" + lat + "," + lon
        except Exception as e:
            result["geo_error"] = str(e)
        return result
    except Exception as e:
        return {"error": str(e)}
