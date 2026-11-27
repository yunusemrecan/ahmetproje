"""{{t:tests_doc}}"""

import main


def setup_function() -> None:
    main.notes.clear()


def test_index_is_empty_at_start() -> None:
    response = main.app.test_client().get("/")
    assert response.status_code == 200
    assert "{{t:web_empty}}" in response.get_data(as_text=True)


def test_add_note() -> None:
    client = main.app.test_client()
    response = client.post("/add", data={"note": "{{t:web_sample}}"}, follow_redirects=True)
    assert response.status_code == 200
    assert "{{t:web_sample}}" in response.get_data(as_text=True)


def test_empty_note_is_ignored() -> None:
    main.app.test_client().post("/add", data={"note": "   "})
    assert main.notes == []
