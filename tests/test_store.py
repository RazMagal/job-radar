from jobradar.store import Store


def test_remark_applied_keeps_cv_note_and_original_date(tmp_path):
    meta = {"company": "X", "title": "T", "url": "https://x/1"}
    first = Store(tmp_path).mark_applied("abc", meta, cv="Verification", note="referred")

    # A later bare re-mark (say, pasted from the page without --cv) must merge,
    # not rebuild the entry from scratch.
    second = Store(tmp_path).mark_applied("abc", meta)
    assert second["cv"] == "Verification"
    assert second["note"] == "referred"
    assert second["applied_on"] == first["applied_on"]


def test_new_cv_overrides_old_one(tmp_path):
    meta = {"company": "X", "title": "T", "url": "https://x/1"}
    Store(tmp_path).mark_applied("abc", meta, cv="Verification")
    entry = Store(tmp_path).mark_applied("abc", meta, cv="Linux")
    assert entry["cv"] == "Linux"
