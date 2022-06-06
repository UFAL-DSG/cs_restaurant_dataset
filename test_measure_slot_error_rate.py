from measure_slot_error_rate import parse_da, Evaluator, logging

def test_parse_da():
    da = "inform(abc=123)"
    parsed = parse_da(da)
    
    assert parsed == {
        "type": "inform",
        "attributes": {"abc" : ["123"]}
    }
    da = "inform()"
    parsed = parse_da(da)
    assert parsed == {
        "type": "inform",
        "attributes": {}
    }
    da = "?request(rr='Baráčnická Rychta',rr=dont_care,cc=382)"
    parsed = parse_da(da)
    assert parsed == {
        "type": "?request",
        "attributes": {"rr": ["Baráčnická Rychta", "dont_care"], "cc": ["382"]}
    }

def test_evaluator_name():
    surface_forms = {
        "name": {
            "Restaurace A": [
                "Restaurace A\tRestaurace A",
                "Restaurace A\tRestauraci A"
            ],
            "Restaurace B": [
                "Restaurace B\tRestaurace B",
                "Restaurace B\tRestauraci B"
            ],
        }
    }
    ser = Evaluator(surface_forms)

    # Correct output
    error_rate, errs, miss, add = ser.evaluate(["inform(name='Restaurace A')"], ["Našla jsem Restauraci A"])
    assert error_rate == 0
    # Missing error
    error_rate, errs, miss, add = ser.evaluate(["inform(name='Restaurace A')"], ["Našla jsem Restauraci"])
    assert error_rate == 1 and miss == 1 and add == 0
    # Additional error
    error_rate, errs, miss, add = ser.evaluate(["inform(type=restaurant)"], ["Našla jsem Restauraci B"])
    assert error_rate == 1 and miss == 0 and add == 1
    # Additional error with the same slot
    error_rate, errs, miss, add = ser.evaluate(["inform(name='Restaurace A')"], ["Našla jsem Restauraci A a Restauraci B"])
    assert error_rate == 1 and miss == 0 and add == 1
    # Repetition doesn't count as an error
    error_rate, errs, miss, add = ser.evaluate(["inform(name='Restaurace B')"], ["Našla jsem Restauraci B a Restauraci B"])
    assert error_rate == 0 and miss == 0 and add == 0
    # Additional+Missing error
    error_rate, errs, miss, add = ser.evaluate(["inform(name='Restaurace B')"], ["Našla jsem Restauraci A"])
    assert error_rate == 2 and miss == 1 and add == 1

def test_evaluator_kids_allowed():
    surface_forms = {}
    ser = Evaluator(surface_forms)

    # Correct output
    error_rate, errs, miss, add = ser.evaluate(["inform(kids_allowed=no)"], ["Restaurace není vhodná pro děti"])
    assert error_rate == 0
    # Correct output
    error_rate, errs, miss, add = ser.evaluate(["inform(kids_allowed=yes)"], ["Restaurace je vhodná pro děti"])
    assert error_rate == 0
    # Missing error
    error_rate, errs, miss, add = ser.evaluate(["inform(kids_allowed=no)"], ["Doporučuji restauraci BarBar"])
    assert error_rate == 1 and miss == 1 and add == 0
    # Additional error
    error_rate, errs, miss, add = ser.evaluate(["inform(type=restaurant)"], ["Restaurace je vhodná pro děti"])
    assert error_rate == 1 and miss == 0 and add == 1
    # Additional+Missing error
    error_rate, errs, miss, add = ser.evaluate(["inform(kids_allowed=no)"], ["Restaurace je vhodná pro děti"])
    assert error_rate == 2 and miss == 1 and add == 1

    # --- special cases ---

    # Correct output we cannot check
    error_rate, errs, miss, add = ser.evaluate(["inform(count=12,kids_allowed=dont_care)"], ["V nabídce je 12 restaurací , které nemají požadavky ohledně dětí"])
    assert error_rate == 0
    # Incorrect output we cannot check
    error_rate, errs, miss, add = ser.evaluate(["inform(count=12,kids_allowed=dont_care)"], ["V nabídce je 12 restaurací které jsou vhodné pro děti"])
    assert error_rate == 0
    # But we can check some additional errors outside of yes/no value
    # because we check the presence of the word "dítě"
    error_rate, errs, miss, add = ser.evaluate(["inform(count=12)"], ["V nabídce je 12 restaurací, které nemají požadavky ohledně dětí"])
    assert error_rate == 1 and miss == 0 and add == 1

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)

    test_parse_da()
    test_evaluator_name()
    test_evaluator_kids_allowed()